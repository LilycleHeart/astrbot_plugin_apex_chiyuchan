"""Steamcharts 爬虫 — Apex Legends (app/1172470) 日活数据"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .ttl_cache import get as cache_get, set as cache_set

_APP_ID = "1172470"
_URL = f"https://steamcharts.com/app/{_APP_ID}"
_CHART_URL = f"https://steamcharts.com/app/{_APP_ID}/chart-data.json"


@dataclass
class MonthEntry:
    month: str       # "May 2026" / "Last 30 Days"
    avg_players: float
    gain: float | None
    gain_pct: float | None
    peak: int


@dataclass
class HourlyBucket:
    ts_ms: int          # 桶起始时间戳（毫秒）
    avg_players: float  # 桶内平均在线


@dataclass
class SteamchartsData:
    current_online: int = 0
    peak_24h: int = 0
    peak_all_time: int = 0
    months: list[MonthEntry] = field(default_factory=list)
    # 最近 7 天按 12 小时分桶（14 个桶）
    seven_day_buckets: list[HourlyBucket] = field(default_factory=list)


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


def _bucket_last_7_days(raw: list[list[int]]) -> list[HourlyBucket]:
    """chart-data.json 是 [[ts_ms, players], ...]。
    取最近 7 天，按 12 小时分桶 = 14 个桶，每桶取平均在线人数。
    """
    if not raw:
        return []
    now_ms = raw[-1][0]
    seven_days_ms = 7 * 86400_000
    bucket_ms = 12 * 3600_000
    start_ms = now_ms - seven_days_ms

    buckets: dict[int, list[int]] = {}
    for ts, players in raw:
        if ts < start_ms:
            continue
        bidx = (ts - start_ms) // bucket_ms
        buckets.setdefault(int(bidx), []).append(players)

    result: list[HourlyBucket] = []
    for i in range(14):
        bstart = start_ms + i * bucket_ms
        vals = buckets.get(i, [])
        avg = sum(vals) / len(vals) if vals else 0.0
        result.append(HourlyBucket(ts_ms=bstart, avg_players=avg))
    return result


_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


async def fetch_steamcharts() -> SteamchartsData | None:
    """抓取 Apex Steamcharts 页面 + chart-data.json（5 分钟 TTL 缓存）"""
    import httpx

    cache_key = "steamcharts:apex"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    data = SteamchartsData()

    # ── 主页 HTML ──
    try:
        async with httpx.AsyncClient(
            timeout=10.0, follow_redirects=True,
            headers={"User-Agent": _UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"},
        ) as c:
            r = await c.get(_URL)
            r.raise_for_status()
            html = r.text
    except Exception as e:
        from astrbot.api import logger
        logger.warning(f"[Steamcharts] HTML 下载失败: {e}")
        return None

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

    # ── chart-data.json：最近 7 天按 12 小时分桶 ──
    try:
        async with httpx.AsyncClient(
            timeout=10.0, follow_redirects=True,
            headers={"User-Agent": _UA, "Referer": _URL, "Accept": "application/json,*/*;q=0.8"},
        ) as c:
            r = await c.get(_CHART_URL)
            r.raise_for_status()
            chart_raw = r.json()
            if isinstance(chart_raw, list):
                data.seven_day_buckets = _bucket_last_7_days(chart_raw)
    except Exception as e:
        from astrbot.api import logger
        logger.warning(f"[Steamcharts] chart-data.json 下载失败: {e}")

    if not data.months and not data.current_online:
        return None

    await cache_set(cache_key, data, 300)
    return data
