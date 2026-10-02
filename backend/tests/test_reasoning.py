import pytest

from surrealmem.knowledge.adapters.surreal.entities import SurrealEntityRepository
from surrealmem.knowledge.domain import BaseType, NewEntity
from surrealmem.reasoning.adapters.surreal.repository import SurrealTraceRepository
from surrealmem.reasoning.application import (
    CompleteTrace,
    GetTrace,
    ListTraces,
    RecordStep,
    StartTrace,
)
from surrealmem.reasoning.domain import NewStep, NewToolCall, NewTrace, TraceNotFound, TraceStatus
from surrealmem.shared.infrastructure.surreal.connection import SurrealConnection, run_one
from tests.fakes import FakeEmbedder


async def test_trace_lifecycle(migrated_db: SurrealConnection) -> None:
    traces = SurrealTraceRepository(migrated_db)
    entities = SurrealEntityRepository(migrated_db)
    repo_entity = await entities.create(
        NewEntity(name="surreal-mem", base_type=BaseType.OBJECT), embedding=None, model=None
    )
    embedder = FakeEmbedder()

    trace = await StartTrace(traces, embedder)(
        NewTrace(space="work", agent_id="claude-code", task="Fix the failing merge test")
    )
    assert trace.status is TraceStatus.RUNNING and trace.step_count == 0
    assert embedder.calls == [["Fix the failing merge test"]]

    record = RecordStep(traces)
    s1 = await record(
        trace.id,
        NewStep(
            thought="Look at the failing assertion",
            action="read test output",
            tool_calls=[
                NewToolCall(
                    tool="Bash",
                    arguments={"cmd": "pytest -k merge"},
                    success=True,
                    duration_ms=1200,
                )
            ],
            touched_entity_ids=[repo_entity.id],
            touched_how="read",
        ),
    )
    s2 = await record(
        trace.id,
        NewStep(thought="Patch the script", action="edit merging.py", observation="tests green"),
    )
    assert (s1.seq, s2.seq) == (1, 2)
    assert s1.tool_calls[0].tool == "Bash"
    assert s1.tool_calls[0].arguments == {"cmd": "pytest -k merge"}
    assert s1.touched_entity_ids == [repo_entity.id]

    done = await CompleteTrace(traces)(trace.id, outcome="merge tests pass", success=True)
    assert done.status is TraceStatus.COMPLETED and done.step_count == 2 and done.completed_at

    view = await GetTrace(traces)(trace.id)
    assert [s.action for s in view.steps] == ["read test output", "edit merging.py"]
    assert view.steps[0].tool_calls[0].duration_ms == 1200

    with pytest.raises(ValueError, match="completed"):
        await record(trace.id, NewStep(thought="too late"))

    listed = await ListTraces(traces)(space="work", status=TraceStatus.COMPLETED)
    assert [t.id for t in listed] == [trace.id]
    tools = await run_one(migrated_db, "SELECT name, call_count FROM tool")
    assert tools == [{"name": "Bash", "call_count": 1}]
    assert await traces.count_by_status() == {"completed": 1}


async def test_trace_links_to_message_and_failures(migrated_db: SurrealConnection) -> None:
    from surrealmem.bootstrap.services import build_services
    from surrealmem.conversations.domain import NewConversation, NewMessage, Role

    services = build_services(migrated_db)
    conversation = await services.conversations.start(NewConversation(space="work", agent_id="a"))
    message = await services.conversations.append(
        conversation.id, NewMessage(role=Role.USER, content="do it")
    )
    traces = SurrealTraceRepository(migrated_db)
    trace = await StartTrace(traces)(
        NewTrace(
            space="work",
            agent_id="a",
            task="do it",
            conversation_id=conversation.id,
            message_id=message.id,
        )
    )
    assert trace.conversation_id == conversation.id
    initiated = await run_one(migrated_db, "SELECT <string>out AS m FROM initiated_by")
    assert initiated == [{"m": message.id}]
    failed = await CompleteTrace(traces)(trace.id, outcome="gave up", failed=True)
    assert failed.status is TraceStatus.FAILED
    with pytest.raises(TraceNotFound):
        await GetTrace(traces)("trace:missing")
