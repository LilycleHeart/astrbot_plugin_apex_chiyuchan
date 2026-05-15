"""TTL 内存缓存 — 用于 API 响应缓存"""

from __future__ import annotations

import time
import asyncio
from typing import Any

_cache: dict[str, tuple[float, Any]] = {}
_lock = asyncio.Lock()


async def get(key: str) -> Any | None:
    async with _lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.time() > expires_at:
            del _cache[key]
            return None
        return value


async def set(key: str, value: Any, ttl_seconds: int):
    async with _lock:
        _cache[key] = (time.time() + ttl_seconds, value)


async def delete(key: str):
    async with _lock:
        _cache.pop(key, None)
