"""Embedder backed by an OpenAI-compatible ``/v1/embeddings`` endpoint (ADR-0010).

Qwen3-Embedding models expect retrieval queries to carry an instruction prefix while documents
are embedded raw, so queries and documents go through separate methods.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

import httpx

if TYPE_CHECKING:
    from collections.abc import Sequence

DEFAULT_QUERY_INSTRUCTION = (
    "Instruct: Given a query, retrieve memories, facts and entities relevant to it\nQuery: "
)


class EmbeddingError(RuntimeError):
    pass


@dataclass(slots=True)
class OpenAIEmbedder:
    base_url: str
    model: str
    dimension: int
    api_key: str | None = None
    batch_size: int = 32
    timeout_seconds: float = 120.0
    query_instruction: str = DEFAULT_QUERY_INSTRUCTION
    _client: httpx.AsyncClient | None = field(default=None, repr=False)

    @property
    def model_name(self) -> str:
        return self.model

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            self._client = httpx.AsyncClient(
                base_url=self.base_url.rstrip("/"), headers=headers, timeout=self.timeout_seconds
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            vectors.extend(await self._request(list(texts[start : start + self.batch_size])))
        return vectors

    async def embed_queries(self, texts: Sequence[str]) -> list[list[float]]:
        return await self.embed([f"{self.query_instruction}{t}" for t in texts])

    async def healthy(self) -> bool:
        try:
            response = await self._http().get("/models")
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def _request(self, batch: list[str]) -> list[list[float]]:
        if not batch:
            return []
        try:
            response = await self._http().post(
                "/embeddings", json={"model": self.model, "input": batch}
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"embedding request failed: {exc}") from exc
        payload = cast("dict[str, Any]", response.json())
        data = sorted(
            cast("list[dict[str, Any]]", payload.get("data", [])),
            key=lambda item: int(item.get("index", 0)),
        )
        if len(data) != len(batch):
            raise EmbeddingError(f"expected {len(batch)} embeddings, got {len(data)}")
        vectors = [[float(x) for x in cast("list[float]", item["embedding"])] for item in data]
        for vector in vectors:
            if len(vector) != self.dimension:
                raise EmbeddingError(
                    f"model {self.model} returned {len(vector)} dimensions, "
                    f"expected {self.dimension}"
                )
        return vectors
