"""REST routes for the dashboard: graph export, neighbours, paths, timelines, analytics and
projections."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from surrealmem.analytics.adapters.surreal.queries import SurrealAnalyticsQueries


def _queries(request: Request) -> SurrealAnalyticsQueries:
    return request.app.state.analytics_queries


Queries = Annotated[SurrealAnalyticsQueries, Depends(_queries)]
router = APIRouter(tags=["analytics"])


class Graph(BaseModel):
    nodes: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])
    edges: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])


class Path(BaseModel):
    edges: list[dict[str, Any]]
    found: bool


class Timeline(BaseModel):
    series: dict[str, list[dict[str, Any]]]


class Rows(BaseModel):
    rows: list[dict[str, Any]]


@router.get("/graph")
async def graph(
    q: Queries,
    space: str | None = None,
    base_type: Annotated[list[str] | None, Query()] = None,
    kind: Annotated[list[str] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
    min_mentions: Annotated[int, Query(ge=0)] = 0,
) -> Graph:
    nodes, edges = await q.graph(
        space=space, base_types=base_type, kinds=kind, limit=limit, min_mentions=min_mentions
    )
    return Graph(nodes=nodes, edges=edges)


@router.get("/graph/neighbors/{entity_id:path}")
async def neighbors(
    entity_id: str, q: Queries, hops: Annotated[int, Query(ge=1, le=3)] = 1
) -> Graph:
    nodes, edges = await q.neighbors(entity_id, hops=hops)
    return Graph(nodes=nodes, edges=edges)


@router.get("/graph/path")
async def shortest_path(
    q: Queries, source: str, target: str, max_depth: Annotated[int, Query(ge=1, le=8)] = 6
) -> Path:
    edges = await q.shortest_path(source, target, max_depth=max_depth)
    return Path(edges=edges, found=bool(edges) or source == target)


@router.get("/stats/timeline")
async def timeline(
    q: Queries, space: str | None = None, days: Annotated[int, Query(ge=1, le=365)] = 30
) -> Timeline:
    return Timeline(series=await q.timeline(space=space, days=days))


@router.get("/analytics/centrality")
async def centrality(
    q: Queries,
    metric: str = "pagerank",
    space: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 25,
) -> Rows:
    return Rows(rows=await q.centrality(metric=metric, space=space, limit=limit))


@router.get("/analytics/communities")
async def communities(
    q: Queries, space: str | None = None, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> Rows:
    return Rows(rows=await q.communities(space=space, limit=limit))


@router.get("/analytics/kinds")
async def kinds(q: Queries, space: str | None = None) -> Rows:
    return Rows(rows=await q.kinds(space=space))


@router.get("/analytics/flows")
async def flows(q: Queries, space: str | None = None) -> Rows:
    return Rows(rows=await q.flows(space=space))


@router.get("/analytics/cooccurrence")
async def cooccurrence(
    q: Queries, space: str | None = None, limit: Annotated[int, Query(ge=1, le=500)] = 60
) -> Rows:
    return Rows(rows=await q.cooccurrence(space=space, limit=limit))


@router.get("/analytics/facts")
async def fact_health(q: Queries, space: str | None = None) -> dict[str, Any]:
    return await q.fact_health(space=space)


@router.get("/projection")
async def projection(
    q: Queries,
    table: str = "entity",
    space: str | None = None,
    limit: Annotated[int, Query(ge=1, le=20000)] = 5000,
) -> Rows:
    return Rows(rows=await q.projection(table=table, space=space, limit=limit))


@router.get("/conversations/{conversation_id:path}/mentions")
async def conversation_mentions(conversation_id: str, q: Queries) -> Rows:
    return Rows(rows=await q.mentions_for_conversation(conversation_id))
