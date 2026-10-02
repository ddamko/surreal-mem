from datetime import UTC, datetime

import pytest

from surrealmem.conversations.adapters.surreal.repository import SurrealConversationRepository
from surrealmem.conversations.application import (
    AppendMessage,
    CloseConversation,
    GetConversation,
    ListConversations,
    StartConversation,
)
from surrealmem.conversations.domain import (
    ConversationNotFound,
    ConversationStatus,
    ExtractionStatus,
    NewConversation,
    NewMessage,
    Role,
)
from surrealmem.shared.domain import InvalidSpace
from surrealmem.shared.infrastructure.surreal.connection import SurrealConnection, run_one
from surrealmem.shared.infrastructure.surreal.jobs import SurrealJobQueue
from tests.fakes import RecordingJobQueue


@pytest.fixture
def repo(migrated_db: SurrealConnection) -> SurrealConversationRepository:
    return SurrealConversationRepository(migrated_db)


async def test_start_conversation_registers_space_and_agent(
    repo: SurrealConversationRepository, migrated_db: SurrealConnection
) -> None:
    conversation = await StartConversation(repo)(
        NewConversation(space="project:surreal-mem", agent_id="claude-code", title="scaffold")
    )
    assert conversation.id.startswith("conversation:")
    assert conversation.status is ConversationStatus.OPEN
    assert conversation.message_count == 0

    spaces = await run_one(migrated_db, "SELECT name FROM space")
    agents = await run_one(migrated_db, "SELECT name FROM agent")
    assert spaces == [{"name": "project:surreal-mem"}]
    assert agents == [{"name": "claude-code"}]


async def test_start_conversation_rejects_bad_space(repo: SurrealConversationRepository) -> None:
    with pytest.raises(InvalidSpace):
        await StartConversation(repo)(NewConversation(space="Not Valid", agent_id="a"))


async def test_external_id_is_idempotent(repo: SurrealConversationRepository) -> None:
    start = StartConversation(repo)
    first = await start(NewConversation(space="personal", agent_id="hermes", external_id="tg-1"))
    second = await start(NewConversation(space="personal", agent_id="hermes", external_id="tg-1"))
    assert first.id == second.id


async def test_append_messages_sequences_and_enqueues_extraction(
    repo: SurrealConversationRepository,
) -> None:
    conversation = await StartConversation(repo)(
        NewConversation(space="personal", agent_id="hermes")
    )
    queue = RecordingJobQueue()
    append = AppendMessage(repo, queue)

    m1 = await append(conversation.id, NewMessage(role=Role.USER, content="Hi, I'm Derek."))
    m2 = await append(conversation.id, NewMessage(role=Role.ASSISTANT, content="Hello Derek."))
    m3 = await append(conversation.id, NewMessage(role=Role.SYSTEM, content="tool noise"))

    assert (m1.seq, m2.seq, m3.seq) == (1, 2, 3)
    assert m1.extraction_status is ExtractionStatus.QUEUED
    assert m3.extraction_status is ExtractionStatus.SKIPPED
    assert [r.payload["message_id"] for r in queue.requests] == [m1.id, m2.id]
    assert queue.requests[0].dedupe_key == f"extract:{m1.id}"
    assert queue.requests[0].payload["space"] == "personal"

    view = await GetConversation(repo)(conversation.id)
    assert view.conversation.message_count == 3
    assert view.conversation.last_message_at is not None
    assert [m.content for m in view.messages] == ["Hi, I'm Derek.", "Hello Derek.", "tool noise"]
    assert view.messages[0].extraction_status is ExtractionStatus.QUEUED


async def test_messages_pagination_and_explicit_timestamps(
    repo: SurrealConversationRepository,
) -> None:
    conversation = await StartConversation(repo)(
        NewConversation(space="personal", agent_id="hermes")
    )
    append = AppendMessage(repo, RecordingJobQueue(), extract=False)
    when = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    for i in range(5):
        await append(conversation.id, NewMessage(role=Role.USER, content=f"m{i}", created_at=when))

    page = await repo.messages(conversation.id, limit=2, before_seq=4)
    assert [m.seq for m in page] == [2, 3]
    assert page[0].created_at == when


async def test_append_to_missing_conversation_raises(repo: SurrealConversationRepository) -> None:
    with pytest.raises(ConversationNotFound):
        await AppendMessage(repo, RecordingJobQueue())(
            "conversation:nope", NewMessage(role=Role.USER, content="x")
        )


async def test_list_and_close(repo: SurrealConversationRepository) -> None:
    start = StartConversation(repo)
    a = await start(NewConversation(space="work", agent_id="claude-code"))
    await start(NewConversation(space="personal", agent_id="hermes"))
    listed = await ListConversations(repo)(space="work")
    assert [c.id for c in listed] == [a.id]
    await CloseConversation(repo)(a.id)
    closed = await repo.get(a.id)
    assert closed is not None and closed.status is ConversationStatus.CLOSED


async def test_surreal_job_queue_dedupes(migrated_db: SurrealConnection) -> None:
    from surrealmem.shared.application import JobRequest

    queue = SurrealJobQueue(migrated_db)
    first = await queue.enqueue(JobRequest(kind="extract", payload={"a": 1}, dedupe_key="k"))
    second = await queue.enqueue(JobRequest(kind="extract", payload={"a": 2}, dedupe_key="k"))
    third = await queue.enqueue(JobRequest(kind="reflect", payload={"nested": {"x": [1, 2]}}))
    assert first == second
    assert third != first
    rows = await run_one(migrated_db, "SELECT kind, status, payload FROM job ORDER BY kind")
    assert [r["kind"] for r in rows] == ["extract", "reflect"]
    assert rows[1]["payload"] == {"nested": {"x": [1, 2]}}
