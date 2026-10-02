"""Merge candidates and the entity merge transaction (ADR-0007)."""

from dataclasses import dataclass
from typing import cast

from surrealmem.knowledge.adapters.surreal.mappers import Row, entity_from_row
from surrealmem.knowledge.domain import Entity, EntityNotFound, MergeCandidate, MergeStatus
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


def _candidate(row: Row) -> MergeCandidate:
    return MergeCandidate(
        id=ref_str(row["id"]),
        left_id=ref_str(row["left"]),
        right_id=ref_str(row["right"]),
        score=float(row["score"]),
        reason=row["reason"],
        status=MergeStatus(row.get("status", "pending")),
        decided_at=opt_datetime(row.get("decided_at")),
        decided_by=row.get("decided_by"),
        created_at=to_datetime(row["created_at"]),
        metadata=plain(row.get("metadata") or {}),
    )


@dataclass(slots=True)
class SurrealMergeCandidateRepository:
    db: SurrealConnection

    async def propose(
        self, left_id: str, right_id: str, *, score: float, reason: str
    ) -> MergeCandidate:
        results = await run_script(
            self.db,
            """
            LET $found = (SELECT * FROM merge_candidate
                WHERE (left = $l AND right = $r) OR (left = $r AND right = $l) LIMIT 1);
            IF array::len($found) > 0 {
                UPDATE $found[0].id SET score = math::max([score, $score]) RETURN AFTER;
            } ELSE {
                CREATE merge_candidate:ulid() CONTENT
                    { left: $l, right: $r, score: $score, reason: $reason } RETURN AFTER;
            };
            """,
            {
                "l": to_record_id(left_id),
                "r": to_record_id(right_id),
                "score": score,
                "reason": reason,
            },
        )
        return _candidate(rows_with(results, "score")[0])

    async def get(self, candidate_id: str) -> MergeCandidate | None:
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                "SELECT * FROM merge_candidate WHERE id = $id",
                {"id": to_record_id(candidate_id)},
            ),
        )
        return _candidate(rows[0]) if rows else None

    async def list(
        self, *, status: MergeStatus | None = None, limit: int = 100
    ) -> list[MergeCandidate]:
        clause = "WHERE status = $status" if status is not None else ""
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                f"SELECT * FROM merge_candidate {clause} ORDER BY score DESC LIMIT $limit",
                {"status": status.value if status else None, "limit": limit},
            ),
        )
        return [_candidate(r) for r in rows]

    async def decide(
        self, candidate_id: str, *, status: MergeStatus, decided_by: str
    ) -> MergeCandidate:
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                "UPDATE $id SET status = $status, decided_at = time::now(), decided_by = $by "
                "RETURN AFTER",
                {"id": to_record_id(candidate_id), "status": status.value, "by": decided_by},
            ),
        )
        if not rows:
            raise LookupError(candidate_id)
        return _candidate(rows[0])


