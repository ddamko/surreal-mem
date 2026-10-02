"""SurrealDB entity repository."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from surrealmem.knowledge.adapters.surreal.mappers import Row, entity_from_row
from surrealmem.knowledge.domain import (
    BaseType,
    Entity,
    EntityNotFound,
    EntityPatch,
    NewEntity,
    ScoredEntity,
)
from surrealmem.shared.infrastructure.surreal.connection import SurrealConnection, run_one
from surrealmem.shared.infrastructure.surreal.records import to_record_id

if TYPE_CHECKING:
    from collections.abc import Sequence

_LIVE = "archived = false AND merged_into IS NONE"


@dataclass(slots=True)
class SurrealEntityRepository:
    db: SurrealConnection

    async def create(
        self, data: NewEntity, *, embedding: list[float] | None, model: str | None
    ) -> Entity:
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                """
                CREATE entity:ulid() CONTENT {
                    name: $name, base_type: $base_type, subtype: $subtype,
                    description: $description,
                    aliases: $aliases, spaces: $spaces, confidence: $confidence, mention_count: 1,
                    first_seen_at: $seen_at ?? time::now(), last_seen_at: $seen_at ?? time::now(),
                    embedding: $embedding, embedding_model: $model, metadata: $metadata
                } RETURN *
                """,
                {
                    "name": data.name.strip(),
                    "base_type": data.base_type.value,
                    "subtype": data.subtype,
                    "description": data.description,
                    "aliases": list(dict.fromkeys(a.strip() for a in data.aliases if a.strip())),
                    "spaces": [data.space] if data.space else [],
                    "confidence": data.confidence,
                    "seen_at": data.seen_at,
                    "embedding": embedding,
                    "model": model,
                    "metadata": data.metadata,
                },
            ),
        )
        return entity_from_row(rows[0])

    async def get(self, entity_id: str) -> Entity | None:
        rows = cast(
            "list[Row]",
            await run_one(
                self.db, "SELECT * FROM entity WHERE id = $id", {"id": to_record_id(entity_id)}
            ),
        )
        return entity_from_row(rows[0]) if rows else None

    async def get_many(self, entity_ids: Sequence[str]) -> list[Entity]:
        if not entity_ids:
            return []
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                "SELECT * FROM entity WHERE id IN $ids",
                {"ids": [to_record_id(i) for i in entity_ids]},
            ),
        )
        return [entity_from_row(r) for r in rows]

    async def find_exact(self, base_type: BaseType, name_key: str) -> Entity | None:
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                f"SELECT * FROM entity WHERE base_type = $t AND name_key = $k AND {_LIVE} LIMIT 1",
                {"t": base_type.value, "k": name_key},
            ),
        )
        return entity_from_row(rows[0]) if rows else None

    async def find_by_alias(self, base_type: BaseType, alias_key: str) -> Entity | None:
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                "SELECT * FROM entity WHERE base_type = $t AND "
                f"id IN (SELECT VALUE entity FROM alias WHERE alias_key = $k) AND {_LIVE} LIMIT 1",
                {"t": base_type.value, "k": alias_key},
            ),
        )
        return entity_from_row(rows[0]) if rows else None

    async def add_alias(self, entity_id: str, alias: str, *, source: str = "extraction") -> None:
        alias = alias.strip()
        if not alias:
            return
        await run_one(
            self.db,
            """
            LET $key = fn::normalize_name($a);
            LET $found = (SELECT VALUE id FROM alias WHERE entity = $e AND alias_key = $key LIMIT 1)[0];
            IF $found IS NONE {
                CREATE alias CONTENT { entity: $e, alias: $a, source: $s };
                UPDATE $e SET aliases = array::union(aliases, [$a]);
            };
            """,
            {"e": to_record_id(entity_id), "a": alias, "s": source},
        )

    async def touch(
        self,
        entity_id: str,
        *,
        space: str | None,
        seen_at: object | None,
        description: str | None = None,
        confidence: float | None = None,
    ) -> Entity:
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                """
                UPDATE $id SET
                    mention_count += 1,
                    last_seen_at = $seen_at ?? time::now(),
                    first_seen_at = first_seen_at ?? ($seen_at ?? time::now()),
                    spaces = IF $space IS NONE { spaces } ELSE { array::union(spaces, [$space]) },
                    description = IF $description IS NONE { description } ELSE {
                        IF description IS NONE
                            OR string::len($description) > string::len(description)
                        { $description } ELSE { description }
                    },
                    confidence = IF $confidence IS NONE { confidence } ELSE {
                        math::max([confidence, $confidence])
                    }
                RETURN AFTER
                """,
                {
                    "id": to_record_id(entity_id),
                    "seen_at": seen_at,
                    "space": space,
                    "description": description,
                    "confidence": confidence,
                },
            ),
        )
        if not rows:
            raise EntityNotFound(entity_id)
        return entity_from_row(rows[0])

    async def patch(self, entity_id: str, data: EntityPatch) -> Entity:
        changes: dict[str, Any] = data.model_dump(exclude_none=True)
        if "base_type" in changes:
            changes["base_type"] = data.base_type.value if data.base_type else None
        if not changes:
            found = await self.get(entity_id)
            if found is None:
                raise EntityNotFound(entity_id)
            return found
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                "UPDATE $id MERGE $changes RETURN AFTER",
                {"id": to_record_id(entity_id), "changes": changes},
            ),
        )
        if not rows:
            raise EntityNotFound(entity_id)
        return entity_from_row(rows[0])

    async def set_embedding(self, entity_id: str, embedding: list[float], model: str) -> None:
        await run_one(
            self.db,
            "UPDATE $id SET embedding = $e, embedding_model = $m",
            {"id": to_record_id(entity_id), "e": embedding, "m": model},
        )

    async def list(
        self,
        *,
        base_type: BaseType | None = None,
        space: str | None = None,
        include_archived: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Entity]:
        clauses = ["merged_into IS NONE"]
        if not include_archived:
            clauses.append("archived = false")
        if base_type is not None:
            clauses.append("base_type = $t")
        if space is not None:
            clauses.append("$space IN spaces")
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                f"SELECT * FROM entity WHERE {' AND '.join(clauses)} "
                "ORDER BY mention_count DESC LIMIT $limit START $offset",
                {
                    "t": base_type.value if base_type else None,
                    "space": space,
                    "limit": limit,
                    "offset": offset,
                },
            ),
        )
        return [entity_from_row(r) for r in rows]

    async def search_text(
        self, query: str, *, base_type: BaseType | None = None, limit: int = 10
    ) -> list[ScoredEntity]:
        type_clause = "AND base_type = $t" if base_type is not None else ""
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                f"SELECT *, search::score(1) AS score FROM entity WHERE name @1@ $q {type_clause} "
                f"AND {_LIVE} ORDER BY score DESC LIMIT $limit",
                {"q": query, "t": base_type.value if base_type else None, "limit": limit},
            ),
        )
        return [
            ScoredEntity(entity=entity_from_row(r), score=float(r.get("score") or 0.0))
            for r in rows
        ]

    async def search_vector(
        self,
        embedding: list[float],
        *,
        base_type: BaseType | None = None,
        limit: int = 10,
    ) -> list[ScoredEntity]:
        k = max(1, min(int(limit), 200))
        type_clause = "AND base_type = $t" if base_type is not None else ""
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                f"SELECT *, vector::distance::knn() AS distance FROM entity "
                f"WHERE embedding <|{k},40|> $vec {type_clause} AND {_LIVE}",
                {"vec": embedding, "t": base_type.value if base_type else None},
            ),
        )
        return [
            ScoredEntity(entity=entity_from_row(r), score=1.0 - float(r.get("distance") or 0.0))
            for r in rows
        ]

    async def count_by_type(self) -> dict[str, int]:
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                f"SELECT base_type, count() AS n FROM entity WHERE {_LIVE} GROUP BY base_type",
            ),
        )
        return {r["base_type"]: int(r["n"]) for r in rows}
