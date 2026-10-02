from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from surrealmem.knowledge.adapters.surreal.entities import SurrealEntityRepository
from surrealmem.knowledge.adapters.surreal.facts import SurrealFactRepository
from surrealmem.knowledge.adapters.surreal.relationships import SurrealRelationshipRepository
from surrealmem.knowledge.application import (
    AddFact,
    AddRelationship,
    GetEntity,
    InvalidateFact,
    SearchEntities,
    UpsertEntity,
)
from surrealmem.knowledge.domain import (
    BaseType,
    EntityNotFound,
    EntityPatch,
    FactStatus,
    NewEntity,
    NewFact,
    NewRelationship,
    normalize_kind,
)
from tests.fakes import FakeEmbedder

if TYPE_CHECKING:
    from surrealmem.shared.infrastructure.surreal.connection import SurrealConnection


class Graph:
    def __init__(self, db: SurrealConnection) -> None:
        self.entities = SurrealEntityRepository(db)
        self.relationships = SurrealRelationshipRepository(db)
        self.facts = SurrealFactRepository(db)
        self.embedder = FakeEmbedder()
        self.upsert = UpsertEntity(self.entities, self.embedder)
        self.relate = AddRelationship(self.relationships, self.entities)
        self.add_fact = AddFact(self.facts, self.entities, self.relationships, self.embedder)
        self.get = GetEntity(self.entities, self.relationships, self.facts)
        self.search = SearchEntities(self.entities, self.embedder)


@pytest.fixture
def graph(migrated_db: SurrealConnection) -> Graph:
    return Graph(migrated_db)


def test_normalize_kind() -> None:
    assert normalize_kind("works at") == "WORKS_AT"
    assert normalize_kind(" Reports-To ") == "REPORTS_TO"
    with pytest.raises(ValueError, match="relationship kind"):
        normalize_kind("###")


async def test_upsert_entity_resolves_exact_and_alias(graph: Graph) -> None:
    derek, created = await graph.upsert(
        NewEntity(
            name="Derek Damko", base_type=BaseType.PERSON, space="personal", aliases=["Derek"]
        )
    )
    assert created is True
    assert derek.name_key == "derek damko"
    assert derek.mention_count == 1
    assert derek.embedding_model == "fake-embedder"

    again, created = await graph.upsert(
        NewEntity(
            name="  derek   DAMKO ",
            base_type=BaseType.PERSON,
            space="work",
            description="Software engineer at WWS",
        )
    )
    assert created is False
    assert again.id == derek.id
    assert again.mention_count == 2
    assert sorted(again.spaces) == ["personal", "work"]
    assert again.description == "Software engineer at WWS"

    via_alias, created = await graph.upsert(NewEntity(name="Derek", base_type=BaseType.PERSON))
    assert created is False
    assert via_alias.id == derek.id

    other_type, created = await graph.upsert(NewEntity(name="Derek", base_type=BaseType.CONCEPT))
    assert created is True
    assert other_type.id != derek.id

    assert graph.embedder.calls[0] == ["Derek Damko (person)"]


async def test_subtype_is_normalized_and_patchable(graph: Graph) -> None:
    repo, created = await graph.upsert(
        NewEntity(name="surreal-mem", base_type=BaseType.OBJECT, subtype="Git Repository")
    )
    assert created and repo.subtype == "git_repository"
    patched = await graph.entities.patch(repo.id, EntityPatch(description="Memory system"))
    assert patched.description == "Memory system"
    with pytest.raises(EntityNotFound):
        await graph.entities.patch("entity:missing", EntityPatch(description="x"))


