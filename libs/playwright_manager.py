"""共享 Playwright 浏览器管理器 — 单一持久进程，全局复用"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright, Browser

_playwright = None
_browser: Browser | None = None
_lock = asyncio.Lock()
_semaphore = asyncio.Semaphore(2)


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
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None


@asynccontextmanager
async def run_with_page(viewport: dict = None, device_scale_factor: float = 1):
    async with _semaphore:
        browser = await get_browser()
        ctx = await browser.new_context(
            viewport=viewport,
            device_scale_factor=device_scale_factor,
        )
        page = await ctx.new_page()
        try:
            yield page
        finally:
            await ctx.close()
