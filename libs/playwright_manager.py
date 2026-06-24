"""共享 Playwright 浏览器管理器 — 单一持久进程，Context 池复用"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright, Browser, BrowserContext

_playwright = None
_browser: Browser | None = None
_lock = asyncio.Lock()
_semaphore = asyncio.Semaphore(2)
_context_pool: asyncio.Queue[BrowserContext] = asyncio.Queue()
_CONTEXT_POOL_SIZE = 2

# 时区 & 主题（通过 main.py 从插件配置读取）
_TIMEZONE_ID = "Asia/Shanghai"
_COLOR_SCHEME = "dark"


def set_timezone(tz: str):
    global _TIMEZONE_ID
    _TIMEZONE_ID = tz


def set_color_scheme(scheme: str):
    global _COLOR_SCHEME
    _COLOR_SCHEME = scheme

# 性能监控
_stats: dict[str, list[float]] = {
    "sem_wait": [],
    "ctx_create": [],
    "page_use": [],
}


def _log_stat(key: str, value: float):
    _stats[key].append(value)
    if len(_stats[key]) > 20:
        _stats[key] = _stats[key][-20:]


def get_pw_stats() -> dict:
    result = {}
    for k, v in _stats.items():
        if v:
            result[k] = {
                "avg": sum(v) / len(v),
                "max": max(v),
                "min": min(v),
                "count": len(v),
            }
    return result


async def get_browser() -> Browser:
    global _playwright, _browser
    if _browser is None:
        async with _lock:
            if _browser is None:
                _playwright = await async_playwright().start()
                _browser = await _playwright.webkit.launch(headless=True)
    return _browser


async def close_browser():
    global _playwright, _browser
    while not _context_pool.empty():
        try:
            ctx = _context_pool.get_nowait()
            await ctx.close()
        except Exception:
            pass
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None


async def _get_context(device_scale_factor: float = 1) -> BrowserContext:
    # df=1 走连接池；df≠1 说明是截图场景，每次新建避免污染池内 context
    if device_scale_factor == 1:
        try:
            return _context_pool.get_nowait()
        except asyncio.QueueEmpty:
            pass
    browser = await get_browser()
    t0 = time.perf_counter()
    ctx = await browser.new_context(
        viewport={"width": 1280, "height": 800},
        timezone_id=_TIMEZONE_ID,
        color_scheme=_COLOR_SCHEME,
        device_scale_factor=device_scale_factor,
    )
    _log_stat("ctx_create", time.perf_counter() - t0)
    return ctx


async def _return_context(ctx: BrowserContext):
    if _context_pool.qsize() < _CONTEXT_POOL_SIZE:
        await _context_pool.put(ctx)
    else:
        await ctx.close()


@asynccontextmanager
async def run_with_page(viewport: dict = None, device_scale_factor: float = 1):
    t_wait = time.perf_counter()
    async with _semaphore:
        _log_stat("sem_wait", time.perf_counter() - t_wait)

        ctx = await _get_context(device_scale_factor=device_scale_factor)
        page = await ctx.new_page()
        if viewport:
            await page.set_viewport_size(viewport)

        t_use = time.perf_counter()
        try:
            yield page
        finally:
            _log_stat("page_use", time.perf_counter() - t_use)
            await page.close()
            await _return_context(ctx)
