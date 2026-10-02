"""Deterministic test doubles for the shared ports (ADR-0025)."""

import hashlib
import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

    from surrealmem.shared.application import JobRequest


class FakeEmbedder:
    """Stable pseudo-embeddings: identical text gives identical vectors; similar text is not
    guaranteed to be close, so tests assert on identity, not on semantics."""

    def __init__(self, dimension: int = 1024, model_name: str = "fake-embedder") -> None:
        self._dimension = dimension
        self._model_name = model_name
        self.calls: list[list[str]] = []

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [self._vector(t) for t in texts]

    async def embed_queries(self, texts: Sequence[str]) -> list[list[float]]:
        return await self.embed(texts)

    def _vector(self, text: str) -> list[float]:
        values: list[float] = []
        counter = 0
        while len(values) < self._dimension:
            digest = hashlib.sha256(f"{text}:{counter}".encode()).digest()
            values.extend((b / 255.0) * 2.0 - 1.0 for b in digest)
            counter += 1
        values = values[: self._dimension]
        norm = math.sqrt(sum(v * v for v in values)) or 1.0
        return [v / norm for v in values]


class RecordingJobQueue:
    def __init__(self) -> None:
        self.requests: list[JobRequest] = []

    async def enqueue(self, request: JobRequest) -> str:
        self.requests.append(request)
        return f"job:{len(self.requests)}"


class StubEmbedder(FakeEmbedder):
    """FakeEmbedder with pinned vectors for chosen texts, to drive the embedding tier."""

    def __init__(self, pinned: dict[str, list[float]] | None = None, dimension: int = 1024) -> None:
        super().__init__(dimension=dimension, model_name="stub-embedder")
        self.pinned = pinned or {}

    def _vector(self, text: str) -> list[float]:
        for needle, vector in self.pinned.items():
            if needle in text:
                return vector
        return super()._vector(text)


def unit_vector(dimension: int, *, axis: int, tilt: float = 0.0) -> list[float]:
    """A unit vector along ``axis``, optionally tilted toward axis+1 by ``tilt`` (0..1)."""
    values = [0.0] * dimension
    values[axis] = math.sqrt(1.0 - tilt * tilt)
    values[(axis + 1) % dimension] = tilt
    return values


class FakeExtractor:
    """Returns a canned ExtractionResult per substring of the message, else an empty result."""

    def __init__(
        self, canned: dict[str, Any] | None = None, *, fail_with: Exception | None = None
    ) -> None:
        from surrealmem.extraction.domain import ExtractionResult

        self.canned = {k: ExtractionResult.model_validate(v) for k, v in (canned or {}).items()}
        self.fail_with = fail_with
        self.contexts: list[Any] = []

    @property
    def name(self) -> str:
        return "fake"

    async def extract(self, context: Any) -> Any:
        from surrealmem.extraction.domain import ExtractionResult

        self.contexts.append(context)
        if self.fail_with is not None:
            raise self.fail_with
        for needle, result in self.canned.items():
            if needle in context.content:
                return result
        return ExtractionResult()
