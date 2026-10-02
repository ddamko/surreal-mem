"""SurrealDB relationship repository: the related_to edge table and the kind vocabulary."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from surrealmem.knowledge.adapters.surreal.mappers import (
    Row,
    kind_from_row,
    relationship_from_row,
)
from surrealmem.shared.infrastructure.surreal.connection import (
    SurrealConnection,
    run_one,
    run_script,
)
from surrealmem.shared.infrastructure.surreal.records import ref_str, rows_with, to_record_id

if TYPE_CHECKING:
    from collections.abc import Sequence

    from surrealmem.knowledge.domain import NewRelationship, RelationKind, Relationship


@dataclass(slots=True)
class SurrealRelationshipRepository:
    db: SurrealConnection

    async def upsert(self, data: NewRelationship, *, proposed: bool) -> Relationship:
        results = await run_script(
            self.db,
            """
            BEGIN;
            LET $existing = (SELECT id FROM related_to
                WHERE in = $in AND out = $out AND kind = $kind LIMIT 1)[0].id;
            IF $existing IS NONE {
                RELATE $in->related_to->$out SET kind = $kind, confidence = $confidence,
                    proposed = $proposed, spaces = $spaces, fact = $fact, metadata = $metadata
                RETURN AFTER;
            } ELSE {
                UPDATE $existing SET mention_count += 1,
                    confidence = math::max([confidence, $confidence]),
                    spaces = array::union(spaces, $spaces),
                    fact = fact ?? $fact
                RETURN AFTER;
            };
            COMMIT;
            """,
            {
                "in": to_record_id(data.source_id),
                "out": to_record_id(data.target_id),
                "kind": data.kind,
                "confidence": data.confidence,
                "proposed": proposed,
                "spaces": [data.space] if data.space else [],
                "fact": to_record_id(data.fact_id) if data.fact_id else None,
                "metadata": data.metadata,
            },
        )
        return relationship_from_row(rows_with(results, "kind")[0])

    async def get(self, relationship_id: str) -> Relationship | None:
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                "SELECT * FROM related_to WHERE id = $id",
                {"id": to_record_id(relationship_id)},
            ),
        )
        return relationship_from_row(rows[0]) if rows else None

    async def for_entity(
        self, entity_id: str, *, kinds: Sequence[str] | None = None, limit: int = 200
    ) -> list[Relationship]:
        kind_clause = "AND kind IN $kinds" if kinds else ""
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                f"SELECT * FROM related_to WHERE (in = $id OR out = $id) {kind_clause} "
                "ORDER BY mention_count DESC LIMIT $limit",
                {"id": to_record_id(entity_id), "kinds": list(kinds or []), "limit": limit},
            ),
        )
        return [relationship_from_row(r) for r in rows]

    async def among(self, entity_ids: Sequence[str]) -> list[Relationship]:
        if not entity_ids:
            return []
        ids = [to_record_id(i) for i in entity_ids]
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                "SELECT * FROM related_to WHERE in IN $ids AND out IN $ids",
                {"ids": ids},
            ),
        )
        return [relationship_from_row(r) for r in rows]

    async def neighbor_ids(self, entity_id: str, *, hops: int = 1) -> list[str]:
        depth = max(1, min(int(hops), 4))
        values = cast(
            "list[Any] | None",
            await run_one(
                self.db,
                f"SELECT VALUE @.{{1..{depth}+collect}}(<->related_to<->entity) FROM ONLY $id",
                {"id": to_record_id(entity_id)},
            ),
        )
        seen: dict[str, None] = {}
        for value in values or []:
            if value is None:
                continue
            ref = ref_str(value)
            if ref != entity_id:
                seen[ref] = None
        return list(seen)

    async def kinds(self) -> list[RelationKind]:
        rows = cast(
            "list[Row]",
            await run_one(self.db, "SELECT * FROM relation_kind ORDER BY kind"),
        )
        return [kind_from_row(r) for r in rows]

    async def get_kind(self, kind: str) -> RelationKind | None:
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                "SELECT * FROM relation_kind WHERE kind = $k LIMIT 1",
                {"k": kind},
            ),
        )
        return kind_from_row(rows[0]) if rows else None

    async def register_kind(self, kind: str, *, proposed: bool) -> RelationKind:
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                "UPSERT type::record('relation_kind', $k) SET kind = $k, proposed = $proposed "
                "RETURN AFTER",
                {"k": kind, "proposed": proposed},
            ),
        )
        return kind_from_row(rows[0])

    async def bump_kind_usage(self, kind: str) -> None:
        await run_one(
            self.db,
            "UPDATE type::record('relation_kind', $k) SET usage_count += 1",
            {"k": kind},
        )

    async def set_kind_proposed(self, kind: str, *, proposed: bool) -> RelationKind:
        results = await run_script(
            self.db,
            """
            BEGIN;
            UPDATE type::record('relation_kind', $k) SET proposed = $p RETURN NONE;
            UPDATE related_to SET proposed = $p WHERE kind = $k RETURN NONE;
            SELECT * FROM relation_kind WHERE kind = $k;
            COMMIT;
            """,
            {"k": kind, "p": proposed},
        )
        try:
            rows = rows_with(results, "kind")
        except LookupError as exc:
            raise LookupError(kind) from exc
        return kind_from_row(rows[0])
