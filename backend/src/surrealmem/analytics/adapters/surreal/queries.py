"""Read queries behind the dashboard's analytics, graph and projection endpoints."""

from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from surrealmem.shared.infrastructure.surreal.connection import SurrealConnection, run_one
from surrealmem.shared.infrastructure.surreal.records import plain, to_record_id

if TYPE_CHECKING:
    from collections.abc import Sequence

type Row = dict[str, Any]
_LIVE = "archived = false AND merged_into IS NONE"


def _rows(value: Any) -> list[Row]:
    return [cast("Row", plain(r)) for r in cast("list[Row]", value or [])]


@dataclass(slots=True)
class SurrealAnalyticsQueries:
    db: SurrealConnection

    async def graph(
        self,
        *,
        space: str | None,
        base_types: Sequence[str] | None,
        kinds: Sequence[str] | None,
        limit: int,
        min_mentions: int = 0,
    ) -> tuple[list[Row], list[Row]]:
        clauses = [_LIVE, "mention_count >= $min_mentions"]
        if space:
            clauses.append("$space IN spaces")
        if base_types:
            clauses.append("base_type IN $types")
        nodes = _rows(
            await run_one(
                self.db,
                "SELECT id, name, base_type, subtype, mention_count, salience, metrics, spaces, "
                f"projection FROM entity WHERE {' AND '.join(clauses)} "
                "ORDER BY mention_count DESC LIMIT $limit",
                {
                    "space": space,
                    "types": list(base_types or []),
                    "limit": limit,
                    "min_mentions": min_mentions,
                },
            )
        )
        ids = [to_record_id(str(n["id"])) for n in nodes]
        kind_clause = "AND kind IN $kinds" if kinds else ""
        edges = _rows(
            await run_one(
                self.db,
                "SELECT id, in, out, kind, confidence, mention_count, proposed, fact "
                f"FROM related_to WHERE in IN $ids AND out IN $ids {kind_clause}",
                {"ids": ids, "kinds": list(kinds or [])},
            )
        )
        return nodes, edges

    async def neighbors(self, entity_id: str, *, hops: int) -> tuple[list[Row], list[Row]]:
        reached: dict[str, None] = {entity_id: None}
        frontier = [entity_id]
        for _ in range(max(1, min(hops, 3))):
            if not frontier:
                break
            edges = _rows(
                await run_one(
                    self.db,
                    "SELECT in, out FROM related_to WHERE in IN $ids OR out IN $ids",
                    {"ids": [to_record_id(i) for i in frontier]},
                )
            )
            nxt: list[str] = []
            for e in edges:
                for end in (str(e["in"]), str(e["out"])):
                    if end not in reached:
                        reached[end] = None
                        nxt.append(end)
            frontier = nxt
        ids = [to_record_id(i) for i in reached]
        nodes = _rows(
            await run_one(
                self.db,
                "SELECT id, name, base_type, subtype, mention_count, salience, metrics, spaces "
                f"FROM entity WHERE id IN $ids AND {_LIVE}",
                {"ids": ids},
            )
        )
        edges = _rows(
            await run_one(
                self.db,
                "SELECT id, in, out, kind, confidence, mention_count, proposed, fact "
                "FROM related_to WHERE in IN $ids AND out IN $ids",
                {"ids": ids},
            )
        )
        return nodes, edges

    async def shortest_path(self, source: str, target: str, *, max_depth: int = 6) -> list[Row]:
        """Breadth-first search over related_to (both directions); returns the edges on the path."""
        if source == target:
            return []
        parents: dict[str, tuple[str, Row]] = {}
        seen = {source}
        frontier = deque([source])
        depth = 0
        while frontier and depth < max_depth:
            level = list(frontier)
            frontier.clear()
            edges = _rows(
                await run_one(
                    self.db,
                    "SELECT id, in, out, kind FROM related_to WHERE in IN $ids OR out IN $ids",
                    {"ids": [to_record_id(i) for i in level]},
                )
            )
            for e in edges:
                a, b = str(e["in"]), str(e["out"])
                for here, there in ((a, b), (b, a)):
                    if here in seen and there not in seen:
                        seen.add(there)
                        parents[there] = (here, e)
                        frontier.append(there)
                        if there == target:
                            path: list[Row] = []
                            node = target
                            while node != source:
                                prev, edge = parents[node]
                                path.append(edge)
                                node = prev
                            path.reverse()
                            return path
            depth += 1
        return []

    async def timeline(self, *, space: str | None, days: int) -> dict[str, list[Row]]:
        window = max(1, min(days, 365))
        out: dict[str, list[Row]] = {}
        for table, field, scope in (
            ("entity", "created_at", "$space IN spaces" if space else "true"),
            ("fact", "recorded_at", "space = $space" if space else "true"),
            ("message", "created_at", "space = $space" if space else "true"),
            ("conversation", "started_at", "space = $space" if space else "true"),
        ):
            rows = _rows(
                await run_one(
                    self.db,
                    f"SELECT time::group({field}, 'day') AS day, count() AS n FROM {table} "
                    f"WHERE {field} > time::now() - {window}d AND {scope} "
                    "GROUP BY day ORDER BY day",
                    {"space": space},
                )
            )
            out[table] = [{"day": str(r["day"])[:10], "n": int(r["n"])} for r in rows]
        return out

    async def centrality(self, *, metric: str, space: str | None, limit: int) -> list[Row]:
        if metric not in {"pagerank", "degree", "betweenness", "in_degree", "out_degree"}:
            raise ValueError(
                "metric must be pagerank, degree, betweenness, in_degree or out_degree"
            )
        scope = "AND $space IN spaces" if space else ""
        return _rows(
            await run_one(
                self.db,
                f"SELECT id, name, base_type, mention_count, metrics.{metric} AS value, "
                f"metrics.community AS community FROM entity WHERE {_LIVE} {scope} "
                f"AND metrics.{metric} IS NOT NONE ORDER BY value DESC LIMIT $limit",
                {"space": space, "limit": limit},
            )
        )

    async def communities(self, *, space: str | None, limit: int) -> list[Row]:
        scope = "AND $space IN spaces" if space else ""
        rows = _rows(
            await run_one(
                self.db,
                f"SELECT metrics.community AS community, count() AS size, "
                "array::group(name) AS members, math::sum(mention_count) AS mentions "
                f"FROM entity WHERE {_LIVE} {scope} AND metrics.community IS NOT NONE "
                "GROUP BY community ORDER BY size DESC LIMIT $limit",
                {"space": space, "limit": limit},
            )
        )
        for r in rows:
            members = cast("list[Any]", r.get("members") or [])
            r["members"] = [str(m) for m in members[:12]]
        return rows

    async def kinds(self, *, space: str | None) -> list[Row]:
        scope = "WHERE $space IN spaces" if space else ""
        return _rows(
            await run_one(
                self.db,
                f"SELECT kind, count() AS n, math::mean(confidence) AS confidence, "
                f"math::sum(mention_count) AS mentions FROM related_to {scope} "
                "GROUP BY kind ORDER BY n DESC",
                {"space": space},
            )
        )

    async def flows(self, *, space: str | None) -> list[Row]:
        scope = "WHERE $space IN spaces" if space else ""
        return _rows(
            await run_one(
                self.db,
                "SELECT in.base_type AS source, out.base_type AS target, kind, count() AS n "
                f"FROM related_to {scope} GROUP BY source, target, kind ORDER BY n DESC",
                {"space": space},
            )
        )

    async def cooccurrence(self, *, space: str | None, limit: int) -> list[Row]:
        """Entity pairs mentioned in the same message, counted over mentions edges."""
        scope = "AND in.space = $space" if space else ""
        rows = _rows(
            await run_one(
                self.db,
                "SELECT in AS message, array::group(out) AS entities FROM mentions "
                f"WHERE true {scope} GROUP BY message LIMIT 5000",
                {"space": space},
            )
        )
        pairs: dict[tuple[str, str], int] = {}
        for r in rows:
            ents = sorted({str(e) for e in cast("list[Any]", r.get("entities") or [])})
            for i, a in enumerate(ents):
                for b in ents[i + 1 :]:
                    pairs[(a, b)] = pairs.get((a, b), 0) + 1
        top = sorted(pairs.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        ids = {i for pair, _ in top for i in pair}
        names: dict[str, str] = {}
        if ids:
            for r in _rows(
                await run_one(
                    self.db,
                    "SELECT id, name, base_type FROM entity WHERE id IN $ids",
                    {"ids": [to_record_id(i) for i in ids]},
                )
            ):
                names[str(r["id"])] = str(r["name"])
        return [
            {"a": a, "b": b, "a_name": names.get(a, a), "b_name": names.get(b, b), "n": n}
            for (a, b), n in top
        ]

    async def fact_health(self, *, space: str | None) -> Row:
        scope = "WHERE space = $space" if space else ""
        by_status = _rows(
            await run_one(
                self.db,
                f"SELECT status, count() AS n FROM fact {scope} GROUP BY status",
                {"space": space},
            )
        )
        confidence = _rows(
            await run_one(
                self.db,
                "SELECT math::floor(confidence * 10) / 10 AS bucket, count() AS n "
                f"FROM fact {scope} GROUP BY bucket ORDER BY bucket",
                {"space": space},
            )
        )
        salience = _rows(
            await run_one(
                self.db,
                f"SELECT math::floor(salience * 10) / 10 AS bucket, count() AS n FROM fact {scope} "
                "GROUP BY bucket ORDER BY bucket",
                {"space": space},
            )
        )
        contradictions = _rows(
            await run_one(
                self.db,
                "SELECT id, content, about, facts, created_at FROM observation "
                "WHERE kind = 'contradiction' AND status = 'active' "
                + ("AND space = $space " if space else "")
                + "ORDER BY created_at DESC LIMIT 50",
                {"space": space},
            )
        )
        flagged = _rows(
            await run_one(
                self.db,
                f"SELECT count() AS n FROM fact {scope} "
                + ("AND" if space else "WHERE")
                + " 'contradiction' IN flags GROUP ALL",
                {"space": space},
            )
        )
        return {
            "by_status": {str(r["status"]): int(r["n"]) for r in by_status},
            "confidence": [{"bucket": float(r["bucket"]), "n": int(r["n"])} for r in confidence],
            "salience": [{"bucket": float(r["bucket"]), "n": int(r["n"])} for r in salience],
            "contradictions": contradictions,
            "flagged": int(flagged[0]["n"]) if flagged else 0,
        }

    async def projection(self, *, table: str, space: str | None, limit: int) -> list[Row]:
        if table == "entity":
            scope = "AND $space IN spaces" if space else ""
            return _rows(
                await run_one(
                    self.db,
                    "SELECT id, name AS label, base_type, subtype, mention_count, salience, "
                    f"metrics.community AS community, projection FROM entity "
                    f"WHERE {_LIVE} AND projection.x IS NOT NONE {scope} LIMIT $limit",
                    {"space": space, "limit": limit},
                )
            )
        if table == "fact":
            scope = "AND space = $space" if space else ""
            return _rows(
                await run_one(
                    self.db,
                    "SELECT id, statement AS label, kind, subject.name AS subject, "
                    "subject.base_type AS base_type, salience, confidence, status, projection "
                    f"FROM fact WHERE status = 'active' AND projection.x IS NOT NONE {scope} "
                    "LIMIT $limit",
                    {"space": space, "limit": limit},
                )
            )
        raise ValueError("table must be entity or fact")

    async def mentions_for_conversation(self, conversation_id: str) -> list[Row]:
        return _rows(
            await run_one(
                self.db,
                "SELECT in AS message, out AS entity, out.name AS name, "
                "out.base_type AS base_type, confidence FROM mentions "
                "WHERE in.conversation = $cid",
                {"cid": to_record_id(conversation_id)},
            )
        )
