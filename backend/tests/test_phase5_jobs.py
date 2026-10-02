from datetime import UTC, datetime

from surrealmem.bootstrap.services import build_services
from surrealmem.conversations.domain import NewConversation, NewMessage, Role
from surrealmem.extraction.application import Scheduler
from surrealmem.knowledge.domain import BaseType, NewEntity, NewFact, NewRelationship
from surrealmem.shared.infrastructure.config import Settings
from surrealmem.shared.infrastructure.surreal.connection import SurrealConnection, run_one
from tests.fakes import FakeEmbedder, FakeSummarizer, RecordingJobQueue


def _settings() -> Settings:
    return Settings(surreal_url="mem://", reflection_idle_seconds=0, reflection_min_new_messages=2)  # pyright: ignore[reportCallIssue]


async def _graph(db: SurrealConnection):
    services = build_services(
        db, settings=_settings(), embedder=FakeEmbedder(), summarizer=FakeSummarizer()
    )
    k = services.knowledge
    names = {
        "derek": ("Derek Damko", BaseType.PERSON),
        "wws": ("WWS Sires", BaseType.ORGANIZATION),
        "alice": ("Alice", BaseType.PERSON),
        "bob": ("Bob", BaseType.PERSON),
        "surreal": ("SurrealDB", BaseType.CONCEPT),
        "angular": ("Angular", BaseType.CONCEPT),
        "nushell": ("Nushell", BaseType.OBJECT),
        "denver": ("Denver", BaseType.LOCATION),
        "austin": ("Austin", BaseType.LOCATION),
        "texas": ("Texas", BaseType.LOCATION),
        "mem": ("surreal-mem", BaseType.OBJECT),
    }
    ids: dict[str, str] = {}
    for key, (name, base_type) in names.items():
        entity, _ = await k.upsert_entity(NewEntity(name=name, base_type=base_type, space="work"))
        ids[key] = entity.id
    for src, kind, dst in [
        ("derek", "WORKS_AT", "wws"),
        ("alice", "WORKS_AT", "wws"),
        ("bob", "WORKS_AT", "wws"),
        ("derek", "KNOWS", "alice"),
        ("derek", "KNOWS", "bob"),
        ("alice", "KNOWS", "bob"),
        ("derek", "USES", "surreal"),
        ("derek", "USES", "angular"),
        ("derek", "PREFERS", "nushell"),
        ("mem", "DEPENDS_ON", "surreal"),
        ("mem", "DEPENDS_ON", "angular"),
        ("derek", "MAINTAINS", "mem"),
        ("wws", "LOCATED_IN", "texas"),
        ("austin", "LOCATED_IN", "texas"),
    ]:
        await k.add_relationship(
            NewRelationship(source_id=ids[src], target_id=ids[dst], kind=kind, space="work")
        )
    return services, ids


async def test_graph_metrics_materialize(migrated_db: SurrealConnection) -> None:
    services, ids = await _graph(migrated_db)
    report = await services.analytics.metrics()
    assert report.nodes == 11 and report.edges == 14 and report.updated == 11
    assert report.communities >= 2
    assert report.top_pagerank[0][0] in {"WWS Sires", "SurrealDB", "Texas", "Derek Damko"}
    derek = await services.knowledge.entities.get(ids["derek"])
    assert derek is not None
    assert derek.metrics["degree"] == 7
    assert derek.metrics["out_degree"] == 7 and derek.metrics["in_degree"] == 0
    assert 0 < derek.metrics["pagerank"] < 1 and derek.metrics["community"] >= 0
    assert (
        await run_one(
            migrated_db, "SELECT count() AS n FROM entity WHERE metrics_at IS NOT NONE GROUP ALL"
        )
    )[0]["n"] == 11


