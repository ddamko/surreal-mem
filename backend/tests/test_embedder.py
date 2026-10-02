import json

import httpx
import pytest

from surrealmem.shared.infrastructure.inference.embedder import EmbeddingError, OpenAIEmbedder


def _server(dimension: int, *, fail: bool = False) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": []})
        if fail:
            return httpx.Response(500, text="boom")
        body = json.loads(request.content)
        data = [
            {"index": i, "embedding": [float(i + 1)] * dimension} for i in range(len(body["input"]))
        ]
        return httpx.Response(200, json={"data": list(reversed(data)), "model": body["model"]})

    return httpx.MockTransport(handler)


async def test_embedder_batches_and_orders(monkeypatch: pytest.MonkeyPatch) -> None:
    embedder = OpenAIEmbedder(base_url="http://embed/v1", model="m", dimension=3, batch_size=2)
    embedder._client = httpx.AsyncClient(transport=_server(3), base_url="http://embed/v1")  # pyright: ignore[reportPrivateUsage]
    vectors = await embedder.embed(["a", "b", "c"])
    assert vectors == [[1.0, 1.0, 1.0], [2.0, 2.0, 2.0], [1.0, 1.0, 1.0]]
    queries = await embedder.embed_queries(["q"])
    assert queries == [[1.0, 1.0, 1.0]]
    assert await embedder.healthy() is True
    assert embedder.model_name == "m"
    await embedder.close()


async def test_embedder_rejects_wrong_dimension_and_errors() -> None:
    embedder = OpenAIEmbedder(base_url="http://embed/v1", model="m", dimension=4)
    embedder._client = httpx.AsyncClient(transport=_server(3), base_url="http://embed/v1")  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(EmbeddingError, match="dimensions"):
        await embedder.embed(["a"])
    failing = OpenAIEmbedder(base_url="http://embed/v1", model="m", dimension=3)
    failing._client = httpx.AsyncClient(transport=_server(3, fail=True), base_url="http://embed/v1")  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(EmbeddingError, match="failed"):
        await failing.embed(["a"])
