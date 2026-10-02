"""Overview statistics for the dashboard and the MCP graph/stats resource."""

from typing import Any, cast

from fastapi import APIRouter
from pydantic import BaseModel, Field

from surrealmem.bootstrap.dependencies import ContainerDep
from surrealmem.shared.infrastructure.surreal.connection import run_one

router = APIRouter(prefix="/stats", tags=["stats"])

_COUNTED = (
    "space",
    "agent",
    "conversation",
    "message",
    "entity",
    "related_to",
    "fact",
    "alias",
    "merge_candidate",
    "trace",
    "step",
    "tool_call",
    "summary",
    "observation",
    "job",
)


class Overview(BaseModel):
    tables: dict[str, int]
    entities_by_type: dict[str, int]
    facts_by_status: dict[str, int]
    jobs_by_status: dict[str, int]
    relationship_kinds: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])
    spaces: list[str] = Field(default_factory=list[str])


@router.get("/overview")
async def overview(container: ContainerDep) -> Overview:
    db = container.db
    services = container.services
    counts: dict[str, int] = {}
    for table in _COUNTED:
        rows = cast(
            "list[dict[str, Any]]",
            await run_one(db, f"SELECT count() AS n FROM {table} GROUP ALL") or [],
        )
        counts[table] = int(rows[0]["n"]) if rows else 0
    kinds = cast(
        "list[dict[str, Any]]",
        await run_one(db, "SELECT kind, count() AS n FROM related_to GROUP BY kind ORDER BY n DESC")
        or [],
    )
    spaces = cast(
        "list[dict[str, Any]]", await run_one(db, "SELECT name FROM space ORDER BY name") or []
    )
    return Overview(
        tables=counts,
        entities_by_type=await services.knowledge.entities.count_by_type(),
        facts_by_status=await services.knowledge.facts.count_by_status(),
        jobs_by_status=await services.extraction.job_store.counts(),
        relationship_kinds=[{"kind": k["kind"], "count": int(k["n"])} for k in kinds],
        spaces=[str(s["name"]) for s in spaces],
    )
