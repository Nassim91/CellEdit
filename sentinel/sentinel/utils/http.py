"""Async HTTP client with retry logic and TTL cache."""

from __future__ import annotations

import asyncio
import hashlib
import time
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from sentinel.utils.logging import get_logger

logger = get_logger(__name__)


class TTLCache:
    """Simple in-memory TTL cache for API responses.

    Prevents redundant API calls when the same endpoint is queried
    multiple times within the TTL window (e.g., DeFiLlama data updates hourly).
    """

    def __init__(self, default_ttl: int = 300) -> None:
        self._store: dict[str, tuple[float, Any]] = {}
        self._default_ttl = default_ttl

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        expires_at = time.monotonic() + (ttl or self._default_ttl)
        self._store[key] = (expires_at, value)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)

    @staticmethod
    def make_key(url: str, params: dict[str, Any] | None = None) -> str:
        """Generate a deterministic cache key from URL + params."""
        raw = url
        if params:
            sorted_params = sorted(params.items())
            raw += "?" + "&".join(f"{k}={v}" for k, v in sorted_params)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


class RateLimiter:
    """Per-domain rate limiter using asyncio semaphores."""

    def __init__(self, max_concurrent: int = 10) -> None:
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._max_concurrent = max_concurrent

    def _get_domain(self, url: str) -> str:
        from urllib.parse import urlparse
        return urlparse(url).netloc

    async def acquire(self, url: str) -> None:
        domain = self._get_domain(url)
        if domain not in self._semaphores:
            self._semaphores[domain] = asyncio.Semaphore(self._max_concurrent)
        await self._semaphores[domain].acquire()

    def release(self, url: str) -> None:
        domain = self._get_domain(url)
        if domain in self._semaphores:
            self._semaphores[domain].release()


class HttpClient:
    """Reusable async HTTP client with retries, TTL cache, and rate limiting."""

    def __init__(
        self,
        timeout: int = 30,
        max_retries: int = 3,
        cache_ttl: int = 300,
        max_concurrent: int = 10,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._timeout = timeout
        self._max_retries = max_retries
        self._client: httpx.AsyncClient | None = None
        self._cache = TTLCache(default_ttl=cache_ttl)
        self._rate_limiter = RateLimiter(max_concurrent=max_concurrent)
        self._extra_headers = extra_headers or {}

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {"User-Agent": "Sentinel-Yield-Agent/0.2"}
            headers.update(self._extra_headers)
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                follow_redirects=True,
                headers=headers,
            )
        return self._client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        cache_ttl: int | None = None,
        skip_cache: bool = False,
    ) -> Any:
        """GET request returning parsed JSON, with optional caching.

        Args:
            url: The URL to fetch.
            params: Query parameters.
            cache_ttl: Override default TTL for this request (seconds).
            skip_cache: If True, bypass cache entirely.
        """
        # Check cache first
        if not skip_cache:
            cache_key = TTLCache.make_key(url, params)
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.debug("http.cache_hit", url=url)
                return cached

        await self._rate_limiter.acquire(url)
        try:
            client = await self._get_client()
            resp = await client.get(url, params=params)

            # Respect Retry-After header
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "5"))
                logger.warning("http.rate_limited", url=url, retry_after=retry_after)
                await asyncio.sleep(retry_after)
                resp = await client.get(url, params=params)

            resp.raise_for_status()
            data = resp.json()

            # Cache the result
            if not skip_cache:
                self._cache.set(cache_key, data, ttl=cache_ttl)

            return data
        finally:
            self._rate_limiter.release(url)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def get_text(self, url: str, params: dict[str, Any] | None = None) -> str:
        """GET request returning raw text (no caching)."""
        await self._rate_limiter.acquire(url)
        try:
            client = await self._get_client()
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.text
        finally:
            self._rate_limiter.release(url)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def post_json(
        self,
        url: str,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """POST request returning parsed JSON."""
        await self._rate_limiter.acquire(url)
        try:
            client = await self._get_client()
            resp = await client.post(url, json=json_body, headers=headers)
            resp.raise_for_status()
            return resp.json()
        finally:
            self._rate_limiter.release(url)

    @property
    def cache(self) -> TTLCache:
        """Access the cache directly for manual operations."""
        return self._cache

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> HttpClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
