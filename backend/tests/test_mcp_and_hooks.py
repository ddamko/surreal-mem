import json
from typing import TYPE_CHECKING, Any, cast

import httpx
import pytest
from pydantic import SecretStr

from surrealmem.bootstrap.app import create_app
from surrealmem.bootstrap.container import AppContainer
from surrealmem.bootstrap.hooks import HookHandlers, last_assistant_text, space_for
from surrealmem.bootstrap.mcp_server import build_mcp_server
from surrealmem.bootstrap.services import Services, build_services
from surrealmem.shared.infrastructure.config import Settings
from tests.fakes import FakeEmbedder

if TYPE_CHECKING:
    from pathlib import Path

    from surrealmem.shared.infrastructure.surreal.connection import SurrealConnection


def _settings() -> Settings:
    return Settings(surreal_url="mem://", log_json=False, api_token=SecretStr("t"))  # pyright: ignore[reportCallIssue]


@pytest.fixture
def services(migrated_db: SurrealConnection) -> Services:
    return build_services(migrated_db, settings=_settings(), embedder=FakeEmbedder())


def _structured(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structured_content", None) or getattr(
        result, "structuredContent", None
    )
    if structured:
        return cast("dict[str, Any]", structured)
    text = result.content[0].text
    return cast("dict[str, Any]", json.loads(text))


async def test_mcp_tools_end_to_end(migrated_db: SurrealConnection, services: Services) -> None:
    container = AppContainer(settings=_settings(), db=migrated_db, services=services)
    mcp = build_mcp_server(
        lambda: container,
        default_space="work",
        default_agent_id="tester",
        default_user_name="Derek",
    )
    names = {t.name for t in await mcp.list_tools()}
    assert {
        "memory_store_message",
        "memory_search",
        "memory_get_context",
        "memory_add_entity",
        "memory_add_fact",
        "memory_add_preference",
        "memory_create_relationship",
        "memory_get_entity",
        "memory_export_graph",
        "memory_start_trace",
        "memory_record_step",
        "memory_complete_trace",
        "memory_wait_for_extraction",
        "graph_query",
        "memory_get_conversation",
        "memory_list_conversations",
    } <= names

    stored = _structured(
        await mcp.call_tool("memory_store_message", {"content": "I'm Derek", "external_id": "s1"})
    )
    assert stored["conversation"]["space"] == "work" and stored["message"]["seq"] == 1
    assert stored["job_id"] is not None
    again = _structured(
        await mcp.call_tool(
            "memory_store_message", {"content": "Hi!", "role": "assistant", "external_id": "s1"}
        )
    )
    assert (
        again["conversation"]["id"] == stored["conversation"]["id"] and again["message"]["seq"] == 2
    )

    waited = _structured(
        await mcp.call_tool(
            "memory_wait_for_extraction", {"job_id": stored["job_id"], "timeout_seconds": 0}
        )
    )
    assert waited["status"] == "queued"

    entity = _structured(
        await mcp.call_tool(
            "memory_add_entity",
            {"name": "Derek Damko", "entity_type": "person", "aliases": ["Derek"]},
        )
    )
    assert entity["base_type"] == "person"
    with pytest.raises(Exception, match="entity_type"):
        await mcp.call_tool("memory_add_entity", {"name": "x", "entity_type": "robot"})

    rel = _structured(
        await mcp.call_tool(
            "memory_create_relationship",
            {
                "source": "Derek",
                "kind": "works at",
                "target": "WWS Sires",
                "target_type": "organization",
            },
        )
    )
    assert rel["kind"] == "WORKS_AT"
    fact = _structured(
        await mcp.call_tool(
            "memory_add_fact",
            {
                "statement": "Derek lives in Denver.",
                "subject": "Derek",
                "kind": "LIVES_IN",
                "object": "Denver",
                "object_type": "location",
                "valid_from": "2024-06",
            },
        )
    )
    assert fact["status"] == "active" and fact["valid_from"].startswith("2024-06-01")
    pref = _structured(
        await mcp.call_tool("memory_add_preference", {"preference": "Nushell", "category": "shell"})
    )
    assert pref["kind"] == "PREFERS" and pref["statement"] == "Derek Damko prefers Nushell."

    neighborhood = _structured(
        await mcp.call_tool("memory_get_entity", {"name_or_id": "derek", "hops": 1})
    )
    assert {n["name"] for n in neighborhood["neighbors"]} == {"WWS Sires", "Denver"}
    context = _structured(
        await mcp.call_tool("memory_get_context", {"query": "where does derek live and what shell"})
    )
    assert "Denver" in context["markdown"] and "Nushell" in context["markdown"]
    search = _structured(
        await mcp.call_tool("memory_search", {"query": "derek", "memory_types": ["fact"]})
    )
    assert search["items"] and all(i["type"] == "fact" for i in search["items"])
    graph = _structured(await mcp.call_tool("memory_export_graph", {}))
    assert len(graph["nodes"]) == 3 and {e["kind"] for e in graph["edges"]} == {
        "WORKS_AT",
        "LIVES_IN",
    }

    trace = _structured(await mcp.call_tool("memory_start_trace", {"task": "test traces"}))
    step = _structured(
        await mcp.call_tool(
            "memory_record_step",
            {"trace_id": trace["id"], "thought": "go", "tool": "Bash", "touched": ["Derek"]},
        )
    )
    assert step["touched_entity_ids"] == [entity["id"]] and step["tool_calls"][0]["tool"] == "Bash"
    done = _structured(
        await mcp.call_tool("memory_complete_trace", {"trace_id": trace["id"], "success": True})
    )
    assert done["status"] == "completed"

    rows = await mcp.call_tool("graph_query", {"query": "SELECT name FROM entity ORDER BY name"})
    payload = _structured(rows)
    names_out = [r["name"] for r in (payload.get("result", payload))]
    assert names_out == ["Denver", "Derek Damko", "WWS Sires"]
    with pytest.raises(Exception, match=r"read-only|only a single"):
        await mcp.call_tool("graph_query", {"query": "DELETE entity"})

    stats = list(await mcp.read_resource("memory://graph/stats"))
    assert "person" in str(cast("Any", stats[0]).content)
    catalog = list(await mcp.read_resource("memory://entities"))
    assert "Derek Damko (person)" in str(cast("Any", catalog[0]).content)
    conv = list(await mcp.read_resource(f"memory://context/{stored['conversation']['id']}"))
    assert "[user] I'm Derek" in str(cast("Any", conv[0]).content)
    prompt = await mcp.get_prompt("memory_review", {"entity": "Derek"})
    assert "memory_get_entity" in prompt.messages[0].content.text  # pyright: ignore[reportAttributeAccessIssue]


