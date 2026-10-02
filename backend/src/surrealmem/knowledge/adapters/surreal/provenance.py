"""mentions and extracted_from edges."""

from dataclasses import dataclass
from typing import Any, cast

from surrealmem.shared.infrastructure.surreal.connection import SurrealConnection, run_one
from surrealmem.shared.infrastructure.surreal.records import ref_str, to_record_id


@dataclass(slots=True)
class SurrealProvenanceRepository:
    db: SurrealConnection

    async def link_mention(
        self, message_id: str, entity_id: str, *, confidence: float = 1.0
    ) -> None:
        await run_one(
            self.db,
            """
            LET $found = (SELECT VALUE id FROM mentions WHERE in = $m AND out = $e LIMIT 1)[0];
            IF $found IS NONE {
                RELATE $m->mentions->$e SET confidence = $c;
            } ELSE {
                UPDATE $found SET confidence = math::max([confidence, $c]);
            };
            """,
            {"m": to_record_id(message_id), "e": to_record_id(entity_id), "c": confidence},
        )

    async def link_source(
        self,
        record_id: str,
        message_id: str,
        *,
        extractor: str,
        model: str | None = None,
        confidence: float = 1.0,
    ) -> None:
        await run_one(
            self.db,
            """
            LET $found = (SELECT VALUE id FROM extracted_from
                WHERE in = $r AND out = $m LIMIT 1)[0];
            IF $found IS NONE {
                RELATE $r->extracted_from->$m SET extractor = $x, model = $model, confidence = $c;
            };
            """,
            {
                "r": to_record_id(record_id),
                "m": to_record_id(message_id),
                "x": extractor,
                "model": model,
                "c": confidence,
            },
        )

    async def sources_of(self, record_id: str) -> list[str]:
        rows = cast(
            "list[Any]",
            await run_one(
                self.db,
                "SELECT VALUE out FROM extracted_from WHERE in = $r",
                {"r": to_record_id(record_id)},
            )
            or [],
        )
        return [ref_str(r) for r in rows]

    async def mentioned_in(self, entity_id: str, *, limit: int = 50) -> list[str]:
        rows = cast(
            "list[Any]",
            await run_one(
                self.db,
                "SELECT VALUE in FROM mentions WHERE out = $e LIMIT $limit",
                {"e": to_record_id(entity_id), "limit": limit},
            )
            or [],
        )
        return [ref_str(r) for r in rows]
