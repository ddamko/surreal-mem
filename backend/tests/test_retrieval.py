from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from surrealmem.bootstrap.services import build_services
from surrealmem.conversations.domain import NewConversation, NewMessage, Role
from surrealmem.knowledge.domain import BaseType, NewEntity, NewFact, NewRelationship
from surrealmem.retrieval.adapters.surreal.reader import SurrealMemoryReader
from surrealmem.retrieval.application import Retriever, estimate_tokens
from surrealmem.retrieval.domain import MemoryType, RetrievalQuery
from surrealmem.shared.infrastructure.inference.embedder import EmbeddingError
from tests.fakes import FakeEmbedder

if TYPE_CHECKING:
    from collections.abc import Sequence

    from surrealmem.shared.infrastructure.surreal.connection import SurrealConnection


async def _seed(db: SurrealConnection, embedder: FakeEmbedder) -> dict[str, str]:
    services = build_services(db, embedder=embedder)
    k = services.knowledge
    derek, _ = await k.upsert_entity(
        NewEntity(name="Derek Damko", base_type=BaseType.PERSON, aliases=["Derek"], space="work")
    )
    wws, _ = await k.upsert_entity(
        NewEntity(name="WWS Sires", base_type=BaseType.ORGANIZATION, space="work")
    )
    denver, _ = await k.upsert_entity(
        NewEntity(name="Denver", base_type=BaseType.LOCATION, space="personal")
    )
    nu, _ = await k.upsert_entity(
        NewEntity(name="Nushell", base_type=BaseType.OBJECT, subtype="shell", space="work")
    )
    await k.add_relationship(
        NewRelationship(source_id=derek.id, target_id=wws.id, kind="WORKS_AT", space="work")
    )
    await k.add_fact(
        NewFact(
            statement="Derek Damko works at WWS Sires as a software engineer.",
            space="work",
            subject_id=derek.id,
            kind="WORKS_AT",
            object_id=wws.id,
            recorded_at=datetime(2026, 9, 1, tzinfo=UTC),
        )
    )
    await k.add_fact(
        NewFact(
            statement="Derek lives in Denver.",
            space="personal",
            subject_id=derek.id,
            kind="LIVES_IN",
            object_id=denver.id,
            recorded_at=datetime(2026, 9, 15, tzinfo=UTC),
        )
    )
    await k.add_fact(
        NewFact(
            statement="Derek prefers Nushell as his shell.",
            space="work",
            subject_id=derek.id,
            kind="PREFERS",
            object_id=nu.id,
            category="shell",
        )
    )
    await k.add_fact(
        NewFact(
            statement="The API listens on port 8790.",
            space="work",
            subject_id=nu.id,
            kind="HAS_ATTRIBUTE",
            object_literal="8790",
        )
    )
    conversation = await services.conversations.start(NewConversation(space="work", agent_id="t"))
    msg = await services.conversations.append(
        conversation.id,
        NewMessage(role=Role.USER, content="Remember that Derek works at WWS Sires."),
    )
    return {
        "derek": derek.id,
        "wws": wws.id,
        "denver": denver.id,
        "nu": nu.id,
        "conversation": conversation.id,
        "message": msg.id,
    }


async def test_hybrid_search_fuses_lexical_and_vector(migrated_db: SurrealConnection) -> None:
    embedder = FakeEmbedder()
    ids = await _seed(migrated_db, embedder)
    retriever = Retriever(SurrealMemoryReader(migrated_db), embedder)

    result = await retriever.search(
        RetrievalQuery(text="where does derek work", space="work", limit=10)
    )
    texts = [i.text for i in result.items]
    assert any("works at WWS Sires" in t for t in texts)
    top = result.items[0]
    assert "lexical" in top.via or "graph" in top.via
    assert 0 < top.score.final <= 1.0
    # Entity linking found Derek by name and expanded to his employer.
    assert next(linked.name for linked in result.graph.linked) == "Derek Damko"
    assert {e["name"] for e in result.graph.entities} >= {"Derek Damko", "WWS Sires"}
    assert any(r["kind"] == "WORKS_AT" for r in result.graph.relationships)
    # Space scoping: the personal fact is not visible from the work space...
    assert not any("Denver" in t for t in texts)
    # ...unless asked for explicitly.
    wide = await retriever.search(
        RetrievalQuery(text="where does derek live", space="work", extra_spaces=["personal"])
    )
    assert any("Denver" in i.text for i in wide.items)
    assert ids["derek"] in {e["id"] for e in wide.graph.entities}


