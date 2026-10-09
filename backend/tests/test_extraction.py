from datetime import UTC, datetime
from typing import Any

import pytest

from surrealmem.bootstrap.services import build_services
from surrealmem.conversations.domain import ExtractionStatus, NewConversation, NewMessage, Role
from surrealmem.extraction.application import backoff_seconds, canonical_base_type, parse_date
from surrealmem.extraction.domain import JobStatus
from surrealmem.knowledge.domain import BaseType, FactStatus
from surrealmem.shared.infrastructure.surreal.connection import SurrealConnection, run_one
from tests.fakes import FakeEmbedder, FakeExtractor

CANNED: dict[str, Any] = {
    "Derek": {
        "entities": [
            {
                "name": "Derek Damko",
                "base_type": "person",
                "aliases": ["Derek"],
                "description": "Software engineer",
            },
            {"name": "WWS", "base_type": "Company", "subtype": "employer"},
            {"name": "SurrealDB", "base_type": "concept", "subtype": "Database"},
            {"name": "Nushell", "base_type": "object", "subtype": "shell"},
            {"name": "Mystery", "base_type": "alien"},
        ],
        "relations": [
            {"source": "Derek", "kind": "works at", "target": "WWS"},
            {"source": "Derek Damko", "kind": "USES", "target": "SurrealDB", "confidence": 0.9},
            {"source": "Derek", "kind": "KNOWS", "target": "Nobody"},
        ],
        "facts": [
            {
                "statement": "Derek Damko works at WWS.",
                "subject": "Derek",
                "kind": "WORKS_AT",
                "object": "WWS",
            },
            {
                "statement": "Derek prefers Nushell as his shell.",
                "subject": "Derek Damko",
                "kind": "PREFERS",
                "object": "Nushell",
                "category": "shell",
            },
            {
                "statement": "Derek started at WWS in 2019.",
                "subject": "Derek",
                "kind": "HAS_ATTRIBUTE",
                "object_literal": "2019",
                "valid_from": "2019",
            },
            {"statement": "Nobody is here.", "subject": "Nobody", "kind": "HAS_ROLE"},
        ],
    }
}


def test_helpers() -> None:
    assert canonical_base_type("Company") == "organization"
    assert canonical_base_type("CONCEPT") == "concept"
    assert canonical_base_type("alien") is None
    assert parse_date("2019") == datetime(2019, 1, 1, tzinfo=UTC)
    assert parse_date("2024-06") == datetime(2024, 6, 1, tzinfo=UTC)
    assert parse_date("2024-06-05T10:00:00Z") == datetime(2024, 6, 5, 10, tzinfo=UTC)
    assert parse_date("yesterday") is None
    assert [backoff_seconds(a) for a in (1, 2, 3, 10)] == [10, 20, 40, 900]


