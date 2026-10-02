"""SurrealDB implementation of the reflection source and writer."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from surrealmem.extraction.domain.reflection import ConversationSlice
from surrealmem.shared.infrastructure.surreal.connection import (
    SurrealConnection,
    run_one,
    run_script,
)
from surrealmem.shared.infrastructure.surreal.records import ref_str, rows_with, to_record_id

if TYPE_CHECKING:
    from datetime import datetime

type Row = dict[str, Any]


@dataclass(slots=True)
class SurrealReflectionRepository:
    db: SurrealConnection

    # ---- source

    async def idle_conversations(
        self, *, idle_seconds: int, min_new_messages: int, limit: int
    ) -> list[str]:
        idle = max(0, int(idle_seconds))
        rows = cast(
            "list[Any]",
            await run_one(
                self.db,
                f"""
                SELECT VALUE id FROM conversation
                WHERE message_count - reflected_to >= $min_new
                  AND last_message_at IS NOT NONE
                  AND last_message_at < time::now() - {idle}s
                LIMIT $limit
                """,
                {"min_new": min_new_messages, "limit": limit},
            )
            or [],
        )
        return [ref_str(r) for r in rows]

    async def unsummarized(
        self, conversation_id: str, *, max_messages: int
    ) -> ConversationSlice | None:
        conv = cast(
            "list[Row]",
            await run_one(
                self.db,
                "SELECT id, space, agent_id, message_count, reflected_to FROM conversation "
                "WHERE id = $id",
                {"id": to_record_id(conversation_id)},
            )
            or [],
        )
        if not conv:
            return None
        row = conv[0]
        start = int(row.get("reflected_to") or 0) + 1
        messages = cast(
            "list[Row]",
            await run_one(
                self.db,
                "SELECT seq, role, content FROM message WHERE conversation = $id AND seq >= $start "
                "ORDER BY seq ASC LIMIT $limit",
                {"id": to_record_id(conversation_id), "start": start, "limit": max_messages},
            )
            or [],
        )
        if not messages:
            return None
        previous = cast(
            "list[Row]",
            await run_one(
                self.db,
                "SELECT content, covers_to FROM summary WHERE conversation = $id "
                "ORDER BY covers_to DESC LIMIT 1",
                {"id": to_record_id(conversation_id)},
            )
            or [],
        )
        return ConversationSlice(
            conversation_id=conversation_id,
            space=str(row["space"]),
            agent_id=str(row["agent_id"]),
            from_seq=int(messages[0]["seq"]),
            to_seq=int(messages[-1]["seq"]),
            messages=[(str(m["role"]), str(m["content"])) for m in messages],
            previous_summary=str(previous[0]["content"]) if previous else None,
        )

    async def contradictions(self) -> list[dict[str, Any]]:
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                """
                SELECT subject, kind, category, space,
                    array::group(id) AS facts, array::group(statement) AS statements, count() AS n
                FROM fact
                WHERE status = 'active' AND NOT ('contradiction' IN flags)
                  AND kind IN (SELECT VALUE kind FROM relation_kind WHERE functional = true)
                GROUP BY subject, kind, category, space
                """,
            )
            or [],
        )
        groups: list[dict[str, Any]] = []
        for row in rows:
            if int(row.get("n") or 0) < 2:
                continue
            subject = ref_str(row["subject"])
            name_rows = cast(
                "list[Row]",
                await run_one(
                    self.db, "SELECT name FROM entity WHERE id = $id", {"id": row["subject"]}
                )
                or [],
            )
            groups.append(
                {
                    "subject": subject,
                    "subject_name": name_rows[0]["name"] if name_rows else subject,
                    "kind": row["kind"],
                    "category": row.get("category"),
                    "space": row.get("space"),
                    "facts": [ref_str(f) for f in cast("list[Any]", row["facts"])],
                    "statements": list(cast("list[Any]", row["statements"])),
                }
            )
        return groups

    # ---- writer

    async def write_summary(
        self,
        conversation: ConversationSlice,
        content: str,
        *,
        model: str,
        embedding: list[float] | None,
        embedding_model: str | None,
    ) -> str:
        results = await run_script(
            self.db,
            """
            BEGIN;
            CREATE summary:ulid() CONTENT {
                conversation: $cid, space: $space, content: $content, covers_from: $from_seq,
                covers_to: $to_seq, model: $model, embedding: $embedding, embedding_model: $emodel
            } RETURN AFTER;
            UPDATE $cid SET reflected_to = $to_seq, reflected_at = time::now(),
                status = IF status = 'closed' { 'closed' } ELSE { 'idle' } RETURN NONE;
            COMMIT;
            """,
            {
                "cid": to_record_id(conversation.conversation_id),
                "space": conversation.space,
                "content": content,
                "from_seq": conversation.from_seq,
                "to_seq": conversation.to_seq,
                "model": model,
                "embedding": embedding,
                "emodel": embedding_model,
            },
        )
        return ref_str(rows_with(results, "covers_to")[0]["id"])

    async def write_observation(
        self,
        *,
        space: str,
        kind: str,
        content: str,
        about: list[str],
        facts: list[str],
        confidence: float = 1.0,
        embedding: list[float] | None = None,
        embedding_model: str | None = None,
    ) -> str:
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                """
                CREATE observation:ulid() CONTENT {
                    space: $space, kind: $kind, content: $content, about: $about, facts: $facts,
                    confidence: $confidence, embedding: $embedding, embedding_model: $emodel
                } RETURN id
                """,
                {
                    "space": space,
                    "kind": kind,
                    "content": content,
                    "about": [to_record_id(a) for a in about],
                    "facts": [to_record_id(f) for f in facts],
                    "confidence": confidence,
                    "embedding": embedding,
                    "emodel": embedding_model,
                },
            ),
        )
        return ref_str(rows[0]["id"])

    async def flag_facts(self, fact_ids: list[str], flag: str) -> None:
        if not fact_ids:
            return
        await run_one(
            self.db,
            "UPDATE fact SET flags = array::union(flags, [$flag]) WHERE id IN $ids",
            {"ids": [to_record_id(f) for f in fact_ids], "flag": flag},
        )

    async def recompute_salience(self, *, now: datetime | None = None) -> int:
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                """
                UPDATE fact SET salience = math::clamp(
                    0.2
                    + 0.12 * math::ln(access_count + 1)
                    + 0.3 * confidence
                    + 0.3 * math::pow(0.5, duration::days(time::now() - recorded_at) / 90.0),
                    0.0, 1.0)
                WHERE status = 'active' RETURN id
                """,
            )
            or [],
        )
        await run_one(
            self.db,
            """
            UPDATE entity SET salience = math::clamp(
                0.2 + 0.15 * math::ln(mention_count + 1)
                + 0.25 * math::pow(0.5,
                    duration::days(time::now() - (last_seen_at ?? created_at)) / 120.0),
                0.0, 1.0)
            WHERE archived = false RETURN NONE
            """,
        )
        return len(rows)

    async def archive_stale(self, *, salience_floor: float, min_age_days: int) -> int:
        age = max(0, int(min_age_days))
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                f"""
                UPDATE fact SET status = 'archived'
                WHERE status = 'active' AND salience < $floor AND access_count = 0
                  AND recorded_at < time::now() - {age}d
                RETURN id
                """,
                {"floor": salience_floor},
            )
            or [],
        )
        return len(rows)
