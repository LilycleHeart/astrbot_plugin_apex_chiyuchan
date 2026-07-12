"""共享 httpx 连接池 — 全局复用，避免每次请求新建 TCP 连接"""

from __future__ import annotations

import asyncio
import httpx

_async_client: httpx.AsyncClient | None = None
_async_lock = asyncio.Lock()

_sync_client: httpx.Client | None = None


async def get_async_client() -> httpx.AsyncClient:
    global _async_client
    if _async_client is None:
        async with _async_lock:
            if _async_client is None:
                _async_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0),
                    limits=httpx.Limits(
                        max_connections=20, max_keepalive_connections=10
                    ),
                )
    return _async_client


def get_sync_client() -> httpx.Client:
    global _sync_client
    if _sync_client is None:
        _sync_client = httpx.Client(
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
    return _sync_client


async def close_clients():
    global _async_client, _sync_client
    if _async_client:
        await _async_client.aclose()
        _async_client = None
    if _sync_client:
        _sync_client.close()
        _sync_client = None
