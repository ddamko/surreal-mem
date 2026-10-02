from typing import TYPE_CHECKING

import httpx
import pytest
from pydantic import SecretStr

from surrealmem.bootstrap.app import create_app
from surrealmem.bootstrap.container import AppContainer
from surrealmem.bootstrap.services import build_services
from surrealmem.conversations.domain import NewConversation, NewMessage, Role
from surrealmem.knowledge.domain import BaseType, NewEntity, NewFact, NewRelationship
from surrealmem.shared.infrastructure.config import Settings
from tests.fakes import FakeEmbedder

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from surrealmem.shared.infrastructure.surreal.connection import SurrealConnection


@pytest.fixture
async def api(migrated_db: SurrealConnection) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(
        surreal_url="mem://", log_json=False, api_token=SecretStr("t"), dashboard_dist=None
    )  # pyright: ignore[reportCallIssue]
    services = build_services(migrated_db, settings=settings, embedder=FakeEmbedder())
    k = services.knowledge
    derek, _ = await k.upsert_entity(
        NewEntity(name="Derek Damko", base_type=BaseType.PERSON, space="work")
    )
    wws, _ = await k.upsert_entity(
        NewEntity(name="WWS Sires", base_type=BaseType.ORGANIZATION, space="work")
    )
    texas, _ = await k.upsert_entity(
        NewEntity(name="Texas", base_type=BaseType.LOCATION, space="work")
    )
    sdb, _ = await k.upsert_entity(
        NewEntity(name="SurrealDB", base_type=BaseType.CONCEPT, space="work")
    )
    await k.add_relationship(
        NewRelationship(source_id=derek.id, target_id=wws.id, kind="WORKS_AT", space="work")
    )
    await k.add_relationship(
        NewRelationship(source_id=wws.id, target_id=texas.id, kind="LOCATED_IN", space="work")
    )
    await k.add_relationship(
        NewRelationship(source_id=derek.id, target_id=sdb.id, kind="USES", space="work")
    )
    await k.add_fact(
        NewFact(
            statement="Derek works at WWS Sires.",
            space="work",
            subject_id=derek.id,
            kind="WORKS_AT",
            object_id=wws.id,
        )
    )
    conversation = await services.conversations.start(NewConversation(space="work", agent_id="t"))
    message = await services.conversations.append(
        conversation.id, NewMessage(role=Role.USER, content="Derek and WWS")
    )
    await k.provenance.link_mention(message.id, derek.id)
    await k.provenance.link_mention(message.id, wws.id)
    await services.analytics.metrics()
    await services.analytics.projection()
    container = AppContainer(settings=settings, db=migrated_db, services=services)
    app = create_app(settings=settings, container=container)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test/api/v1",
        headers={"Authorization": "Bearer t"},
    ) as client:
        client.headers["X-Conversation"] = conversation.id
        client.headers["X-Derek"] = derek.id
        client.headers["X-Texas"] = texas.id
        yield client


async def test_graph_endpoints(api: httpx.AsyncClient) -> None:
    graph = (await api.get("/graph", params={"space": "work"})).json()
    assert len(graph["nodes"]) == 4 and len(graph["edges"]) == 3
    assert "metrics" in graph["nodes"][0] and "pagerank" in graph["nodes"][0]["metrics"]
    typed = (
        await api.get("/graph", params=[("base_type", "person"), ("base_type", "organization")])
    ).json()
    assert {n["base_type"] for n in typed["nodes"]} == {"person", "organization"}
    assert [e["kind"] for e in typed["edges"]] == ["WORKS_AT"]
    derek = api.headers["X-Derek"]
    hood = (await api.get(f"/graph/neighbors/{derek}", params={"hops": 2})).json()
    assert len(hood["nodes"]) == 4
    path = (
        await api.get("/graph/path", params={"source": derek, "target": api.headers["X-Texas"]})
    ).json()
    assert path["found"] and [e["kind"] for e in path["edges"]] == ["WORKS_AT", "LOCATED_IN"]
    none = (
        await api.get("/graph/path", params={"source": derek, "target": "entity:nowhere"})
    ).json()
    assert none["found"] is False


async def test_analytics_endpoints(api: httpx.AsyncClient) -> None:
    timeline = (await api.get("/stats/timeline", params={"space": "work", "days": 7})).json()[
        "series"
    ]
    assert timeline["entity"][0]["n"] == 4 and timeline["message"][0]["n"] == 1
    central = (
        await api.get("/analytics/centrality", params={"metric": "pagerank", "limit": 3})
    ).json()["rows"]
    assert len(central) == 3 and central[0]["value"] >= central[1]["value"]
    assert (await api.get("/analytics/centrality", params={"metric": "nope"})).status_code == 422
    communities = (await api.get("/analytics/communities")).json()["rows"]
    assert sum(c["size"] for c in communities) == 4
    kinds = (await api.get("/analytics/kinds", params={"space": "work"})).json()["rows"]
    assert {k["kind"] for k in kinds} == {"WORKS_AT", "LOCATED_IN", "USES"}
    flows = (await api.get("/analytics/flows")).json()["rows"]
    assert {"source": "person", "target": "organization", "kind": "WORKS_AT", "n": 1} in flows
    co = (await api.get("/analytics/cooccurrence")).json()["rows"]
    assert co[0]["n"] == 1 and {co[0]["a_name"], co[0]["b_name"]} == {"Derek Damko", "WWS Sires"}
    health = (await api.get("/analytics/facts", params={"space": "work"})).json()
    assert health["by_status"] == {"active": 1} and health["flagged"] == 0
    projection = (await api.get("/projection", params={"table": "entity"})).json()["rows"]
    assert len(projection) == 4 and {"x", "y", "z3"} <= set(projection[0]["projection"])
    assert (await api.get("/projection", params={"table": "nope"})).status_code == 422
    mentions = (await api.get(f"/conversations/{api.headers['X-Conversation']}/mentions")).json()[
        "rows"
    ]
    assert {m["name"] for m in mentions} == {"Derek Damko", "WWS Sires"}