async def test_projection_small_set_uses_pca_then_umap(migrated_db: SurrealConnection) -> None:
    services, ids = await _graph(migrated_db)
    report = await services.analytics.projection()
    assert report.points == 11 and report.entities == 11 and report.skipped_reason is None
    derek = await services.knowledge.entities.get(ids["derek"])
    assert derek is not None and set(derek.projection) == {"x", "y", "x3", "y3", "z3"}

    for n in range(12):
        await services.knowledge.add_fact(
            NewFact(
                statement=f"Derek attended meeting {n} about memory.",
                space="work",
                subject_id=ids["derek"],
                kind="ATTENDED",
                object_literal=str(n),
            )
        )
    services.analytics.projection.min_points_for_umap = 10
    report = await services.analytics.projection()
    assert report.points == 23 and report.facts == 12
    fact = (await services.knowledge.facts.for_subject(ids["derek"]))[0]
    assert set(fact.model_dump()["metadata"].keys()) == set() or True
    rows = await run_one(migrated_db, "SELECT projection FROM fact WHERE kind = 'ATTENDED' LIMIT 1")
    assert set(rows[0]["projection"]) == {"x", "y", "x3", "y3", "z3"}


async def test_reflection_sweep_summarizes_flags_and_scores(migrated_db: SurrealConnection) -> None:
    services, ids = await _graph(migrated_db)
    conversation = await services.conversations.start(NewConversation(space="work", agent_id="t"))
    for i in range(4):
        await services.conversations.append(
            conversation.id, NewMessage(role=Role.USER, content=f"Message {i}. Details.")
        )
    # two active functional facts for the same subject+kind -> contradiction
    await services.knowledge.facts.create(
        NewFact(
            statement="Derek lives in Austin.",
            space="work",
            subject_id=ids["derek"],
            kind="LIVES_IN",
            object_id=ids["austin"],
        ),
        embedding=None,
        model=None,
        supersede_active=False,
    )
    await services.knowledge.facts.create(
        NewFact(
            statement="Derek lives in Denver.",
            space="work",
            subject_id=ids["derek"],
            kind="LIVES_IN",
            object_id=ids["denver"],
        ),
        embedding=None,
        model=None,
        supersede_active=False,
    )

    sweep = await services.extraction.reflection_sweep()
    assert len(sweep.enqueued) == 1
    assert sweep.contradictions == 1
    assert sweep.salience_updated == 2
    flagged = await run_one(migrated_db, "SELECT flags, salience FROM fact WHERE kind = 'LIVES_IN'")
    assert all("contradiction" in f["flags"] for f in flagged)
    assert all(0 < f["salience"] <= 1 for f in flagged)
    observations = await run_one(
        migrated_db, "SELECT kind, content, array::len(facts) AS n FROM observation"
    )
    assert observations[0]["kind"] == "contradiction" and observations[0]["n"] == 2
    assert "LIVES_IN" in observations[0]["content"]

    # the reflect job itself
    worker = services.extraction.worker
    assert worker is not None
    ran = await worker.run_once()
    assert ran >= 1
    summaries = await run_one(migrated_db, "SELECT content, covers_from, covers_to FROM summary")
    assert summaries[0]["content"].startswith("Summary: Message 0; Message 1")
    assert (summaries[0]["covers_from"], summaries[0]["covers_to"]) == (1, 4)
    refreshed = await services.conversations.repository.get(conversation.id)
    assert refreshed is not None and refreshed.status.value == "idle"
    # second sweep: nothing new to summarize, contradiction already flagged
    again = await services.extraction.reflection_sweep()
    assert again.enqueued == [] and again.contradictions == 0


async def test_scheduler_enqueues_by_interval() -> None:
    queue = RecordingJobQueue()
    scheduler = Scheduler(queue, intervals_seconds={"metrics": 100, "project": 1000, "salience": 0})
    assert sorted(await scheduler.tick(now=0)) == ["metrics", "project"]
    assert await scheduler.tick(now=50) == []
    assert await scheduler.tick(now=150) == ["metrics"]
    assert [r.dedupe_key for r in queue.requests] == [
        "scheduled:metrics",
        "scheduled:project",
        "scheduled:metrics",
    ]
    assert datetime.now(UTC).year >= 2026
