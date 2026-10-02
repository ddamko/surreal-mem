"""SurrealDB implementation of the retrieval reader.

Hybrid search runs the lexical (BM25) and vector (HNSW) legs as separate queries and fuses them in
Python with reciprocal rank fusion, which keeps the behaviour identical on the embedded 3.2 engine
used in tests and the 3.3 server.
"""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from surrealmem.retrieval.domain import MemoryType
from surrealmem.shared.infrastructure.surreal.connection import SurrealConnection, run_one
from surrealmem.shared.infrastructure.surreal.records import plain, to_record_id

if TYPE_CHECKING:
    from collections.abc import Sequence

type Row = dict[str, Any]

# table, text field, filters that keep only live records
_TABLES: dict[MemoryType, tuple[str, str, str]] = {
    MemoryType.FACT: ("fact", "statement", "status = 'active'"),
    MemoryType.ENTITY: ("entity", "name", "archived = false AND merged_into IS NONE"),
    MemoryType.MESSAGE: ("message", "content", "true"),
    MemoryType.SUMMARY: ("summary", "content", "true"),
    MemoryType.OBSERVATION: ("observation", "content", "status = 'active'"),
    MemoryType.TRACE: ("trace", "task", "true"),
}
_SPACE_SCOPED = {
    MemoryType.FACT,
    MemoryType.MESSAGE,
    MemoryType.SUMMARY,
    MemoryType.OBSERVATION,
    MemoryType.TRACE,
}


def _space_clause(memory_type: MemoryType) -> str:
    if memory_type in _SPACE_SCOPED:
        return "space IN $spaces"
    return "(array::len(spaces) = 0 OR array::any(spaces, |$s| $s IN $spaces))"


def _rows(value: Any) -> list[Row]:
    return [cast("Row", plain(r)) for r in cast("list[Row]", value or [])]


_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "do",
        "does",
        "did",
        "for",
        "from",
        "has",
        "have",
        "how",
        "i",
        "in",
        "is",
        "it",
        "its",
        "me",
        "my",
        "of",
        "on",
        "or",
        "our",
        "that",
        "the",
        "their",
        "there",
        "these",
        "this",
        "to",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "you",
        "your",
        "about",
        "into",
        "than",
        "then",
        "them",
        "they",
    ]
)
_TOKEN = re.compile(r"[a-z0-9][a-z0-9_.+#-]*")


def query_terms(text: str, *, limit: int = 8) -> list[str]:
    """Split a natural-language query into search terms. SurrealDB's ``@@`` matches all terms of a
    string (AND), so retrieval ORs one predicate per term instead."""
    seen: dict[str, None] = {}
    for token in _TOKEN.findall(text.lower()):
        if len(token) < 2 or token in _STOPWORDS:
            continue
        seen.setdefault(token, None)
        if len(seen) >= limit:
            break
    return list(seen)


def _or_predicates(field: str, terms: Sequence[str]) -> tuple[str, str, dict[str, str]]:
    """Return (where clause, score expression, variables) for OR-ed full-text predicates."""
    clauses = " OR ".join(f"{field} @{i + 1}@ $t{i}" for i in range(len(terms)))
    score = " + ".join(f"search::score({i + 1})" for i in range(len(terms)))
    return f"({clauses})", score, {f"t{i}": term for i, term in enumerate(terms)}


