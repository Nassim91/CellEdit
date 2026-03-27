"""Async HTTP client with retry logic."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from sentinel.utils.logging import get_logger

logger = get_logger(__name__)


class HttpClient:
    """Reusable async HTTP client with retries and rate-limit awareness."""

    def __init__(self, timeout: int = 30, max_retries: int = 3) -> None:
        self._timeout = timeout
        self._max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                follow_redirects=True,
                headers={"User-Agent": "Sentinel-Yield-Agent/0.1"},
            )
        return self._client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """GET request returning parsed JSON."""
        client = await self._get_client()
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def get_text(self, url: str, params: dict[str, Any] | None = None) -> str:
        """GET request returning raw text."""
        client = await self._get_client()
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.text

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> HttpClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