_MERGE_SCRIPT = """
BEGIN;
LET $loser_row = (SELECT * FROM ONLY $loser);
-- outgoing semantic edges (FOR must iterate a bound variable, not an inline subquery)
LET $out_edges = (SELECT * FROM related_to WHERE in = $loser);
FOR $e IN $out_edges {
    LET $out = $e.out;
    IF $out != $winner {
        LET $dup = (SELECT VALUE id FROM related_to
            WHERE in = $winner AND out = $out AND kind = $e.kind LIMIT 1)[0];
        IF $dup IS NONE {
            RELATE $winner->related_to->$out SET kind = $e.kind, confidence = $e.confidence,
                proposed = $e.proposed, spaces = $e.spaces, mention_count = $e.mention_count,
                fact = $e.fact, metadata = $e.metadata RETURN NONE;
        } ELSE {
            UPDATE $dup SET mention_count += $e.mention_count,
                spaces = array::union(spaces, $e.spaces),
                confidence = math::max([confidence, $e.confidence]) RETURN NONE;
        };
    };
    DELETE $e.id;
};
-- incoming semantic edges
LET $in_edges = (SELECT * FROM related_to WHERE out = $loser);
FOR $e IN $in_edges {
    LET $in = $e.in;
    IF $in != $winner {
        LET $dup = (SELECT VALUE id FROM related_to
            WHERE in = $in AND out = $winner AND kind = $e.kind LIMIT 1)[0];
        IF $dup IS NONE {
            RELATE $in->related_to->$winner SET kind = $e.kind, confidence = $e.confidence,
                proposed = $e.proposed, spaces = $e.spaces, mention_count = $e.mention_count,
                fact = $e.fact, metadata = $e.metadata RETURN NONE;
        } ELSE {
            UPDATE $dup SET mention_count += $e.mention_count,
                spaces = array::union(spaces, $e.spaces),
                confidence = math::max([confidence, $e.confidence]) RETURN NONE;
        };
    };
    DELETE $e.id;
};
-- facts, mentions, provenance, touched, aliases
UPDATE fact SET subject = $winner WHERE subject = $loser RETURN NONE;
UPDATE fact SET object = $winner WHERE object = $loser RETURN NONE;
LET $mention_rows = (SELECT * FROM mentions WHERE out = $loser);
FOR $m IN $mention_rows {
    LET $msg = $m.in;
    IF (SELECT VALUE id FROM mentions WHERE in = $msg AND out = $winner LIMIT 1)[0] IS NONE {
        RELATE $msg->mentions->$winner SET confidence = $m.confidence RETURN NONE;
    };
    DELETE $m.id;
};
LET $source_rows = (SELECT * FROM extracted_from WHERE in = $loser);
FOR $x IN $source_rows {
    LET $msg = $x.out;
    IF (SELECT VALUE id FROM extracted_from WHERE in = $winner AND out = $msg LIMIT 1)[0] IS NONE {
        RELATE $winner->extracted_from->$msg SET extractor = $x.extractor, model = $x.model,
            confidence = $x.confidence RETURN NONE;
    };
    DELETE $x.id;
};
LET $touched_rows = (SELECT * FROM touched WHERE out = $loser);
FOR $t IN $touched_rows {
    LET $step = $t.in;
    LET $dup_t = (SELECT VALUE id FROM touched
        WHERE in = $step AND out = $winner AND how = $t.how LIMIT 1)[0];
    IF $dup_t IS NONE {
        RELATE $step->touched->$winner SET how = $t.how RETURN NONE;
    };
    DELETE $t.id;
};
LET $alias_rows = (SELECT * FROM alias WHERE entity = $loser);
FOR $a IN $alias_rows {
    LET $dup_a = (SELECT VALUE id FROM alias
        WHERE entity = $winner AND alias_key = $a.alias_key LIMIT 1)[0];
    IF $dup_a IS NONE {
        CREATE alias CONTENT { entity: $winner, alias: $a.alias, source: 'merge' } RETURN NONE;
    };
    DELETE $a.id;
};
LET $dup_name = (SELECT VALUE id FROM alias
    WHERE entity = $winner AND alias_key = $loser_row.name_key LIMIT 1)[0];
IF $dup_name IS NONE {
    CREATE alias CONTENT { entity: $winner, alias: $loser_row.name, source: 'merge' } RETURN NONE;
};
UPDATE $loser SET archived = true, merged_into = $winner RETURN NONE;
RELATE $loser->same_as->$winner SET reason = $reason, score = $score, merged_by = $by RETURN NONE;
UPDATE $winner SET
    aliases = array::distinct(
        array::concat(array::concat(aliases, $loser_row.aliases), [$loser_row.name])),
    spaces = array::union(spaces, $loser_row.spaces),
    mention_count += $loser_row.mention_count,
    description = description ?? $loser_row.description,
    first_seen_at = IF first_seen_at IS NONE { $loser_row.first_seen_at }
        ELSE { IF $loser_row.first_seen_at IS NONE OR first_seen_at <= $loser_row.first_seen_at
               { first_seen_at } ELSE { $loser_row.first_seen_at } }
RETURN AFTER;
COMMIT;
"""


@dataclass(slots=True)
class SurrealEntityMerger:
    db: SurrealConnection

    async def merge(
        self, loser_id: str, winner_id: str, *, reason: str, score: float | None, merged_by: str
    ) -> Entity:
        if loser_id == winner_id:
            raise ValueError("cannot merge an entity into itself")
        results = await run_script(
            self.db,
            _MERGE_SCRIPT,
            {
                "loser": to_record_id(loser_id),
                "winner": to_record_id(winner_id),
                "reason": reason,
                "score": score,
                "by": merged_by,
            },
        )
        try:
            rows = rows_with(results, "name_key")
        except LookupError as exc:
            raise EntityNotFound(winner_id) from exc
        return entity_from_row(rows[-1])
