"""Overview statistics for the dashboard and the MCP graph/stats resource."""

from typing import Any, cast

from fastapi import APIRouter
from pydantic import BaseModel, Field

from surrealmem import __version__
from surrealmem.bootstrap.dependencies import ContainerDep
from surrealmem.shared.infrastructure.surreal import migrations as mig
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


class ConfigView(BaseModel):
    version: str
    surreal_url: str
    namespace: str
    database: str
    llm_base_url: str
    llm_model: str
    llm_fallback_model: str | None
    embed_base_url: str
    embed_model: str
    embed_dimension: int
    extraction_window: int
    resolution_auto_merge: float
    resolution_review: float
    worker_concurrency: int
    schedule_seconds: dict[str, int]
    default_space: str


@router.get("/config")
async def config(container: ContainerDep) -> ConfigView:
    """Effective configuration without secrets (Operations page)."""
    s = container.settings
    return ConfigView(
        version=__version__,
        surreal_url=s.surreal_url,
        namespace=s.surreal_namespace,
        database=s.surreal_database,
        llm_base_url=s.llm_base_url,
        llm_model=s.llm_model,
        llm_fallback_model=s.llm_fallback_model,
        embed_base_url=s.embed_base_url,
        embed_model=s.embed_model,
        embed_dimension=s.embed_dimension,
        extraction_window=s.extraction_window,
        resolution_auto_merge=s.resolution_auto_merge,
        resolution_review=s.resolution_review,
        worker_concurrency=s.worker_concurrency,
        schedule_seconds={
            "reflect_sweep": s.schedule_reflect_sweep_seconds,
            "salience": s.schedule_salience_seconds,
            "metrics": s.schedule_metrics_seconds,
            "project": s.schedule_project_seconds,
        },
        default_space=s.default_space,
    )


class MigrationRow(BaseModel):
    version: int
    name: str
    applied: bool
    checksum_matches: bool


@router.get("/migrations")
async def migrations(container: ContainerDep) -> list[MigrationRow]:
    """Schema migration status against the migrations directory."""
    found = mig.discover(container.settings.migrations_dir)
    report = await mig.status(container.db, found)
    return [
        MigrationRow(
            version=r.migration.version,
            name=r.migration.name,
            applied=r.applied,
            checksum_matches=r.checksum_matches,
        )
        for r in report
    ]