async def test_vector_only_leg_reaches_exact_statement(migrated_db: SurrealConnection) -> None:
    embedder = FakeEmbedder()
    await _seed(migrated_db, embedder)
    retriever = Retriever(SurrealMemoryReader(migrated_db), embedder)
    # FakeEmbedder is hash based: the exact statement text embeds identically to the stored fact.
    result = await retriever.search(
        RetrievalQuery(
            text="The API listens on port 8790.",
            space="work",
            lexical=False,
            graph=False,
            memory_types=[MemoryType.FACT],
        )
    )
    assert result.items[0].text == "The API listens on port 8790."
    assert result.items[0].score.vector_similarity is not None
    assert result.items[0].score.vector_similarity > 0.99
    assert result.items[0].via == ["vector"]


async def test_context_pack_respects_budget_and_touches_facts(
    migrated_db: SurrealConnection,
) -> None:
    embedder = FakeEmbedder()
    ids = await _seed(migrated_db, embedder)
    reader = SurrealMemoryReader(migrated_db)
    retriever = Retriever(reader, embedder)

    pack = await retriever.context(
        RetrievalQuery(text="derek shell preference and employer", space="work", token_budget=400)
    )
    assert pack.tokens_used <= 400
    assert [p.record["kind"] for p in pack.preferences] == ["PREFERS"]
    assert any("WWS Sires" in f.text for f in pack.facts)
    assert "## Memory context" in pack.markdown
    assert "### Preferences" in pack.markdown
    assert "WORKS_AT" in pack.markdown
    assert pack.timings_ms["total"] >= 0

    services = build_services(migrated_db, embedder=embedder)
    for n in range(12):
        await services.knowledge.add_fact(
            NewFact(
                statement=f"Derek attended planning meeting number {n} about the memory dashboard.",
                space="work",
                subject_id=ids["derek"],
                kind="ATTENDED",
                object_literal=f"meeting-{n}",
            )
        )
    tiny = await retriever.context(
        RetrievalQuery(text="derek meeting dashboard", space="work", token_budget=100)
    )
    assert tiny.tokens_used <= 100
    assert tiny.dropped >= 1

    from surrealmem.shared.infrastructure.surreal.connection import run_one

    rows = await run_one(migrated_db, "SELECT access_count FROM fact WHERE kind = 'PREFERS'")
    assert rows[0]["access_count"] >= 1
    assert ids["nu"]


async def test_messages_and_summaries_are_searchable(migrated_db: SurrealConnection) -> None:
    embedder = FakeEmbedder()
    ids = await _seed(migrated_db, embedder)
    retriever = Retriever(SurrealMemoryReader(migrated_db), embedder)
    result = await retriever.search(
        RetrievalQuery(
            text="remember WWS", space="work", memory_types=[MemoryType.MESSAGE], graph=False
        )
    )
    assert result.items and result.items[0].id == ids["message"]
    assert result.items[0].text.startswith("[user]")


def test_estimate_tokens() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("a" * 400) == 100


class _BrokenEmbedder(FakeEmbedder):
    """Embeds documents fine (so seeding works) but fails every query embedding."""

    def __init__(self) -> None:
        super().__init__()
        self.query_calls = 0

    async def embed_queries(self, texts: Sequence[str]) -> list[list[float]]:
        self.query_calls += 1
        raise EmbeddingError("ConnectTimeout (http://embed:8082/v1)")


async def test_embedding_outage_degrades_to_lexical_with_warning(
    migrated_db: SurrealConnection,
) -> None:
    embedder = _BrokenEmbedder()
    await _seed(migrated_db, embedder)
    retriever = Retriever(SurrealMemoryReader(migrated_db), embedder)
    result = await retriever.search(
        RetrievalQuery(text="port 8790", space="work", graph=False, memory_types=[MemoryType.FACT])
    )
    assert result.items, "lexical leg should still find the fact"
    assert all(i.via == ["lexical"] for i in result.items)
    assert result.warnings and "embedding service unavailable" in result.warnings[0]
    pack = await retriever.context(
        RetrievalQuery(text="port 8790", space="work", graph=False, memory_types=[MemoryType.FACT])
    )
    # The second call inside the backoff window does not touch the embedder at all.
    assert embedder.query_calls == 1
    assert pack.warnings and "retrying in" in pack.warnings[0]


async def test_embedding_outage_on_vector_only_query_raises(
    migrated_db: SurrealConnection,
) -> None:
    embedder = _BrokenEmbedder()
    await _seed(migrated_db, embedder)
    retriever = Retriever(SurrealMemoryReader(migrated_db), embedder)
    with pytest.raises(EmbeddingError):
        await retriever.search(
            RetrievalQuery(text="port 8790", space="work", lexical=False, graph=False)
        )
