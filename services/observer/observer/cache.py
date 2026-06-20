"""In-process snapshot cache — TTL 30s. Read amplification koruması.

Canonical key: endpoint + normalize edilmiş query param (None dışlanır). v1.3 param
uzayı flat (sadece `window`). Nested/list canonicalization → v1.4.
Horizontal scale gerekirse Redis'e geçilir → v1.4.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Awaitable, Callable

TTL = 30  # seconds
_cache: dict[str, tuple[float, Any]] = {}  # key → (expires_at, value)


def _key(endpoint: str, params: dict[str, Any]) -> str:
    norm = {k: v for k, v in params.items() if v is not None}
    canonical = json.dumps(dict(sorted(norm.items())), separators=(",", ":"))
    return hashlib.sha256(f"{endpoint}:{canonical}".encode()).hexdigest()


async def cached(
    endpoint: str, params: dict[str, Any], producer: Callable[[], Awaitable[Any]]
) -> Any:
    """Cache hit ise döndürür, miss ise producer'ı çağırıp 30s saklar."""
    key = _key(endpoint, params)
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and hit[0] > now:
        return hit[1]
    value = await producer()
    _cache[key] = (now + TTL, value)
    return value
