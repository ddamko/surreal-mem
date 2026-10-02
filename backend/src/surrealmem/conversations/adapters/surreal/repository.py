"""SurrealDB implementation of the conversation repository."""

from dataclasses import dataclass
from typing import Any, cast

from surrealmem.conversations.domain import (
    Conversation,
    ConversationStatus,
    ExtractionStatus,
    Message,
    NewConversation,
    NewMessage,
)
from surrealmem.shared.infrastructure.surreal.connection import (
    SurrealConnection,
    run_one,
    run_script,
)
from surrealmem.shared.infrastructure.surreal.records import (
    opt_datetime,
    plain,
    ref_str,
    rows_with,
    to_datetime,
    to_record_id,
)

type Row = dict[str, Any]


def _conversation(row: Row) -> Conversation:
    return Conversation(
        id=ref_str(row["id"]),
        space=row["space"],
        agent_id=row["agent_id"],
        user_id=row.get("user_id", "default"),
        title=row.get("title"),
        status=ConversationStatus(row.get("status", "open")),
        external_id=row.get("external_id"),
        message_count=int(row.get("message_count", 0)),
        last_message_at=opt_datetime(row.get("last_message_at")),
        started_at=to_datetime(row["started_at"]),
        metadata=plain(row.get("metadata") or {}),
    )


def _message(row: Row) -> Message:
    return Message(
        id=ref_str(row["id"]),
        conversation_id=ref_str(row["conversation"]),
        space=row["space"],
        seq=int(row["seq"]),
        role=row["role"],
        content=row["content"],
        name=row.get("name"),
        tokens=row.get("tokens"),
        extraction_status=ExtractionStatus(row.get("extraction_status", "pending")),
        created_at=to_datetime(row["created_at"]),
        metadata=plain(row.get("metadata") or {}),
    )


@dataclass(slots=True)
class SurrealConversationRepository:
    db: SurrealConnection

    async def create(self, data: NewConversation) -> Conversation:
        results = await run_script(
            self.db,
            """
            UPSERT type::record('space', $space) SET name = $space;
            UPSERT type::record('agent', $agent_id) SET name = $agent_id;
            CREATE conversation:ulid() CONTENT {
                space: $space, agent_id: $agent_id, user_id: $user_id, title: $title,
                external_id: $external_id, metadata: $metadata
            } RETURN *;
            """,
            {
                "space": data.space,
                "agent_id": data.agent_id,
                "user_id": data.user_id,
                "title": data.title,
                "external_id": data.external_id,
                "metadata": data.metadata,
            },
        )
        return _conversation(cast("list[Row]", results[2])[0])

    async def get(self, conversation_id: str) -> Conversation | None:
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                "SELECT * FROM conversation WHERE id = $id",
                {"id": to_record_id(conversation_id)},
            ),
        )
        return _conversation(rows[0]) if rows else None

    async def find_external(self, agent_id: str, external_id: str) -> Conversation | None:
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                "SELECT * FROM conversation WHERE agent_id = $agent_id "
                "AND external_id = $external_id LIMIT 1",
                {"agent_id": agent_id, "external_id": external_id},
            ),
        )
        return _conversation(rows[0]) if rows else None

    async def list(
        self,
        *,
        space: str | None = None,
        agent_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Conversation]:
        clauses = ["true"]
        if space is not None:
            clauses.append("space = $space")
        if agent_id is not None:
            clauses.append("agent_id = $agent_id")
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                f"SELECT * FROM conversation WHERE {' AND '.join(clauses)} "
                "ORDER BY started_at DESC LIMIT $limit START $offset",
                {"space": space, "agent_id": agent_id, "limit": limit, "offset": offset},
            ),
        )
        return [_conversation(r) for r in rows]

    async def set_status(self, conversation_id: str, status: ConversationStatus) -> None:
        await run_one(
            self.db,
            "UPDATE $id SET status = $status",
            {"id": to_record_id(conversation_id), "status": status.value},
        )

    async def append_message(self, conversation_id: str, data: NewMessage) -> Message:
        results = await run_script(
            self.db,
            """
            BEGIN;
            LET $conv = (SELECT id, space, message_count FROM ONLY $cid);
            LET $seq = $conv.message_count + 1;
            CREATE message:ulid() CONTENT {
                conversation: $conv.id, space: $conv.space, seq: $seq, role: $role,
                content: $content, name: $name, tokens: $tokens,
                created_at: $created_at ?? time::now(), metadata: $metadata
            } RETURN *;
            UPDATE $conv.id SET message_count = $seq,
                last_message_at = $created_at ?? time::now(), status = 'open';
            COMMIT;
            """,
            {
                "cid": to_record_id(conversation_id),
                "role": data.role.value,
                "content": data.content,
                "name": data.name,
                "tokens": data.tokens,
                "created_at": data.created_at,
                "metadata": data.metadata,
            },
        )
        return _message(rows_with(results, "seq")[0])

    async def get_message(self, message_id: str) -> Message | None:
        rows = cast(
            "list[Row]",
            await run_one(
                self.db, "SELECT * FROM message WHERE id = $id", {"id": to_record_id(message_id)}
            ),
        )
        return _message(rows[0]) if rows else None

    async def messages(
        self, conversation_id: str, *, limit: int = 100, before_seq: int | None = None
    ) -> list[Message]:
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                "SELECT * FROM message WHERE conversation = $cid AND seq < $before "
                "ORDER BY seq DESC LIMIT $limit",
                {
                    "cid": to_record_id(conversation_id),
                    "before": before_seq if before_seq is not None else 2**53,
                    "limit": limit,
                },
            ),
        )
        return [_message(r) for r in reversed(rows)]

    async def set_extraction_status(self, message_id: str, status: ExtractionStatus) -> None:
        await run_one(
            self.db,
            "UPDATE $id SET extraction_status = $status",
            {"id": to_record_id(message_id), "status": status.value},
        )