async def test_mcp_http_mount_is_protected(
    migrated_db: SurrealConnection, services: Services
) -> None:
    settings = _settings()
    app = create_app(
        settings=settings,
        container=AppContainer(settings=settings, db=migrated_db, services=services),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        anonymous = await client.post("/mcp/", json={})
        assert anonymous.status_code == 401
        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "t", "version": "0"},
            },
        }
        async with app.router.lifespan_context(app):
            initialized = await client.post(
                "/mcp/",
                json=body,
                headers={
                    "Authorization": "Bearer t",
                    "Accept": "application/json, text/event-stream",
                },
            )
        assert initialized.status_code == 200, initialized.text
        assert "surrealmem" in initialized.text


def test_space_for_and_transcript(tmp_path: Path) -> None:
    assert (
        space_for({"cwd": "/home/derek/code/vibe/Surreal Mem"}, override=None)
        == "project:surreal-mem"
    )
    assert space_for({}, override="work") == "work"
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        "\n".join(
            [
                json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}),
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "role": "assistant",
                            "content": [{"type": "tool_use", "name": "Bash"}],
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "role": "assistant",
                            "content": [{"type": "text", "text": "Done: fixed it."}],
                        },
                    }
                ),
                "not json",
            ]
        )
    )
    assert last_assistant_text(transcript) == "Done: fixed it."
    assert last_assistant_text(tmp_path / "missing.jsonl") is None


async def test_hook_handlers(services: Services, tmp_path: Path) -> None:
    handlers = HookHandlers(services, token_budget=600)
    payload = {"session_id": "abc", "cwd": "/tmp/surreal-mem", "source": "startup"}
    started = await handlers.session_start(payload)
    text = started["hookSpecificOutput"]["additionalContext"]
    assert "space project:surreal-mem" in text

    first = await handlers.user_prompt_submit({**payload, "prompt": "Remember I prefer Nushell."})
    assert first is None  # nothing stored yet to recall
    from surrealmem.knowledge.domain import BaseType, NewEntity, NewFact

    derek, _ = await services.knowledge.upsert_entity(
        NewEntity(name="Derek", base_type=BaseType.PERSON, space="project:surreal-mem")
    )
    await services.knowledge.add_fact(
        NewFact(
            statement="Derek prefers Nushell.",
            space="project:surreal-mem",
            subject_id=derek.id,
            kind="PREFERS",
            category="shell",
            object_literal="Nushell",
        )
    )
    second = await handlers.user_prompt_submit({**payload, "prompt": "what shell does derek use"})
    assert second is not None and "Nushell" in second["hookSpecificOutput"]["additionalContext"]

    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "You use Nushell."}]},
            }
        )
    )
    assert await handlers.stop({**payload, "transcript_path": str(transcript)}) is None
    assert (
        await handlers.stop(
            {**payload, "stop_hook_active": True, "transcript_path": str(transcript)}
        )
        is None
    )

    conversations = await services.conversations.list(space="project:surreal-mem")
    assert len(conversations) == 1
    view = await services.conversations.get(conversations[0].id)
    assert [m.role.value for m in view.messages] == ["user", "user", "assistant"]
    assert view.conversation.external_id == "claude-code:abc"