async def test_pipeline_end_to_end(migrated_db: SurrealConnection) -> None:
    extractor = FakeExtractor(CANNED)
    services = build_services(migrated_db, embedder=FakeEmbedder(), extractor=extractor)
    worker = services.extraction.worker
    assert worker is not None

    conversation = await services.conversations.start(
        NewConversation(space="work", agent_id="claude-code")
    )
    await services.conversations.append(
        conversation.id, NewMessage(role=Role.ASSISTANT, content="Hello! How can I help?")
    )
    message = await services.conversations.append(
        conversation.id, NewMessage(role=Role.USER, content="I'm Derek, I work at WWS.")
    )

    ran = await worker.run_once()
    assert ran == 2
    assert extractor.contexts[-1].window == [("assistant", "Hello! How can I help?")]
    assert "WORKS_AT" in extractor.contexts[-1].known_kinds

    stored = await services.conversations.repository.get_message(message.id)
    assert stored is not None and stored.extraction_status is ExtractionStatus.DONE

    jobs = await services.extraction.job_store.recent()
    done = next(j for j in jobs if j.payload.get("message_id") == message.id)
    assert done.status is JobStatus.DONE
    assert done.result["entities"] == 4
    assert done.result["relationships"] == 2
    assert done.result["facts"] == 3
    assert any("alien" in s for s in done.result["skipped"])
    assert any("Nobody" in s for s in done.result["skipped"])

    counts = await services.knowledge.entities.count_by_type()
    assert counts == {"person": 1, "organization": 1, "concept": 1, "object": 1}

    derek = await services.knowledge.entities.find_exact(BaseType.PERSON, "derek damko")
    assert derek is not None
    assert derek.spaces == ["work"]
    assert derek.description == "Software engineer"
    assert await services.knowledge.entities.find_by_alias(BaseType.PERSON, "derek") is not None

    view = await services.knowledge.get_entity(derek.id, hops=1)
    assert {r.kind for r in view.relationships} == {"WORKS_AT", "USES", "PREFERS"}
    assert {n.name for n in view.neighbors} == {"WWS", "SurrealDB", "Nushell"}
    assert {f.kind for f in view.facts} == {"WORKS_AT", "PREFERS", "HAS_ATTRIBUTE"}
    started = next(f for f in view.facts if f.kind == "HAS_ATTRIBUTE")
    assert started.valid_from == datetime(2019, 1, 1, tzinfo=UTC)
    assert started.status is FactStatus.ACTIVE

    mentioned = await services.knowledge.provenance.mentioned_in(derek.id)
    assert mentioned == [message.id]
    sources = await services.knowledge.provenance.sources_of(started.id)
    assert sources == [message.id]
    edge_sources = await run_one(
        migrated_db, "SELECT count() AS n FROM extracted_from WHERE in.kind IS NOT NONE GROUP ALL"
    )
    assert edge_sources[0]["n"] >= 2
    assert (await run_one(migrated_db, "SELECT count() AS n FROM mentions GROUP ALL"))[0]["n"] == 4


async def test_failed_jobs_retry_then_die(migrated_db: SurrealConnection) -> None:
    extractor = FakeExtractor(fail_with=RuntimeError("model down"))
    services = build_services(migrated_db, embedder=FakeEmbedder(), extractor=extractor)
    worker = services.extraction.worker
    assert worker is not None
    worker.retry_base_seconds = 0

    conversation = await services.conversations.start(NewConversation(space="work", agent_id="a"))
    message = await services.conversations.append(
        conversation.id, NewMessage(role=Role.USER, content="x")
    )

    for attempt in range(1, 4):
        assert await worker.run_once(max_jobs=1) == 1
        job = (await services.extraction.job_store.recent())[0]
        assert job.attempts == attempt
        assert job.error == "RuntimeError: model down"
        assert job.status is (JobStatus.DEAD if attempt == 3 else JobStatus.QUEUED)
    assert await worker.run_once() == 0
    stored = await services.conversations.repository.get_message(message.id)
    assert stored is not None and stored.extraction_status is ExtractionStatus.FAILED
    assert await services.extraction.job_store.counts() == {"dead": 1}