async def test_relationships_upsert_and_flag_unknown_kinds(graph: Graph) -> None:
    derek, _ = await graph.upsert(NewEntity(name="Derek", base_type=BaseType.PERSON))
    wws, _ = await graph.upsert(NewEntity(name="WWS", base_type=BaseType.ORGANIZATION))

    rel = await graph.relate(
        NewRelationship(source_id=derek.id, target_id=wws.id, kind="works at", space="work")
    )
    assert rel.kind == "WORKS_AT"
    assert rel.proposed is False
    assert rel.mention_count == 1

    same = await graph.relate(
        NewRelationship(
            source_id=derek.id, target_id=wws.id, kind="WORKS_AT", confidence=0.4, space="personal"
        )
    )
    assert same.id == rel.id
    assert same.mention_count == 2
    assert same.confidence == 1.0
    assert sorted(same.spaces) == ["personal", "work"]

    odd = await graph.relate(
        NewRelationship(source_id=derek.id, target_id=wws.id, kind="hums near")
    )
    assert odd.kind == "HUMS_NEAR" and odd.proposed is True
    kinds = {k.kind: k for k in await graph.relationships.kinds()}
    assert kinds["HUMS_NEAR"].proposed is True
    assert kinds["WORKS_AT"].usage_count == 2

    with pytest.raises(EntityNotFound):
        await graph.relate(
            NewRelationship(source_id=derek.id, target_id="entity:ghost", kind="KNOWS")
        )


async def test_functional_facts_supersede_and_keep_history(graph: Graph) -> None:
    derek, _ = await graph.upsert(NewEntity(name="Derek", base_type=BaseType.PERSON))
    austin, _ = await graph.upsert(NewEntity(name="Austin", base_type=BaseType.LOCATION))
    denver, _ = await graph.upsert(NewEntity(name="Denver", base_type=BaseType.LOCATION))

    f1 = await graph.add_fact(
        NewFact(
            statement="Derek lives in Austin.",
            space="personal",
            subject_id=derek.id,
            kind="LIVES_IN",
            object_id=austin.id,
            valid_from=datetime(2020, 1, 1, tzinfo=UTC),
        )
    )
    f2 = await graph.add_fact(
        NewFact(
            statement="Derek lives in Denver.",
            space="personal",
            subject_id=derek.id,
            kind="LIVES_IN",
            object_id=denver.id,
            valid_from=datetime(2024, 6, 1, tzinfo=UTC),
        )
    )
    old = await graph.facts.get(f1.id)
    assert old is not None
    assert old.status is FactStatus.INVALIDATED
    assert old.superseded_by == f2.id
    assert old.valid_to == datetime(2024, 6, 1, tzinfo=UTC)
    assert f2.supersedes == f1.id
    assert f2.status is FactStatus.ACTIVE

    active = await graph.facts.for_subject(derek.id)
    assert [f.id for f in active] == [f2.id]
    history = await graph.facts.history(f2.id)
    assert [f.id for f in history] == [f1.id, f2.id]

    # The edge follows the fact: both LIVES_IN edges exist, each linked to its fact.
    edges = await graph.relationships.for_entity(derek.id, kinds=["LIVES_IN"])
    assert {e.target_id: e.fact_id for e in edges} == {austin.id: f1.id, denver.id: f2.id}


async def test_non_functional_facts_accumulate(graph: Graph) -> None:
    derek, _ = await graph.upsert(NewEntity(name="Derek", base_type=BaseType.PERSON))
    a, _ = await graph.upsert(NewEntity(name="Alice", base_type=BaseType.PERSON))
    b, _ = await graph.upsert(NewEntity(name="Bob", base_type=BaseType.PERSON))
    await graph.add_fact(
        NewFact(
            statement="Derek knows Alice.",
            space="personal",
            subject_id=derek.id,
            kind="KNOWS",
            object_id=a.id,
        )
    )
    await graph.add_fact(
        NewFact(
            statement="Derek knows Bob.",
            space="personal",
            subject_id=derek.id,
            kind="KNOWS",
            object_id=b.id,
        )
    )
    assert len(await graph.facts.for_subject(derek.id)) == 2


async def test_preferences_supersede_within_category(graph: Graph) -> None:
    derek, _ = await graph.upsert(NewEntity(name="Derek", base_type=BaseType.PERSON))
    p1 = await graph.add_fact(
        NewFact(
            statement="Derek prefers tabs.",
            space="work",
            subject_id=derek.id,
            kind="PREFERS",
            category="indentation",
            object_literal="tabs",
        )
    )
    p2 = await graph.add_fact(
        NewFact(
            statement="Derek prefers spaces.",
            space="work",
            subject_id=derek.id,
            kind="PREFERS",
            category="indentation",
            object_literal="spaces",
        )
    )
    other = await graph.add_fact(
        NewFact(
            statement="Derek prefers Nushell.",
            space="work",
            subject_id=derek.id,
            kind="PREFERS",
            category="shell",
            object_literal="nushell",
        )
    )
    active = {f.id for f in await graph.facts.for_subject(derek.id)}
    assert active == {p2.id, other.id}
    assert (await graph.facts.get(p1.id)).status is FactStatus.INVALIDATED  # type: ignore[union-attr]
    assert p2.is_preference


