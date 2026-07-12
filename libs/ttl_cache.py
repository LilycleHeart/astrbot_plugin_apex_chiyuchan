"""TTL 内存缓存 — 用于 API 响应缓存"""

from __future__ import annotations

import time
import asyncio
from typing import Any

_cache: dict[str, tuple[float, Any]] = {}
_lock = asyncio.Lock()
_cleaner_started = False


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


async def _auto_clean():
    while True:
        await asyncio.sleep(300)
        async with _lock:
            now = time.time()
            expired = [k for k, v in _cache.items() if now > v[0]]
            for k in expired:
                del _cache[k]


def start_cleaner():
    global _cleaner_started
    if not _cleaner_started:
        _cleaner_started = True
        asyncio.create_task(_auto_clean())