async def test_claims_respect_priority_and_expired_leases(migrated_db: SurrealConnection) -> None:
    from surrealmem.shared.application import JobRequest

    services = build_services(migrated_db)
    store = services.extraction.job_store
    low = await services.jobs.enqueue(JobRequest(kind="extract", payload={"n": 1}, priority=9))
    high = await services.jobs.enqueue(JobRequest(kind="extract", payload={"n": 2}, priority=1))
    future = await services.jobs.enqueue(
        JobRequest(kind="extract", payload={"n": 3}, scheduled_at=datetime(2999, 1, 1, tzinfo=UTC))
    )
    assert low != high != future

    first = await store.claim("w1", kinds=["extract"], lease_seconds=300)
    assert first is not None and first.id == high and first.claimed_by == "w1"
    second = await store.claim("w1", kinds=["extract"], lease_seconds=300)
    assert second is not None and second.id == low
    assert await store.claim("w1", kinds=["extract"], lease_seconds=300) is None
    assert await store.claim("w1", kinds=["reflect"], lease_seconds=300) is None

    # Expire the lease of the first job: another worker may reclaim it.
    await run_one(
        migrated_db,
        "UPDATE $id SET lease_until = time::now() - 1h",
        {"id": __import__("surrealdb").RecordID.parse(first.id.replace(":", ":", 1))},
    )
    reclaimed = await store.claim("w2", kinds=["extract"], lease_seconds=300)
    assert reclaimed is not None and reclaimed.id == high and reclaimed.attempts == 2
    await store.heartbeat(reclaimed.id, lease_seconds=600)
    finished = await store.complete(reclaimed.id, {"ok": True})
    assert finished.status is JobStatus.DONE and finished.result == {"ok": True}
    assert finished.finished_at is not None


async def test_merge_candidates_and_auto_merge(migrated_db: SurrealConnection) -> None:
    from tests.fakes import StubEmbedder, unit_vector

    close = unit_vector(1024, axis=0, tilt=0.30)  # cosine ~0.954 with axis 0
    near = unit_vector(1024, axis=0, tilt=0.55)  # cosine ~0.835 with axis 0
    embedder = StubEmbedder(
        {"Robert Smith": unit_vector(1024, axis=0), "Bob Smith": close, "Rob Smyth": near}
    )
    services = build_services(migrated_db, embedder=embedder)
    from surrealmem.knowledge.domain import MergeStatus, NewEntity

    robert, created = await services.knowledge.upsert_entity(
        NewEntity(name="Robert Smith", base_type=BaseType.PERSON)
    )
    assert created
    bob, created = await services.knowledge.upsert_entity(
        NewEntity(name="Bob Smith", base_type=BaseType.PERSON, space="personal")
    )
    assert created is False and bob.id == robert.id
    assert "Bob Smith" in bob.aliases
    assert await services.knowledge.entities.find_by_alias(BaseType.PERSON, "bob smith") is not None

    rob, created = await services.knowledge.upsert_entity(
        NewEntity(name="Rob Smyth", base_type=BaseType.PERSON)
    )
    assert created and rob.id != robert.id
    pending = await services.knowledge.candidates.list(status=MergeStatus.PENDING)
    assert len(pending) == 1
    assert {pending[0].left_id, pending[0].right_id} == {rob.id, robert.id}
    assert 0.80 <= pending[0].score < 0.92

    decided = await services.knowledge.review_candidate(pending[0].id, approve=True)
    assert decided.status is MergeStatus.APPROVED
    gone = await services.knowledge.entities.get(rob.id)
    assert gone is not None and gone.archived and gone.merged_into == robert.id
    winner = await services.knowledge.entities.get(robert.id)
    assert winner is not None and "Rob Smyth" in winner.aliases
    assert await services.knowledge.entities.find_exact(BaseType.PERSON, "rob smyth") is None
    assert (
        await services.knowledge.entities.find_by_alias(BaseType.PERSON, "rob smyth")
    ).id == robert.id  # type: ignore[union-attr]


