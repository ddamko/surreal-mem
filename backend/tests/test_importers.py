import json
from typing import TYPE_CHECKING, Any

import httpx

from surrealmem.bootstrap.services import build_services
from surrealmem.curation.adapters.hindsight.client import HindsightClient
from surrealmem.curation.adapters.hindsight.importer import (
    HindsightImporter,
    parse_transcript,
    session_tag,
)
from tests.fakes import FakeEmbedder

if TYPE_CHECKING:
    from surrealmem.shared.infrastructure.surreal.connection import SurrealConnection

DOCS = [{"id": "doc1", "created_at": "2026-08-18T23:03:03+00:00", "tags": ["session:s1"]}]
DOC1 = {
    "id": "doc1",
    "created_at": "2026-08-18T23:03:03+00:00",
    "original_text": json.dumps(
        [
            [
                {"role": "user", "content": "User: Hi, I'm Derek and I use Nushell."},
                {"role": "assistant", "content": [{"type": "text", "text": "Noted."}]},
            ]
        ]
    ),
    "document_metadata": {"platform": "telegram", "session_id": "s1"},
    "tags": ["session:s1"],
}
MEMORIES = [
    {
        "id": "m1",
        "text": "Derek works at WWS Sires.",
        "fact_type": "world",
        "state": "valid",
        "tags": ["session:s1"],
        "mentioned_at": "2026-08-19T00:00:00+00:00",
        "entities": "Derek, WWS Sires",
        "document_id": "doc1",
    },
    {
        "id": "m2",
        "text": "Agent created a journal entry.",
        "fact_type": "experience",
        "state": "valid",
        "tags": ["session:s2"],
        "mentioned_at": "2026-08-20T00:00:00+00:00",
        "entities": "",
        "document_id": None,
    },
    {
        "id": "m3",
        "text": "stale",
        "fact_type": "world",
        "state": "invalidated",
        "tags": ["session:s2"],
        "mentioned_at": "2026-08-21T00:00:00+00:00",
        "entities": "",
    },
]


def _transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        offset = int(request.url.params.get("offset", 0))
        if path.endswith("/documents"):
            return httpx.Response(200, json={"items": DOCS if offset == 0 else [], "total": 1})
        if path.endswith("/documents/doc1"):
            return httpx.Response(200, json=DOC1)
        if path.endswith("/memories/list"):
            return httpx.Response(200, json={"items": MEMORIES if offset == 0 else [], "total": 3})
        if path.endswith("/banks"):
            return httpx.Response(200, json=[{"bank_id": "hermes"}])
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_transcript_and_tags() -> None:
    messages = parse_transcript(DOC1["original_text"])  # type: ignore[arg-type]
    assert [(m.role, m.content) for m in messages] == [
        ("user", "Hi, I'm Derek and I use Nushell."),
        ("assistant", "Noted."),
    ]
    assert parse_transcript("plain text")[0].content == "plain text"
    assert parse_transcript("") == []
    assert session_tag(["x", "session:abc"]) == "abc" and session_tag(None) is None


async def test_hindsight_import_is_idempotent_and_queues_extraction(
    migrated_db: SurrealConnection,
) -> None:
    services = build_services(migrated_db, embedder=FakeEmbedder())
    client = HindsightClient(base_url="http://hindsight")
    client._client = httpx.AsyncClient(transport=_transport(), base_url="http://hindsight")  # pyright: ignore[reportPrivateUsage]
    importer = HindsightImporter(client, services.curation.import_sink)

    assert await client.banks() == ["hermes"]
    report = await importer.run("hermes", space="personal")
    assert (report.conversations, report.messages, report.skipped) == (3, 4, 0)

    conversations = await services.conversations.list(space="personal")
    by_external = {c.external_id: c for c in conversations}
    assert set(by_external) == {
        "hindsight:hermes:doc:doc1",
        "hindsight:hermes:session:s1",
        "hindsight:hermes:session:s2",
    }
    doc = await services.conversations.get(by_external["hindsight:hermes:doc:doc1"].id)
    assert [m.role.value for m in doc.messages] == ["user", "assistant"]
    assert doc.conversation.metadata["platform"] == "telegram"
    session = await services.conversations.get(by_external["hindsight:hermes:session:s1"].id)
    assert session.messages[0].metadata["entities"] == ["Derek", "WWS Sires"]
    assert session.messages[0].metadata["fact_type"] == "world"
    counts = await services.extraction.job_store.counts()
    assert counts == {"queued": 4}

    again = await importer.run("hermes", space="personal")
    assert again.conversations == 0 and again.skipped == 3
    assert await services.extraction.job_store.counts() == {"queued": 4}


async def test_synthetic_seed(migrated_db: SurrealConnection) -> None:
    services = build_services(migrated_db, embedder=FakeEmbedder())
    report = await services.curation.synthetic.run(space="demo", count=3, extract=False)
    assert (report.conversations, report.messages) == (3, 24)
    conversations = await services.conversations.list(space="demo")
    assert len(conversations) == 3
    first = await services.conversations.get(conversations[-1].id)
    assert "Quick intro:" in first.messages[0].content
    assert await services.extraction.job_store.counts() == {}
    repeat = await services.curation.synthetic.run(space="demo", count=3, extract=False)
    assert repeat.skipped == 3
    generated: list[Any] = services.curation.synthetic.conversations(2)
    assert (
        generated[0].messages[0].content
        == services.curation.synthetic.conversations(2)[0].messages[0].content
    )
