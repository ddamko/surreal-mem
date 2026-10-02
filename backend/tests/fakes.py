"""Deterministic test doubles for the shared ports (ADR-0025)."""

import hashlib
import math
from typing import TYPE_CHECKING

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