async def test_merge_moves_edges_facts_and_mentions(migrated_db: SurrealConnection) -> None:
    from surrealmem.knowledge.domain import NewEntity, NewFact, NewRelationship

    services = build_services(migrated_db, embedder=FakeEmbedder())
    k = services.knowledge
    a, _ = await k.upsert_entity(NewEntity(name="Acme Corp", base_type=BaseType.ORGANIZATION))
    b, _ = await k.upsert_entity(
        NewEntity(name="ACME Corporation", base_type=BaseType.ORGANIZATION)
    )
    derek, _ = await k.upsert_entity(NewEntity(name="Derek", base_type=BaseType.PERSON))
    texas, _ = await k.upsert_entity(NewEntity(name="Texas", base_type=BaseType.LOCATION))
    await k.add_relationship(NewRelationship(source_id=derek.id, target_id=a.id, kind="WORKS_AT"))
    await k.add_relationship(NewRelationship(source_id=derek.id, target_id=b.id, kind="WORKS_AT"))
    await k.add_relationship(NewRelationship(source_id=b.id, target_id=texas.id, kind="LOCATED_IN"))
    fact = await k.add_fact(
        NewFact(
            statement="ACME Corporation was founded in 1990.",
            space="work",
            subject_id=b.id,
            kind="HAS_ATTRIBUTE",
            object_literal="1990",
        )
    )
    conversation = await services.conversations.start(NewConversation(space="work", agent_id="x"))
    msg = await services.conversations.append(
        conversation.id, NewMessage(role=Role.USER, content="hi")
    )
    await k.provenance.link_mention(msg.id, b.id)
    await k.provenance.link_source(fact.id, msg.id, extractor="t")

    winner = await k.merge_entities(b.id, a.id, reason="manual")
    assert winner.id == a.id
    assert "ACME Corporation" in winner.aliases

    rels = await k.relationships.for_entity(a.id)
    assert {(r.source_id, r.target_id, r.kind) for r in rels} == {
        (derek.id, a.id, "WORKS_AT"),
        (a.id, texas.id, "LOCATED_IN"),
    }
    works = next(r for r in rels if r.kind == "WORKS_AT")
    assert works.mention_count == 2
    assert await k.relationships.for_entity(b.id) == []
    moved = await k.facts.get(fact.id)
    assert moved is not None and moved.subject_id == a.id
    assert await k.provenance.mentioned_in(a.id) == [msg.id]
    same_as = await run_one(
        migrated_db, "SELECT <string>in AS loser, <string>out AS winner FROM same_as"
    )
    assert same_as == [{"loser": b.id, "winner": a.id}]
    with pytest.raises(ValueError, match="itself"):
        await k.merge_entities(a.id, a.id)


async def test_worker_loop_survives_claim_errors() -> None:
    import asyncio

    from surrealmem.extraction.application import Worker
    from surrealmem.extraction.domain import Job, JobStatus

    calls = {"n": 0}

    class FlakyStore:
        async def claim(self, worker_id: str, *, kinds: Any, lease_seconds: int) -> Job | None:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("Transaction conflict")
            if calls["n"] == 2:
                return Job(
                    id="job:1",
                    kind="noop",
                    status=JobStatus.RUNNING,
                    scheduled_at=datetime.now(UTC),
                    created_at=datetime.now(UTC),
                )
            return None

        async def heartbeat(self, job_id: str, *, lease_seconds: int) -> None: ...

        async def complete(self, job_id: str, result: dict[str, Any]) -> Job:
            return Job(
                id=job_id,
                kind="noop",
                status=JobStatus.DONE,
                scheduled_at=datetime.now(UTC),
                created_at=datetime.now(UTC),
            )

        async def fail(self, job_id: str, error: str, *, retry_in_seconds: int) -> Job:
            raise AssertionError("should not fail")

        async def get(self, job_id: str) -> Job | None:
            return None

        async def counts(self) -> dict[str, int]:
            return {}

        async def recent(self, *, limit: int = 50, status: str | None = None) -> list[Job]:
            return []

        async def requeue(self, *, status: str = "dead", kind: str | None = None) -> int:
            return 0

    async def noop(job: Job) -> dict[str, Any]:
        return {"ok": True}

    worker = Worker(
        jobs=FlakyStore(), handlers={"noop": noop}, worker_id="w", poll_seconds=0.01, concurrency=2
    )
    stop = asyncio.Event()
    task = asyncio.create_task(worker.run_forever(stop))
    await asyncio.sleep(0.3)
    stop.set()
    await task
    assert worker.processed == 1
    assert calls["n"] >= 3
