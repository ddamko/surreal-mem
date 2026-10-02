"""SurrealDB trace repository."""

from dataclasses import dataclass
from typing import Any, cast

from surrealmem.reasoning.domain import (
    NewStep,
    NewTrace,
    Step,
    ToolCall,
    Trace,
    TraceNotFound,
    TraceStatus,
)
from surrealmem.shared.infrastructure.surreal.connection import (
    SurrealConnection,
    run_one,
    run_script,
)
from surrealmem.shared.infrastructure.surreal.records import (
    opt_datetime,
    opt_ref_str,
    plain,
    ref_str,
    rows_with,
    to_datetime,
    to_record_id,
)

type Row = dict[str, Any]


def _trace(row: Row) -> Trace:
    return Trace(
        id=ref_str(row["id"]),
        space=row["space"],
        agent_id=row["agent_id"],
        task=row["task"],
        status=TraceStatus(row.get("status", "running")),
        conversation_id=opt_ref_str(row.get("conversation")),
        outcome=row.get("outcome"),
        success=row.get("success"),
        step_count=int(row.get("step_count", 0)),
        started_at=to_datetime(row["started_at"]),
        completed_at=opt_datetime(row.get("completed_at")),
        metadata=plain(row.get("metadata") or {}),
    )


def _tool_call(row: Row) -> ToolCall:
    tool = row.get("tool")
    if isinstance(tool, dict):
        tool_name = str(cast("dict[str, Any]", tool).get("name"))
    else:
        tool_name = ref_str(tool).split(":", 1)[1]
    return ToolCall(
        id=ref_str(row["id"]),
        step_id=ref_str(row["step"]),
        tool=tool_name,
        arguments=plain(row.get("arguments") or {}),
        result=row.get("result"),
        success=row.get("success"),
        duration_ms=row.get("duration_ms"),
        created_at=to_datetime(row["created_at"]),
    )


def _step(row: Row, calls: list[Row], touched: list[Any]) -> Step:
    return Step(
        id=ref_str(row["id"]),
        trace_id=ref_str(row["trace"]),
        seq=int(row["seq"]),
        thought=row.get("thought"),
        action=row.get("action"),
        observation=row.get("observation"),
        started_at=to_datetime(row["started_at"]),
        duration_ms=row.get("duration_ms"),
        tool_calls=[_tool_call(c) for c in calls],
        touched_entity_ids=[ref_str(t) for t in touched],
        metadata=plain(row.get("metadata") or {}),
    )


