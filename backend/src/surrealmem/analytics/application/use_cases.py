# pyright: reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportAttributeAccessIssue=false
"""Graph metrics (networkx) and embedding projections (UMAP) materialized onto records.

See ADR-0020 and ADR-0022.
"""

import math
from dataclasses import dataclass
from typing import Any, cast

import networkx as nx

from surrealmem.analytics.domain import (
    EmbeddingReader,
    EntityNames,
    GraphReader,
    MetricsReport,
    MetricsWriter,
    ProjectionReport,
    ProjectionWriter,
)


@dataclass(slots=True)
class ComputeGraphMetrics:
    reader: GraphReader
    writer: MetricsWriter
    names: EntityNames | None = None
    betweenness_samples: int = 200

    async def __call__(self) -> MetricsReport:
        ids = await self.reader.entity_ids()
        edges = await self.reader.edges()
        directed: nx.DiGraph[str] = nx.DiGraph()
        directed.add_nodes_from(ids)
        for source, target, weight in edges:
            if directed.has_edge(source, target):
                directed[source][target]["weight"] += weight
            else:
                directed.add_edge(source, target, weight=weight)
        undirected = directed.to_undirected()
        n = directed.number_of_nodes()
        if n == 0:
            return MetricsReport(nodes=0, edges=0, communities=0, updated=0)

        pagerank = (
            nx.pagerank(directed, weight="weight")
            if directed.number_of_edges()
            else dict.fromkeys(ids, 1.0 / n)
        )
        k = min(self.betweenness_samples, n) if n > self.betweenness_samples else None
        betweenness = nx.betweenness_centrality(undirected, k=k, seed=42, normalized=True)
        communities = (
            nx.community.louvain_communities(undirected, weight="weight", seed=42)
            if undirected.number_of_edges()
            else [{node} for node in undirected.nodes]
        )
        community_of: dict[str, int] = {}
        for index, members in enumerate(sorted(communities, key=lambda c: (-len(c), min(c)))):
            for member in members:
                community_of[member] = index
        clustering = cast("dict[str, float]", nx.clustering(undirected))

        metrics: dict[str, dict[str, Any]] = {}
        for node in directed.nodes:
            metrics[node] = {
                "pagerank": round(float(pagerank.get(node, 0.0)), 6),
                "degree": int(undirected.degree(node)),
                "in_degree": int(directed.in_degree(node)),
                "out_degree": int(directed.out_degree(node)),
                "betweenness": round(float(betweenness.get(node, 0.0)), 6),
                "clustering": round(float(clustering.get(node, 0.0)), 4),
                "community": community_of.get(node, -1),
            }
        updated = await self.writer.write_metrics(metrics)
        top = sorted(
            ((node, m["pagerank"]) for node, m in metrics.items()), key=lambda p: p[1], reverse=True
        )[:10]
        if self.names is not None:
            labels = await self.names.names([node for node, _ in top])
            top = [(labels.get(node, node), score) for node, score in top]
        return MetricsReport(
            nodes=n,
            edges=directed.number_of_edges(),
            communities=len(communities),
            updated=updated,
            top_pagerank=top,
        )


def _pca_2d_3d(vectors: list[list[float]]) -> tuple[list[list[float]], list[list[float]]]:
    """Deterministic fallback for tiny sets: principal components without numpy heavy lifting."""
    import numpy as np

    matrix = np.asarray(vectors, dtype=float)
    centered = matrix - matrix.mean(axis=0)
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    comps = min(3, vt.shape[0])
    coords = centered @ vt[:comps].T
    if comps < 3:
        coords = np.pad(coords, ((0, 0), (0, 3 - comps)))
    return _coords(coords[:, :2]), _coords(coords[:, :3])


@dataclass(slots=True)
class ComputeProjection:
    reader: EmbeddingReader
    writer: ProjectionWriter
    tables: tuple[str, ...] = ("entity", "fact")
    limit_per_table: int = 20000
    min_points_for_umap: int = 10

    async def __call__(self) -> ProjectionReport:
        keys: list[tuple[str, str]] = []
        vectors: list[list[float]] = []
        counts = dict.fromkeys(self.tables, 0)
        for table in self.tables:
            for record_id, vector in await self.reader.embeddings(
                table, limit=self.limit_per_table
            ):
                keys.append((table, record_id))
                vectors.append(vector)
                counts[table] += 1
        n = len(vectors)
        if n < 3:
            return ProjectionReport(
                points=n,
                entities=counts.get("entity", 0),
                facts=counts.get("fact", 0),
                skipped_reason="fewer than 3 embedded records",
            )
        if n >= self.min_points_for_umap:
            import numpy as np
            from umap import UMAP

            matrix = np.asarray(vectors, dtype=float)
            neighbors = max(2, min(15, n - 1))
            two = _coords(
                UMAP(
                    n_components=2,
                    n_neighbors=neighbors,
                    min_dist=0.1,
                    metric="cosine",
                    random_state=42,
                ).fit_transform(matrix)
            )
            three = _coords(
                UMAP(
                    n_components=3,
                    n_neighbors=neighbors,
                    min_dist=0.1,
                    metric="cosine",
                    random_state=42,
                ).fit_transform(matrix)
            )
        else:
            two, three = _pca_2d_3d(vectors)
        per_table: dict[str, dict[str, dict[str, float]]] = {table: {} for table in self.tables}
        for (table, record_id), xy, xyz in zip(keys, two, three, strict=True):
            per_table[table][record_id] = {
                "x": _finite(xy[0]),
                "y": _finite(xy[1]),
                "x3": _finite(xyz[0]),
                "y3": _finite(xyz[1]),
                "z3": _finite(xyz[2]),
            }
        for table, coordinates in per_table.items():
            if coordinates:
                await self.writer.write_projection(table, coordinates)
        return ProjectionReport(
            points=n, entities=counts.get("entity", 0), facts=counts.get("fact", 0)
        )


def _coords(result: Any) -> list[list[float]]:
    """Normalize whatever the reducer returned (ndarray, tuple, sparse) to a list of rows.

    numpy and umap are untyped here, hence the relaxed pyright rules for this module.
    """
    import numpy as np

    array = result[0] if isinstance(result, tuple) else result
    if hasattr(array, "toarray"):
        array = array.toarray()
    return cast("list[list[float]]", np.asarray(array, dtype=float).tolist())


def _finite(value: float) -> float:
    value = float(value)
    return round(value, 5) if math.isfinite(value) else 0.0
