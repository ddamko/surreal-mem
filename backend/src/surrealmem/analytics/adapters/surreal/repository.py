"""SurrealDB access for the analytics jobs."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from surrealmem.shared.infrastructure.surreal.connection import SurrealConnection, run_one
from surrealmem.shared.infrastructure.surreal.records import ref_str, to_record_id

if TYPE_CHECKING:
    from collections.abc import Sequence

type Row = dict[str, Any]


@dataclass(slots=True)
class SurrealAnalyticsRepository:
    db: SurrealConnection

    async def entity_ids(self) -> list[str]:
        rows = cast(
            "list[Any]",
            await run_one(
                self.db,
                "SELECT VALUE id FROM entity WHERE archived = false AND merged_into IS NONE",
            )
            or [],
        )
        return [ref_str(r) for r in rows]

    async def edges(self) -> list[tuple[str, str, float]]:
        rows = cast(
            "list[Row]",
            await run_one(self.db, "SELECT in, out, mention_count, weight FROM related_to") or [],
        )
        return [
            (
                ref_str(r["in"]),
                ref_str(r["out"]),
                float(r.get("mention_count") or 1) * float(r.get("weight") or 1.0),
            )
            for r in rows
        ]

    async def write_metrics(self, metrics: dict[str, dict[str, Any]]) -> int:
        updated = 0
        items = list(metrics.items())
        for start in range(0, len(items), 200):
            batch = items[start : start + 200]
            await run_one(
                self.db,
                """
                FOR $item IN $items {
                    UPDATE type::record($item.id)
                        SET metrics = $item.metrics, metrics_at = time::now()
                    RETURN NONE;
                };
                """,
                {"items": [{"id": entity_id, "metrics": m} for entity_id, m in batch]},
            )
            updated += len(batch)
        return updated

    async def names(self, ids: Sequence[str]) -> dict[str, str]:
        if not ids:
            return {}
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                "SELECT id, name FROM entity WHERE id IN $ids",
                {"ids": [to_record_id(i) for i in ids]},
            )
            or [],
        )
        return {ref_str(r["id"]): str(r["name"]) for r in rows}

    async def embeddings(self, table: str, *, limit: int) -> list[tuple[str, list[float]]]:
        if table not in {"entity", "fact", "summary", "observation", "message", "trace"}:
            raise ValueError(f"unsupported table {table!r}")
        live = {
            "entity": "AND archived = false AND merged_into IS NONE",
            "fact": "AND status = 'active'",
        }.get(table, "")
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                f"SELECT id, embedding FROM {table} "
                f"WHERE embedding IS NOT NONE {live} LIMIT $limit",
                {"limit": limit},
            )
            or [],
        )
        return [
            (ref_str(r["id"]), [float(x) for x in cast("list[float]", r["embedding"])])
            for r in rows
        ]

    async def write_projection(self, table: str, coordinates: dict[str, dict[str, float]]) -> int:
        items = list(coordinates.items())
        for start in range(0, len(items), 500):
            batch = items[start : start + 500]
            await run_one(
                self.db,
                """
                FOR $item IN $items {
                    UPDATE type::record($item.id) SET projection = $item.projection RETURN NONE;
                };
                """,
                {"items": [{"id": record_id, "projection": p} for record_id, p in batch]},
            )
        return len(items)
