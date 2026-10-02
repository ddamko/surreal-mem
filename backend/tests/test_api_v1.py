from typing import TYPE_CHECKING

import httpx
import pytest
from pydantic import SecretStr

from surrealmem.bootstrap.app import create_app
from surrealmem.bootstrap.container import AppContainer
from surrealmem.bootstrap.services import build_services
from surrealmem.shared.infrastructure.config import Settings
from tests.fakes import FakeEmbedder

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from surrealmem.shared.infrastructure.surreal.connection import SurrealConnection

TOKEN = "test-token"


@pytest.fixture
async def api(migrated_db: SurrealConnection) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(surreal_url="mem://", log_json=False, api_token=SecretStr(TOKEN))  # pyright: ignore[reportCallIssue]
    services = build_services(migrated_db, settings=settings, embedder=FakeEmbedder())
    container = AppContainer(settings=settings, db=migrated_db, services=services)
    app = create_app(settings=settings, container=container)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test/api/v1",
        headers={"Authorization": f"Bearer {TOKEN}"},
    ) as client:
        yield client


async def test_requires_bearer_token(api: httpx.AsyncClient) -> None:
    anonymous = await api.get("/entities", headers={"Authorization": ""})
    assert anonymous.status_code == 401
    assert anonymous.headers["WWW-Authenticate"] == "Bearer"
    assert anonymous.headers["content-type"].startswith("application/problem+json")
    wrong = await api.get("/entities", headers={"Authorization": "Bearer nope"})
    assert wrong.status_code == 401
    health = await api.get("http://test/health/live", headers={"Authorization": ""})
    assert health.status_code == 200


async def test_conversation_flow(api: httpx.AsyncClient) -> None:
    created = await api.post(
        "/conversations", json={"space": "work", "agent_id": "claude-code", "title": "api test"}
    )
    assert created.status_code == 201, created.text
    conversation = created.json()
    cid = conversation["id"]

    m1 = await api.post(
        f"/conversations/{cid}/messages", json={"role": "user", "content": "I'm Derek"}
    )
    assert m1.status_code == 201 and m1.json()["seq"] == 1
    assert m1.json()["extraction_status"] == "queued"
    m2 = await api.post(
        f"/conversations/{cid}/messages", json={"role": "assistant", "content": "Hi"}
    )
    assert m2.json()["seq"] == 2

    detail = await api.get(f"/conversations/{cid}")
    assert detail.status_code == 200
    assert detail.json()["conversation"]["message_count"] == 2
    assert [m["content"] for m in detail.json()["messages"]] == ["I'm Derek", "Hi"]

    listed = await api.get("/conversations", params={"space": "work"})
    assert [c["id"] for c in listed.json()] == [cid]

    closed = await api.post(f"/conversations/{cid}/close")
    assert closed.status_code == 204
    missing = await api.get("/conversations/conversation:nope")
    assert missing.status_code == 404
    bad_space = await api.post("/conversations", json={"space": "Bad Space", "agent_id": "x"})
    assert bad_space.status_code == 422

    jobs = await api.get("/jobs", params={"status": "queued"})
    assert len(jobs.json()) == 2
    counts = await api.get("/jobs/counts")
    assert counts.json() == {"counts": {"queued": 2}}
    waited = await api.get(
        "/jobs/wait", params={"job_id": jobs.json()[0]["id"], "timeout_seconds": 0}
    )
    assert waited.json()["settled"] is False


