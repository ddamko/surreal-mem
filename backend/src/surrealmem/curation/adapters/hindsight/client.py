"""Read-only client for the Hindsight HTTP API (0.10.x)."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

import httpx

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@dataclass(slots=True)
class HindsightClient:
    base_url: str = "http://127.0.0.1:8888"
    api_key: str | None = None
    tenant: str = "default"
    timeout_seconds: float = 60.0
    _client: httpx.AsyncClient | None = field(default=None, repr=False)

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

    def _bank(self, bank_id: str) -> str:
        return f"/v1/{self.tenant}/banks/{bank_id}"

    async def banks(self) -> list[str]:
        response = await self._http().get(f"/v1/{self.tenant}/banks")
        response.raise_for_status()
        payload = cast("object", response.json())
        if isinstance(payload, list):
            items = cast("list[dict[str, Any]]", payload)
        else:
            record = cast("dict[str, Any]", payload)
            items = cast("list[dict[str, Any]]", record.get("items") or record.get("banks") or [])
        return [str(b.get("bank_id") or b.get("id")) for b in items]

    async def documents(
        self, bank_id: str, *, page_size: int = 100
    ) -> AsyncIterator[dict[str, Any]]:
        offset = 0
        while True:
            response = await self._http().get(
                f"{self._bank(bank_id)}/documents", params={"limit": page_size, "offset": offset}
            )
            response.raise_for_status()
            items = cast("list[dict[str, Any]]", response.json().get("items") or [])
            for item in items:
                yield item
            if len(items) < page_size:
                return
            offset += page_size

    async def document(self, bank_id: str, document_id: str) -> dict[str, Any]:
        response = await self._http().get(f"{self._bank(bank_id)}/documents/{document_id}")
        response.raise_for_status()
        return cast("dict[str, Any]", response.json())

    async def memories(
        self, bank_id: str, *, page_size: int = 200
    ) -> AsyncIterator[dict[str, Any]]:
        offset = 0
        while True:
            response = await self._http().get(
                f"{self._bank(bank_id)}/memories/list",
                params={"limit": page_size, "offset": offset},
            )
            response.raise_for_status()
            items = cast("list[dict[str, Any]]", response.json().get("items") or [])
            for item in items:
                yield item
            if len(items) < page_size:
                return
            offset += page_size