@dataclass(slots=True)
class SurrealMemoryReader:
    db: SurrealConnection

    async def lexical(
        self, memory_type: MemoryType, query: str, *, spaces: Sequence[str], limit: int
    ) -> list[Row]:
        table, field, live = _TABLES[memory_type]
        terms = query_terms(query)
        if not terms:
            return []
        where, score, variables = _or_predicates(field, terms)
        rows = await run_one(
            self.db,
            f"SELECT *, {score} AS score FROM {table} "
            f"WHERE {where} AND {live} AND {_space_clause(memory_type)} "
            "ORDER BY score DESC LIMIT $limit",
            {**variables, "spaces": list(spaces), "limit": limit},
        )
        return _rows(rows)

    async def vector(
        self,
        memory_type: MemoryType,
        embedding: Sequence[float],
        *,
        spaces: Sequence[str],
        limit: int,
    ) -> list[Row]:
        table, _field, live = _TABLES[memory_type]
        k = max(1, min(int(limit), 200))
        rows = await run_one(
            self.db,
            f"SELECT *, vector::distance::knn() AS distance FROM {table} "
            f"WHERE embedding <|{k},40|> $vec AND {live} AND {_space_clause(memory_type)}",
            {"vec": list(embedding), "spaces": list(spaces)},
        )
        return _rows(rows)

    async def link_entities(self, query: str, *, limit: int) -> list[Row]:
        terms = query_terms(query)
        if not terms:
            return []
        name_where, name_score, name_vars = _or_predicates("name", terms)
        by_name = _rows(
            await run_one(
                self.db,
                f"SELECT id, name, base_type, mention_count, {name_score} AS score "
                "FROM entity "
                f"WHERE {name_where} AND archived = false AND merged_into IS NONE "
                "ORDER BY score DESC LIMIT $limit",
                {**name_vars, "limit": limit},
            )
        )
        alias_where, alias_score, alias_vars = _or_predicates("alias", terms)
        by_alias = _rows(
            await run_one(
                self.db,
                "SELECT entity.id AS id, entity.name AS name, entity.base_type AS base_type, "
                f"entity.mention_count AS mention_count, alias, {alias_score} AS score "
                "FROM alias "
                f"WHERE {alias_where} AND entity.archived = false AND entity.merged_into IS NONE "
                "ORDER BY score DESC LIMIT $limit",
                {**alias_vars, "limit": limit},
            )
        )
        linked: dict[str, Row] = {}
        for row in by_name:
            linked[str(row["id"])] = {**row, "matched_on": "name"}
        for row in by_alias:
            linked.setdefault(str(row["id"]), {**row, "matched_on": f"alias:{row.get('alias')}"})
        ordered = sorted(
            linked.values(),
            key=lambda r: (float(r.get("score") or 0.0), int(r.get("mention_count") or 0)),
            reverse=True,
        )
        return ordered[:limit]

    async def expand(self, entity_ids: Sequence[str], *, hops: int) -> tuple[list[Row], list[Row]]:
        if not entity_ids:
            return [], []
        reached: dict[str, None] = dict.fromkeys(entity_ids)
        frontier = list(entity_ids)
        for _ in range(max(0, min(int(hops), 3))):
            if not frontier:
                break
            edges = _rows(
                await run_one(
                    self.db,
                    "SELECT in, out FROM related_to WHERE in IN $ids OR out IN $ids",
                    {"ids": [to_record_id(i) for i in frontier]},
                )
            )
            next_frontier: list[str] = []
            for edge in edges:
                for end in (str(edge["in"]), str(edge["out"])):
                    if end not in reached:
                        reached[end] = None
                        next_frontier.append(end)
            frontier = next_frontier
        ids = [to_record_id(i) for i in reached]
        entities = _rows(
            await run_one(
                self.db,
                "SELECT id, name, base_type, subtype, description, mention_count, salience, "
                "metrics FROM entity WHERE id IN $ids AND archived = false",
                {"ids": ids},
            )
        )
        relationships = _rows(
            await run_one(
                self.db,
                "SELECT id, in, out, kind, confidence, mention_count, proposed, fact "
                "FROM related_to WHERE in IN $ids AND out IN $ids",
                {"ids": ids},
            )
        )
        return entities, relationships

    async def facts_about(
        self, entity_ids: Sequence[str], *, spaces: Sequence[str], limit: int
    ) -> list[Row]:
        if not entity_ids:
            return []
        ids = [to_record_id(i) for i in entity_ids]
        return _rows(
            await run_one(
                self.db,
                "SELECT * FROM fact WHERE (subject IN $ids OR object IN $ids) "
                "AND status = 'active' AND space IN $spaces "
                "ORDER BY salience DESC, recorded_at DESC LIMIT $limit",
                {"ids": ids, "spaces": list(spaces), "limit": limit},
            )
        )

    async def recent_messages(self, conversation_id: str, *, limit: int) -> list[Row]:
        rows = _rows(
            await run_one(
                self.db,
                "SELECT * FROM message WHERE conversation = $cid ORDER BY seq DESC LIMIT $limit",
                {"cid": to_record_id(conversation_id), "limit": limit},
            )
        )
        rows.reverse()
        return rows

    async def touch_facts(self, fact_ids: Sequence[str]) -> None:
        if not fact_ids:
            return
        await run_one(
            self.db,
            "UPDATE fact SET access_count += 1, last_accessed_at = time::now() WHERE id IN $ids",
            {"ids": [to_record_id(i) for i in fact_ids]},
        )
