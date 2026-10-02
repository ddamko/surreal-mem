"""Hybrid retrieval, graph expansion, scoring and context packing (ADR-0012)."""

import math
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from surrealmem.retrieval.domain import (
    ContextPack,
    GraphContext,
    LinkedEntity,
    MemoryReader,
    MemoryType,
    RetrievalQuery,
    RetrievedItem,
    ScoreBreakdown,
    SearchResult,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from surrealmem.shared.application import Embedder

PREFERENCE_KIND = "PREFERS"
_TEXT_FIELD = {
    MemoryType.FACT: "statement",
    MemoryType.ENTITY: "name",
    MemoryType.MESSAGE: "content",
    MemoryType.SUMMARY: "content",
    MemoryType.OBSERVATION: "content",
    MemoryType.TRACE: "task",
}
_TIME_FIELD = {
    MemoryType.FACT: "recorded_at",
    MemoryType.ENTITY: "last_seen_at",
    MemoryType.MESSAGE: "created_at",
    MemoryType.SUMMARY: "created_at",
    MemoryType.OBSERVATION: "created_at",
    MemoryType.TRACE: "started_at",
}


@dataclass(frozen=True, slots=True)
class ScoringWeights:
    rrf: float = 0.55
    graph: float = 0.20
    recency: float = 0.10
    salience: float = 0.075
    confidence: float = 0.075
    recency_half_life_days: float = 90.0
    rrf_k: int = 60


def estimate_tokens(text: str) -> int:
    """Cheap, model-agnostic estimate: about four characters per token."""
    return max(1, math.ceil(len(text) / 4))


def _parse_time(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _entity_text(row: dict[str, Any]) -> str:
    name = str(row.get("name", ""))
    subtype = row.get("subtype")
    description = row.get("description")
    head = f"{name} ({row.get('base_type')}{':' + str(subtype) if subtype else ''})"
    return f"{head}: {description}" if description else head


def _item_text(memory_type: MemoryType, row: dict[str, Any]) -> str:
    if memory_type is MemoryType.ENTITY:
        return _entity_text(row)
    if memory_type is MemoryType.MESSAGE:
        return f"[{row.get('role')}] {row.get('content', '')}"
    return str(row.get(_TEXT_FIELD[memory_type], ""))


@dataclass(slots=True)
class Retriever:
    reader: MemoryReader
    embedder: Embedder | None = None
    weights: ScoringWeights = field(default_factory=ScoringWeights)
    now: datetime | None = None

    async def search(self, query: RetrievalQuery) -> SearchResult:
        timings: dict[str, float] = {}
        started = time.perf_counter()
        items, graph = await self._retrieve(query, timings)
        timings["total"] = (time.perf_counter() - started) * 1000
        return SearchResult(
            query=query.text, spaces=query.spaces, items=items, graph=graph, timings_ms=timings
        )

    async def context(self, query: RetrievalQuery) -> ContextPack:
        timings: dict[str, float] = {}
        started = time.perf_counter()
        items, graph = await self._retrieve(query, timings)
        pack = pack_context(query, items, graph)
        await self.reader.touch_facts([i.id for i in pack.facts + pack.preferences])
        timings["total"] = (time.perf_counter() - started) * 1000
        return pack.model_copy(update={"timings_ms": timings})

    async def _retrieve(
        self, query: RetrievalQuery, timings: dict[str, float]
    ) -> tuple[list[RetrievedItem], GraphContext]:
        spaces = query.spaces
        per_type = max(query.limit, 10)
        embedding: list[float] | None = None
        if query.vector and self.embedder is not None:
            t0 = time.perf_counter()
            embedding = (await self.embedder.embed_queries([query.text]))[0]
            timings["embed"] = (time.perf_counter() - t0) * 1000

        candidates: dict[str, _Candidate] = {}
        t0 = time.perf_counter()
        for memory_type in query.memory_types:
            if query.lexical:
                rows = await self.reader.lexical(
                    memory_type, query.text, spaces=spaces, limit=per_type
                )
                for rank, row in enumerate(rows, start=1):
                    cand = _candidate(candidates, memory_type, row)
                    cand.lexical_rank = rank
                    cand.lexical_score = float(row.get("score") or 0.0)
            if embedding is not None:
                rows = await self.reader.vector(
                    memory_type, embedding, spaces=spaces, limit=per_type
                )
                for rank, row in enumerate(rows, start=1):
                    cand = _candidate(candidates, memory_type, row)
                    cand.vector_rank = rank
                    cand.vector_similarity = 1.0 - float(row.get("distance") or 0.0)
        timings["hybrid"] = (time.perf_counter() - t0) * 1000

        graph = GraphContext()
        if query.graph:
            t0 = time.perf_counter()
            linked_rows = await self.reader.link_entities(query.text, limit=5)
            linked = [
                LinkedEntity(
                    id=str(r["id"]),
                    name=str(r.get("name")),
                    base_type=str(r.get("base_type")),
                    score=float(r.get("score") or 0.0),
                    matched_on=str(r.get("matched_on", "name")),
                )
                for r in linked_rows
            ]
            # Entities surfaced by the hybrid legs also seed the expansion.
            seed_ids = list(
                dict.fromkeys(
                    [linked_entity.id for linked_entity in linked]
                    + [
                        c.id
                        for c in candidates.values()
                        if c.type is MemoryType.ENTITY and (c.lexical_rank or 99) <= 3
                    ]
                )
            )
            entities, relationships = await self.reader.expand(seed_ids, hops=query.hops)
            graph = GraphContext(linked=linked, entities=entities, relationships=relationships)
            reached = {str(e["id"]) for e in entities}
            direct = set(seed_ids)
            if MemoryType.FACT in query.memory_types and reached:
                for row in await self.reader.facts_about(
                    list(reached), spaces=spaces, limit=per_type * 2
                ):
                    cand = _candidate(candidates, MemoryType.FACT, row)
                    subject = str(row.get("subject"))
                    obj = str(row.get("object")) if row.get("object") else None
                    cand.graph = max(
                        cand.graph,
                        1.0 if subject in direct or obj in direct else 0.6,
                    )
            for cand in candidates.values():
                if cand.type is MemoryType.ENTITY and cand.id in reached:
                    cand.graph = max(cand.graph, 1.0 if cand.id in direct else 0.6)
            timings["graph"] = (time.perf_counter() - t0) * 1000

        items = self._score(candidates.values())
        items.sort(key=lambda i: i.score.final, reverse=True)
        return items[: query.limit * 3], graph

    def _score(self, candidates: Iterable[_Candidate]) -> list[RetrievedItem]:
        now = self.now or datetime.now(UTC)
        w = self.weights
        scored: list[RetrievedItem] = []
        for cand in candidates:
            rrf = 0.0
            if cand.lexical_rank is not None:
                rrf += 1.0 / (w.rrf_k + cand.lexical_rank)
            if cand.vector_rank is not None:
                rrf += 1.0 / (w.rrf_k + cand.vector_rank)
            # Normalize so that rank 1 in both legs is 1.0.
            rrf_norm = rrf / (2.0 / (w.rrf_k + 1))
            when = _parse_time(cand.row.get(_TIME_FIELD[cand.type]))
            recency = 0.0
            if when is not None:
                age_days = max(0.0, (now - when).total_seconds() / 86400)
                recency = 0.5 ** (age_days / w.recency_half_life_days)
            salience = float(cand.row.get("salience") or 0.5)
            confidence = float(cand.row.get("confidence") or 1.0)
            final = (
                w.rrf * rrf_norm
                + w.graph * cand.graph
                + w.recency * recency
                + w.salience * salience
                + w.confidence * confidence
            )
            via: list[str] = []
            if cand.lexical_rank is not None:
                via.append("lexical")
            if cand.vector_rank is not None:
                via.append("vector")
            if cand.graph > 0:
                via.append("graph")
            scored.append(
                RetrievedItem(
                    id=cand.id,
                    type=cand.type,
                    text=_item_text(cand.type, cand.row),
                    space=cand.row.get("space"),
                    created_at=when,
                    record=cand.row,
                    via=via,
                    score=ScoreBreakdown(
                        lexical_rank=cand.lexical_rank,
                        lexical_score=cand.lexical_score,
                        vector_rank=cand.vector_rank,
                        vector_similarity=cand.vector_similarity,
                        rrf=round(rrf_norm, 4),
                        graph=cand.graph,
                        recency=round(recency, 4),
                        salience=salience,
                        confidence=confidence,
                        final=round(final, 4),
                    ),
                )
            )
        return scored


@dataclass(slots=True)
class _Candidate:
    id: str
    type: MemoryType
    row: dict[str, Any]
    lexical_rank: int | None = None
    lexical_score: float | None = None
    vector_rank: int | None = None
    vector_similarity: float | None = None
    graph: float = 0.0


def _candidate(
    store: dict[str, _Candidate], memory_type: MemoryType, row: dict[str, Any]
) -> _Candidate:
    key = str(row["id"])
    if key not in store:
        store[key] = _Candidate(id=key, type=memory_type, row=row)
    return store[key]


def pack_context(
    query: RetrievalQuery, items: Sequence[RetrievedItem], graph: GraphContext
) -> ContextPack:
    """Fill sections in priority order until the token budget is spent, then render markdown."""
    budget = query.token_budget
    used = 0
    dropped = 0
    sections: dict[str, list[RetrievedItem]] = {
        "preferences": [],
        "facts": [],
        "entities": [],
        "summaries": [],
        "observations": [],
        "messages": [],
    }
    caps = {
        "preferences": 8,
        "facts": 15,
        "entities": 10,
        "summaries": 3,
        "observations": 5,
        "messages": 6,
    }

    def section_of(item: RetrievedItem) -> str:
        if item.type is MemoryType.FACT:
            return "preferences" if item.record.get("kind") == PREFERENCE_KIND else "facts"
        return {
            MemoryType.ENTITY: "entities",
            MemoryType.SUMMARY: "summaries",
            MemoryType.OBSERVATION: "observations",
            MemoryType.MESSAGE: "messages",
            MemoryType.TRACE: "observations",
        }[item.type]

    ordered = sorted(items, key=lambda i: i.score.final, reverse=True)
    priority = ["preferences", "facts", "entities", "summaries", "observations", "messages"]
    for name in priority:
        for item in ordered:
            if section_of(item) != name or len(sections[name]) >= caps[name]:
                continue
            cost = estimate_tokens(item.text) + 4
            if used + cost > budget:
                dropped += 1
                continue
            sections[name].append(item)
            used += cost

    markdown = render_markdown(query, sections, graph)
    return ContextPack(
        query=query.text,
        spaces=query.spaces,
        preferences=sections["preferences"],
        facts=sections["facts"],
        entities=sections["entities"],
        summaries=sections["summaries"],
        messages=sections["messages"],
        observations=sections["observations"],
        graph=graph,
        dropped=dropped,
        token_budget=budget,
        tokens_used=used,
        markdown=markdown,
    )


def render_markdown(
    query: RetrievalQuery, sections: dict[str, list[RetrievedItem]], graph: GraphContext
) -> str:
    lines: list[str] = [
        "## Memory context",
        f"_Query: {query.text}_ (spaces: {', '.join(query.spaces)})",
    ]
    titles = {
        "preferences": "Preferences",
        "facts": "Facts",
        "entities": "Entities",
        "summaries": "Conversation summaries",
        "observations": "Observations",
        "messages": "Relevant messages",
    }
    for name, title in titles.items():
        items = sections.get(name) or []
        if not items:
            continue
        lines.append(f"\n### {title}")
        for item in items:
            suffix = ""
            if item.type is MemoryType.FACT and item.record.get("valid_from"):
                suffix = f" (since {str(item.record['valid_from'])[:10]})"
            lines.append(f"- {item.text}{suffix}")
    if graph.relationships:
        names = {str(e["id"]): str(e.get("name")) for e in graph.entities}
        lines.append("\n### Relationships")
        for rel in graph.relationships[:20]:
            src = names.get(str(rel.get("in")), str(rel.get("in")))
            dst = names.get(str(rel.get("out")), str(rel.get("out")))
            lines.append(f"- {src} —{rel.get('kind')}→ {dst}")
    return "\n".join(lines)
