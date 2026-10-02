"""SurrealDB fact repository with bi-temporal supersession (ADR-0006)."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from surrealmem.knowledge.adapters.surreal.mappers import Row, fact_from_row
from surrealmem.knowledge.domain import Fact, FactNotFound, FactStatus, NewFact
from surrealmem.shared.infrastructure.surreal.connection import (
    SurrealConnection,
    run_one,
    run_script,
)
from surrealmem.shared.infrastructure.surreal.records import rows_with, to_record_id

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(slots=True)
class SurrealFactRepository:
    db: SurrealConnection

    async def create(
        self,
        data: NewFact,
        *,
        embedding: list[float] | None,
        model: str | None,
        supersede_active: bool,
    ) -> Fact:
        results = await run_script(
            self.db,
            """
            BEGIN;
            LET $previous = (SELECT VALUE id FROM fact WHERE $supersede = true
                AND subject = $subject AND kind = $kind AND status = 'active'
                AND category = $category);
            LET $created = (CREATE fact:ulid() CONTENT {
                statement: $statement, space: $space, subject: $subject, object: $object,
                object_literal: $object_literal, kind: $kind, category: $category,
                confidence: $confidence, valid_from: $valid_from, valid_to: $valid_to,
                recorded_at: $recorded_at ?? time::now(), source_kind: $source_kind,
                supersedes: $previous[0], embedding: $embedding, embedding_model: $model,
                metadata: $metadata
            } RETURN AFTER)[0];
            IF array::len($previous) > 0 {
                UPDATE $previous SET status = 'invalidated', invalidated_at = time::now(),
                    superseded_by = $created.id,
                    valid_to = valid_to ?? ($created.valid_from ?? time::now())
                RETURN NONE;
            };
            SELECT * FROM fact WHERE id = $created.id;
            COMMIT;
            """,
            {
                "supersede": supersede_active,
                "statement": data.statement.strip(),
                "space": data.space,
                "subject": to_record_id(data.subject_id),
                "object": to_record_id(data.object_id) if data.object_id else None,
                "object_literal": data.object_literal,
                "kind": data.kind,
                "category": data.category,
                "confidence": data.confidence,
                "valid_from": data.valid_from,
                "valid_to": data.valid_to,
                "recorded_at": data.recorded_at,
                "source_kind": data.source_kind.value,
                "embedding": embedding,
                "model": model,
                "metadata": data.metadata,
            },
        )
        return fact_from_row(rows_with(results, "statement")[0])

    async def get(self, fact_id: str) -> Fact | None:
        rows = cast(
            "list[Row]",
            await run_one(
                self.db, "SELECT * FROM fact WHERE id = $id", {"id": to_record_id(fact_id)}
            ),
        )
        return fact_from_row(rows[0]) if rows else None

    async def for_subject(
        self,
        subject_id: str,
        *,
        statuses: Sequence[FactStatus] = (FactStatus.ACTIVE,),
        limit: int = 100,
    ) -> list[Fact]:
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                "SELECT * FROM fact WHERE subject = $s AND status IN $statuses "
                "ORDER BY recorded_at DESC LIMIT $limit",
                {
                    "s": to_record_id(subject_id),
                    "statuses": [s.value for s in statuses],
                    "limit": limit,
                },
            ),
        )
        return [fact_from_row(r) for r in rows]

    async def for_entities(
        self, entity_ids: Sequence[str], *, statuses: Sequence[FactStatus] = (FactStatus.ACTIVE,)
    ) -> list[Fact]:
        if not entity_ids:
            return []
        ids = [to_record_id(i) for i in entity_ids]
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                "SELECT * FROM fact WHERE (subject IN $ids OR object IN $ids) "
                "AND status IN $statuses ORDER BY recorded_at DESC",
                {"ids": ids, "statuses": [s.value for s in statuses]},
            ),
        )
        return [fact_from_row(r) for r in rows]

    async def history(self, fact_id: str) -> list[Fact]:
        chain: list[Fact] = []
        current = await self.get(fact_id)
        seen: set[str] = set()
        while current is not None and current.id not in seen:
            chain.append(current)
            seen.add(current.id)
            current = await self.get(current.supersedes) if current.supersedes else None
        chain.reverse()
        return chain

    async def invalidate(self, fact_id: str, *, reason: str | None = None) -> Fact:
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                "UPDATE $id SET status = 'invalidated', invalidated_at = time::now(), "
                "metadata.invalidation_reason = $reason WHERE status = 'active' RETURN AFTER",
                {"id": to_record_id(fact_id), "reason": reason},
            ),
        )
        if rows:
            return fact_from_row(rows[0])
        found = await self.get(fact_id)
        if found is None:
            raise FactNotFound(fact_id)
        return found

    async def set_embedding(self, fact_id: str, embedding: list[float], model: str) -> None:
        await run_one(
            self.db,
            "UPDATE $id SET embedding = $e, embedding_model = $m",
            {"id": to_record_id(fact_id), "e": embedding, "m": model},
        )

    async def count_by_status(self) -> dict[str, int]:
        rows = cast(
            "list[Row]",
            await run_one(self.db, "SELECT status, count() AS n FROM fact GROUP BY status"),
        )
        return {r["status"]: int(r["n"]) for r in rows}