@dataclass(slots=True)
class SurrealTraceRepository:
    db: SurrealConnection

    async def start(self, data: NewTrace) -> Trace:
        results = await run_script(
            self.db,
            """
            BEGIN;
            LET $trace = (CREATE trace:ulid() CONTENT {
                space: $space, agent_id: $agent_id, task: $task, conversation: $conversation,
                metadata: $metadata
            } RETURN AFTER)[0];
            IF $message IS NOT NONE { RELATE ($trace.id)->initiated_by->$message RETURN NONE; };
            SELECT * FROM trace WHERE id = $trace.id;
            COMMIT;
            """,
            {
                "space": data.space,
                "agent_id": data.agent_id,
                "task": data.task,
                "conversation": to_record_id(data.conversation_id)
                if data.conversation_id
                else None,
                "message": to_record_id(data.message_id) if data.message_id else None,
                "metadata": data.metadata,
            },
        )
        return _trace(rows_with(results, "task")[0])

    async def get(self, trace_id: str) -> Trace | None:
        rows = cast(
            "list[Row]",
            await run_one(
                self.db, "SELECT * FROM trace WHERE id = $id", {"id": to_record_id(trace_id)}
            ),
        )
        return _trace(rows[0]) if rows else None

    async def list(
        self,
        *,
        space: str | None = None,
        agent_id: str | None = None,
        conversation_id: str | None = None,
        status: TraceStatus | None = None,
        limit: int = 50,
    ) -> list[Trace]:
        clauses = ["true"]
        if space:
            clauses.append("space = $space")
        if agent_id:
            clauses.append("agent_id = $agent_id")
        if conversation_id:
            clauses.append("conversation = $conversation")
        if status:
            clauses.append("status = $status")
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                f"SELECT * FROM trace WHERE {' AND '.join(clauses)} "
                "ORDER BY started_at DESC LIMIT $limit",
                {
                    "space": space,
                    "agent_id": agent_id,
                    "conversation": to_record_id(conversation_id) if conversation_id else None,
                    "status": status.value if status else None,
                    "limit": limit,
                },
            ),
        )
        return [_trace(r) for r in rows]

    async def add_step(self, trace_id: str, data: NewStep) -> Step:
        results = await run_script(
            self.db,
            """
            BEGIN;
            LET $t = (SELECT id, step_count FROM ONLY $trace);
            LET $seq = $t.step_count + 1;
            LET $step = (CREATE step:ulid() CONTENT {
                trace: $t.id, seq: $seq, thought: $thought, action: $action,
                observation: $observation, duration_ms: $duration_ms, metadata: $metadata
            } RETURN AFTER)[0];
            UPDATE $t.id SET step_count = $seq RETURN NONE;
            FOR $call IN $calls {
                UPSERT type::record('tool', $call.tool)
                    SET name = $call.tool, call_count += 1 RETURN NONE;
                CREATE tool_call:ulid() CONTENT {
                    step: $step.id, tool: type::record('tool', $call.tool),
                    arguments: $call.arguments,
                    result: $call.result, success: $call.success, duration_ms: $call.duration_ms
                } RETURN NONE;
            };
            FOR $entity IN $touched {
                LET $dup = (SELECT VALUE id FROM touched
                    WHERE in = $step.id AND out = $entity AND how = $how LIMIT 1)[0];
                IF $dup IS NONE { RELATE ($step.id)->touched->$entity SET how = $how RETURN NONE; };
            };
            SELECT * FROM step WHERE id = $step.id;
            COMMIT;
            """,
            {
                "trace": to_record_id(trace_id),
                "thought": data.thought,
                "action": data.action,
                "observation": data.observation,
                "duration_ms": data.duration_ms,
                "metadata": data.metadata,
                "calls": [c.model_dump() for c in data.tool_calls],
                "touched": [to_record_id(e) for e in data.touched_entity_ids],
                "how": data.touched_how,
            },
        )
        try:
            row = rows_with(results, "seq")[0]
        except LookupError as exc:
            raise TraceNotFound(trace_id) from exc
        steps = await self._hydrate([row])
        return steps[0]

    async def steps(self, trace_id: str) -> list[Step]:
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                "SELECT * FROM step WHERE trace = $trace ORDER BY seq ASC",
                {"trace": to_record_id(trace_id)},
            ),
        )
        return await self._hydrate(rows)

    async def _hydrate(self, rows: list[Row]) -> list[Step]:
        if not rows:
            return []
        ids = [r["id"] for r in rows]
        calls = cast(
            "list[Row]",
            await run_one(
                self.db,
                "SELECT *, tool.name AS tool_name FROM tool_call WHERE step IN $ids "
                "ORDER BY created_at",
                {"ids": ids},
            ),
        )
        touched = cast(
            "list[Row]",
            await run_one(self.db, "SELECT in, out FROM touched WHERE in IN $ids", {"ids": ids}),
        )
        by_step_calls: dict[str, list[Row]] = {}
        for call in calls:
            call = {**call, "tool": {"name": call.get("tool_name")}}
            by_step_calls.setdefault(ref_str(call["step"]), []).append(call)
        by_step_touched: dict[str, list[Any]] = {}
        for edge in touched:
            by_step_touched.setdefault(ref_str(edge["in"]), []).append(edge["out"])
        return [
            _step(
                r,
                by_step_calls.get(ref_str(r["id"]), []),
                by_step_touched.get(ref_str(r["id"]), []),
            )
            for r in rows
        ]

    async def complete(
        self, trace_id: str, *, status: TraceStatus, outcome: str | None, success: bool | None
    ) -> Trace:
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                "UPDATE $id SET status = $status, outcome = $outcome, success = $success, "
                "completed_at = time::now() RETURN AFTER",
                {
                    "id": to_record_id(trace_id),
                    "status": status.value,
                    "outcome": outcome,
                    "success": success,
                },
            ),
        )
        if not rows:
            raise TraceNotFound(trace_id)
        return _trace(rows[0])

    async def set_embedding(self, trace_id: str, embedding: list[float], model: str) -> None:
        await run_one(
            self.db,
            "UPDATE $id SET embedding = $e, embedding_model = $m",
            {"id": to_record_id(trace_id), "e": embedding, "m": model},
        )

    async def count_by_status(self) -> dict[str, int]:
        rows = cast(
            "list[Row]",
            await run_one(self.db, "SELECT status, count() AS n FROM trace GROUP BY status"),
        )
        return {r["status"]: int(r["n"]) for r in rows}