async def test_knowledge_flow(api: httpx.AsyncClient) -> None:
    derek = await api.post(
        "/entities",
        json={"name": "Derek Damko", "base_type": "person", "aliases": ["Derek"], "space": "work"},
    )
    assert derek.status_code == 201 and derek.json()["created"] is True
    derek_id = derek.json()["entity"]["id"]
    again = await api.post("/entities", json={"name": "derek", "base_type": "person"})
    assert again.json()["created"] is False and again.json()["entity"]["id"] == derek_id
    wws = (
        await api.post("/entities", json={"name": "WWS Sires", "base_type": "organization"})
    ).json()["entity"]

    rel = await api.post(
        "/relationships",
        json={"source_id": derek_id, "target_id": wws["id"], "kind": "works at", "space": "work"},
    )
    assert rel.status_code == 201 and rel.json()["kind"] == "WORKS_AT"
    kinds = await api.get("/relationship-kinds")
    assert any(k["kind"] == "WORKS_AT" and k["usage_count"] == 1 for k in kinds.json())

    f1 = await api.post(
        "/facts",
        json={
            "statement": "Derek lives in Austin.",
            "space": "work",
            "subject_id": derek_id,
            "kind": "LIVES_IN",
            "object_literal": "Austin",
        },
    )
    f2 = await api.post(
        "/facts",
        json={
            "statement": "Derek lives in Denver.",
            "space": "work",
            "subject_id": derek_id,
            "kind": "LIVES_IN",
            "object_literal": "Denver",
        },
    )
    assert f1.status_code == 201 and f2.status_code == 201
    history = await api.get(f"/facts/{f2.json()['id']}/history")
    assert [f["status"] for f in history.json()["facts"]] == ["invalidated", "active"]
    invalidated = await api.post(
        f"/facts/{f2.json()['id']}/invalidate", json={"reason": "moved again"}
    )
    assert invalidated.json()["status"] == "invalidated"
    active = await api.get(f"/entities/{derek_id}/facts")
    assert active.json() == []
    everything = await api.get(
        f"/entities/{derek_id}/facts", params=[("status", "active"), ("status", "invalidated")]
    )
    assert len(everything.json()) == 2

    neighborhood = await api.get(f"/entities/{derek_id}", params={"hops": 1})
    assert neighborhood.status_code == 200
    assert [n["name"] for n in neighborhood.json()["neighbors"]] == ["WWS Sires"]
    search = await api.get("/entities/search", params={"q": "derek"})
    assert search.json()[0]["entity"]["id"] == derek_id
    patched = await api.patch(f"/entities/{derek_id}", json={"description": "Engineer"})
    assert patched.json()["description"] == "Engineer"
    listed = await api.get("/entities", params={"base_type": "person"})
    assert [e["id"] for e in listed.json()] == [derek_id]

    dup = (
        await api.post("/entities", json={"name": "W.W.S. Sires", "base_type": "organization"})
    ).json()["entity"]
    merged = await api.post(f"/entities/{dup['id']}/merge", json={"winner_id": wws["id"]})
    assert merged.status_code == 200 and "W.W.S. Sires" in merged.json()["aliases"]
    candidates = await api.get("/merge-candidates")
    assert candidates.json() == []
    assert (await api.get("/facts/fact:missing")).status_code == 404


async def test_retrieval_and_traces_and_stats(api: httpx.AsyncClient) -> None:
    derek = (
        await api.post(
            "/entities", json={"name": "Derek Damko", "base_type": "person", "space": "work"}
        )
    ).json()["entity"]
    await api.post(
        "/facts",
        json={
            "statement": "Derek prefers Nushell as his shell.",
            "space": "work",
            "subject_id": derek["id"],
            "kind": "PREFERS",
            "category": "shell",
            "object_literal": "Nushell",
        },
    )
    await api.post(
        "/facts",
        json={
            "statement": "Derek works at WWS Sires.",
            "space": "work",
            "subject_id": derek["id"],
            "kind": "WORKS_AT",
            "object_literal": "WWS Sires",
        },
    )

    context = await api.post(
        "/retrieval/context",
        json={"text": "what shell does derek prefer", "space": "work", "token_budget": 500},
    )
    assert context.status_code == 200, context.text
    pack = context.json()
    assert pack["preferences"][0]["record"]["kind"] == "PREFERS"
    assert "### Preferences" in pack["markdown"]
    assert pack["tokens_used"] <= 500
    assert pack["graph"]["linked"][0]["name"] == "Derek Damko"

    search = await api.post(
        "/retrieval/search", json={"text": "derek", "space": "work", "limit": 5}
    )
    assert search.status_code == 200
    assert search.json()["items"][0]["score"]["final"] > 0

    trace = await api.post(
        "/traces", json={"space": "work", "agent_id": "claude-code", "task": "ship phase 4"}
    )
    assert trace.status_code == 201
    tid = trace.json()["id"]
    step = await api.post(
        f"/traces/{tid}/steps",
        json={
            "thought": "write routers",
            "tool_calls": [{"tool": "Edit", "arguments": {"file": "app.py"}}],
            "touched_entity_ids": [derek["id"]],
        },
    )
    assert step.status_code == 201 and step.json()["seq"] == 1
    assert step.json()["tool_calls"][0]["tool"] == "Edit"
    done = await api.post(
        f"/traces/{tid}/complete", json={"outcome": "routers shipped", "success": True}
    )
    assert done.json()["status"] == "completed"
    view = await api.get(f"/traces/{tid}")
    assert len(view.json()["steps"]) == 1
    listed = await api.get("/traces", params={"status": "completed"})
    assert [t["id"] for t in listed.json()] == [tid]

    overview = await api.get("/stats/overview")
    assert overview.status_code == 200
    body = overview.json()
    assert body["tables"]["entity"] == 1
    assert body["tables"]["fact"] == 2
    assert body["entities_by_type"] == {"person": 1}
    assert body["spaces"] == []
    assert any(k["kind"] == "WORKS_AT" for k in body["relationship_kinds"]) is False

    schema = await api.get("http://test/openapi.json", headers={"Authorization": ""})
    assert schema.status_code == 200
    paths = schema.json()["paths"]
    assert "/api/v1/retrieval/context" in paths and "/api/v1/entities/{entity_id}" in paths