async def test_invalidate_fact(graph: Graph) -> None:
    derek, _ = await graph.upsert(NewEntity(name="Derek", base_type=BaseType.PERSON))
    fact = await graph.add_fact(
        NewFact(
            statement="Derek's API listens on port 8787.",
            space="work",
            subject_id=derek.id,
            kind="HAS_ATTRIBUTE",
            object_literal="8787",
        )
    )
    gone = await InvalidateFact(graph.facts)(fact.id, reason="port changed")
    assert gone.status is FactStatus.INVALIDATED
    assert gone.metadata["invalidation_reason"] == "port changed"
    assert gone.invalidated_at is not None


async def test_get_entity_neighborhood_with_hops(graph: Graph) -> None:
    derek, _ = await graph.upsert(NewEntity(name="Derek", base_type=BaseType.PERSON))
    wws, _ = await graph.upsert(NewEntity(name="WWS", base_type=BaseType.ORGANIZATION))
    texas, _ = await graph.upsert(NewEntity(name="Texas", base_type=BaseType.LOCATION))
    await graph.relate(NewRelationship(source_id=derek.id, target_id=wws.id, kind="WORKS_AT"))
    await graph.relate(NewRelationship(source_id=wws.id, target_id=texas.id, kind="LOCATED_IN"))
    await graph.add_fact(
        NewFact(
            statement="Derek is an engineer.",
            space="work",
            subject_id=derek.id,
            kind="HAS_ROLE",
            object_literal="engineer",
        )
    )

    one = await graph.get(derek.id, hops=1)
    assert {n.id for n in one.neighbors} == {wws.id}
    assert {r.kind for r in one.relationships} == {"WORKS_AT"}
    assert [f.kind for f in one.facts] == ["HAS_ROLE"]

    two = await graph.get(derek.id, hops=2)
    assert {n.id for n in two.neighbors} == {wws.id, texas.id}
    assert {r.kind for r in two.relationships} == {"WORKS_AT", "LOCATED_IN"}


async def test_search_entities_lexical_and_vector(graph: Graph) -> None:
    for name in ["Derek Damko", "Darren Smith", "SurrealDB", "Angular"]:
        await graph.upsert(
            NewEntity(name=name, base_type=BaseType.CONCEPT if name[0] in "SA" else BaseType.PERSON)
        )
    # The english analyzer splits camel case, so "SurrealDB" is indexed as "surreal" + "db".
    lexical = await graph.entities.search_text("surreal")
    assert [s.entity.name for s in lexical] == ["SurrealDB"]
    assert [s.entity.name for s in await graph.entities.search_text("SurrealDB")] == ["SurrealDB"]

    vec = (await graph.embedder.embed(["Angular (concept)"]))[0]
    nearest = await graph.entities.search_vector(vec, limit=1)
    assert nearest[0].entity.name == "Angular"
    assert nearest[0].score > 0.99

    fused = await graph.search("Angular", limit=3)
    assert fused[0].entity.name == "Angular"

    typed = await graph.entities.search_text("derek", base_type=BaseType.PERSON)
    assert [s.entity.name for s in typed] == ["Derek Damko"]


async def test_counts(graph: Graph) -> None:
    await graph.upsert(NewEntity(name="A", base_type=BaseType.PERSON))
    await graph.upsert(NewEntity(name="B", base_type=BaseType.PERSON))
    await graph.upsert(NewEntity(name="C", base_type=BaseType.CONCEPT))
    assert await graph.entities.count_by_type() == {"person": 2, "concept": 1}
    derek = (await graph.entities.list(base_type=BaseType.PERSON))[0]
    await graph.add_fact(
        NewFact(
            statement="A has role x.",
            space="work",
            subject_id=derek.id,
            kind="HAS_ROLE",
            object_literal="x",
        )
    )
    assert await graph.facts.count_by_status() == {"active": 1}
