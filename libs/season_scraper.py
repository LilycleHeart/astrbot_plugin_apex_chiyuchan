"""赛季信息抓取器 — esportstales + ALS meta"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from .ttl_cache import get as cache_get, set as cache_set


_CST = ZoneInfo("Asia/Shanghai")


@dataclass
class SeasonMetaLegend:
    name: str        # 中文名
    en: str          # 英文名
    icon: str        # 图片URL
    win_rate: str    # e.g. "50%"
    pick_rate: str   # e.g. "50%"

@dataclass
class SeasonInfo:
    season_number: int
    season_name: str
    season_start: str     # "May 5, 2026"
    season_end: str       # "Aug 4, 2026"
    split: int            # 1 or 2
    split_label: str      # "Split 1"
    days_left: int
    hours_left: int
    minutes_left: int
    meta_top5: list[SeasonMetaLegend] = field(default_factory=list)


# ── 英雄名中英文映射 ──
LEGEND_ZH = {
    "Wraith": "恶灵", "Horizon": "地平线", "Valkyrie": "瓦尔基里",
    "Pathfinder": "探路者", "Bloodhound": "寻血猎犬", "Gibraltar": "直布罗陀",
    "Lifeline": "命脉", "Mirage": "幻象", "Caustic": "侵蚀",
    "Octane": "动力小子", "Bangalore": "班加罗尔", "Wattson": "沃特森",
    "Crypto": "密客", "Revenant": "亡灵", "Loba": "罗芭",
    "Rampart": "兰伯特", "Fuse": "暴雷", "Seer": "先知",
    "Ash": "艾许", "Mad Maggie": "疯玛吉", "Newcastle": "纽卡斯尔",
    "Vantage": "万蒂奇", "Catalyst": "卡特莉丝", "Ballistic": "弹道",
    "Conduit": "导管", "Alter": "变幻", "Forge": "锻铁",
    "Axle": "艾克赛尔",
}

# ── 赛季名中文映射 ──
SEASON_NAME_ZH = {
    "Overclocked": "超频",
    "Breach": "突破",
    "Amped": "增幅",
    "Showdown": "对决",
    "Prodigy": "天才",
    "Takeover": "接管",
    "From the Rift": "裂隙降临",
    "Shockwave": "冲击波",
    "Upheaval": "剧变",
    "Breakout": "破局",
    "Ignite": "点燃",
    "Resurrection": "复活",
    "Arsenal": "军火库",
    "Revelry": "狂欢",
    "Eclipse": "日蚀",
    "Hunted": "猎杀",
    "Saviors": "救世主",
    "Defiance": "反抗",
    "Escape": "逃亡",
    "Emergence": "涌现",
    "Legacy": "传承",
    "Mayhem": "混乱",
    "Ascension": "飞升",
    "Boosted": "加速",
    "Fortune's Favor": "命运之恩",
    "Assimilation": "同化",
    "Meltdown": "融毁",
    "Battle Charge": "战斗号角",
    "Wild Frontier": "荒野前线",
}

# ALS legend icon base URL
ALS_ICON_BASE = "https://apexlegendsstatus.com/assets/legends"

# 分割日期 (Season 20+ 有 mid-season split)
# Season 29: Split 1 ends Jun 23, Split 2 starts Jun 23 ends Aug 4
# (based on page saying "Season 29 will end on August 4, 2026")
# We estimate split midpoint based on total duration
_SPLIT_DATES_S29 = {
    "split1_end": _dt.datetime(2026, 6, 23, tzinfo=_CST),
    "season_end": _dt.datetime(2026, 8, 4, tzinfo=_CST),
    "season_start": _dt.datetime(2026, 5, 5, tzinfo=_CST),
}


def _determine_split_and_end() -> tuple[int, int, int, int]:
    """Determine current split and compute countdown. Returns (days, hours, minutes, split)."""
    now = _dt.datetime.now(tz=_CST)
    split1_end = _dt.datetime(2026, 6, 23, tzinfo=_CST)
    s29_end = _dt.datetime(2026, 8, 4, tzinfo=_CST)

    if now < split1_end:
        split = 1
        split_end = split1_end
    else:
        split = 2
        split_end = s29_end

    delta = split_end - now
    days = max(0, delta.days)
    hours = max(0, delta.seconds // 3600)
    minutes = max(0, (delta.seconds % 3600) // 60)

    return days, hours, minutes, split


async def fetch_season_info() -> SeasonInfo | None:
    """获取赛季信息 (TTL 缓存 10 分钟)"""
    cache_key = "season_info"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    days_left, hours_left, minutes_left, split = _determine_split_and_end()
    split_label = f"Split {split}"
    season_name_zh = SEASON_NAME_ZH.get("Overclocked", "超频")

    result = SeasonInfo(
        season_number=29,
        season_name=season_name_zh,
        season_start="2026-05-05",
        season_end="2026-08-04",
        split=split,
        split_label=split_label,
        days_left=days_left,
        hours_left=hours_left,
        minutes_left=minutes_left,
    )

    await cache_set(cache_key, result, 600)  # 10 min cache
    return result


async def fetch_meta_top5() -> list[SeasonMetaLegend]:
    """从 ALS meta 页面抓取 Top 5 英雄胜率 (TTL 缓存 30 分钟)
    
    页面数据为 DataTables 动态渲染，innerText 格式：
    '#1 Axle 55.1% 32.2% 1,660'
    '#2 Seer 55.2% 25.2% 1,300'
    """
    cache_key = "meta_top5"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    from .playwright_manager import run_with_page

    results: list[SeasonMetaLegend] = []

    try:
        async with run_with_page() as page:
            try:
                await page.goto(
                    "https://apexlegendsstatus.com/meta",
                    wait_until="networkidle",
                    timeout=30000,
                )
            except Exception:
                await page.goto(
                    "https://apexlegendsstatus.com/meta",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
            await page.wait_for_timeout(3000)

            # 获取 innerText 然后用正则解析
            text = await page.evaluate("() => document.body.innerText")

            # 格式: "#1 Axle 55.1% 32.2% 1,660"
            # 胜率/选取率可含小数点, 总场次可含逗号
            import re as _re
            pattern = _re.compile(r"#(\d+)\s+(\S+(?:\s+\S+)?)\s+(\d+\.?\d*%)\s+(\d+\.?\d*%)\s+([\d,]+)")

            for m in pattern.finditer(text):
                name_en = m.group(2).strip()
                win_rate = m.group(3)
                pick_rate = m.group(4)
                total_games = int(m.group(5).replace(",", ""))

                # 跳过完全没有数据的条目
                if total_games < 1:
                    continue

                name_zh = LEGEND_ZH.get(name_en, name_en)
                icon = f"https://apexlegendsstatus.com/assets/legends-select/{name_en.lower().replace(' ', '')}.png"

                results.append(SeasonMetaLegend(
                    name=name_zh,
                    en=name_en,
                    icon=icon,
                    win_rate=win_rate,
                    pick_rate=pick_rate,
                ))

                if len(results) >= 6:
                    break

    except Exception:
        pass

    if results:
        await cache_set(cache_key, results, 1800)  # 30 min
    return results
