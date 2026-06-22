"""Steamcharts 爬虫 — Apex Legends (app/1172470) 日活数据"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .ttl_cache import get as cache_get, set as cache_set

_APP_ID = "1172470"
_URL = f"https://steamcharts.com/app/{_APP_ID}"


@dataclass
class MonthEntry:
    month: str       # "May 2026" / "Last 30 Days"
    avg_players: float
    gain: float | None
    gain_pct: float | None
    peak: int


@dataclass
class SteamchartsData:
    current_online: int = 0
    peak_24h: int = 0
    peak_all_time: int = 0
    months: list[MonthEntry] = field(default_factory=list)


def _to_int(s: str) -> int:
    return int(s.replace(",", "").strip() or "0")


def _to_float(s: str) -> float | None:
    s = s.replace(",", "").replace("+", "").replace("&#43;", "").strip()
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


async def fetch_steamcharts() -> SteamchartsData | None:
    """抓取 Apex Steamcharts 页面（静态 HTML，httpx + regex 解析）。TTL 缓存 5 分钟。"""
    cache_key = "steamcharts:apex"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    import httpx

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=headers) as c:
            r = await c.get(_URL)
            r.raise_for_status()
            html = r.text
    except Exception as e:
        from astrbot.api import logger
        logger.warning(f"[Steamcharts] 下载失败: {e}")
        return None

    data = SteamchartsData()

    # 顶部三个 app-stat：playing / 24-hour peak / all-time peak
    stats = re.findall(
        r'<div class="app-stat">\s*<span class="num">([\d,]+)</span>\s*<br>([^<]+)',
        html,
    )
    if len(stats) >= 3:
        data.current_online = _to_int(stats[0][0])
        data.peak_24h = _to_int(stats[1][0])
        data.peak_all_time = _to_int(stats[2][0])

    # 月度表格行
    row_re = re.compile(
        r'<tr[^>]*>\s*'
        r'<td class="month-cell left([^"]*)">([^<]+)</td>\s*'
        r'<td class="right num-f[^"]*">([^<]+)</td>\s*'
        r'<td class="right num-p gainorloss[^"]*">([^<]+)</td>\s*'
        r'<td class="right gainorloss[^"]*">([^<]+)</td>\s*'
        r'<td class="right num[^"]*">([^<]+)</td>\s*</tr>',
        re.DOTALL,
    )
    for m in row_re.finditer(html):
        month = m.group(2).strip()
        avg = _to_float(m.group(3))
        gain = _to_float(m.group(4))
        gain_pct = _to_float(m.group(5))
        peak = _to_int(m.group(6))
        if avg is None:
            continue
        data.months.append(
            MonthEntry(month=month, avg_players=avg, gain=gain, gain_pct=gain_pct, peak=peak)
        )

    if not data.months and not data.current_online:
        return None

    await cache_set(cache_key, data, 300)
    return data
