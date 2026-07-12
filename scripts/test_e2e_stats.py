#!/usr/bin/env python3
"""E2E test: fetch real API data, render stats card, save preview."""
import sys, types, asyncio, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Stub astrbot modules
astrbot_pkg = types.ModuleType("astrbot")
astrbot_api = types.ModuleType("astrbot.api")
class _L:
    @staticmethod
    def info(msg, *a, **kw): print(f"[INFO] {msg}")
    @staticmethod
    def warning(msg, *a, **kw): print(f"[WARN] {msg}")
    @staticmethod
    def error(msg, *a, **kw): print(f"[ERR]  {msg}")
    @staticmethod
    def debug(msg, *a, **kw): pass
astrbot_api.logger = _L()
astrbot_pkg.api = astrbot_api
sys.modules["astrbot"] = astrbot_pkg
sys.modules["astrbot.api"] = astrbot_api

API_KEY = "796c7ebc049ebf34b1b4c7b93b8a0960"
UID = "1000392976892"
PLATFORM = "PC"


async def fetch_api_data():
    """Fetch real player data from ALS API."""
    import httpx
    headers = {"Authorization": API_KEY, "User-Agent": "ApexChiyuchan/1.0"}
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        r = await client.get(
            "https://api.mozambiquehe.re/bridge",
            params={"uid": UID, "platform": PLATFORM, "merge": "1"},
            headers=headers,
        )
        r.raise_for_status()
        return r.json()


async def fetch_rank_distribution():
    """Fetch rank distribution data."""
    import httpx
    headers = {"Authorization": API_KEY, "User-Agent": "ApexChiyuchan/1.0"}
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        r = await client.get(
            "https://api.mozambiquehe.re/rankedThreshold",
            params={"platform": PLATFORM},
            headers=headers,
        )
        r.raise_for_status()
        return r.json()


def build_profile_data(raw_data, rank_dist_data):
    """Build the same profile_data dict that cmd_stats builds."""
    from libs.apex_client import PlayerStats, RankDistEntry
    from libs.playwright_renderer import _legend_zh

    stats = PlayerStats(raw_data)

    # Build rank dist entries
    rank_dist_entries = None
    if rank_dist_data:
        entries = []
        color_map = {
            "Rookie": "#484852", "Bronze": "#cd7f32", "Silver": "#c0c0c0",
            "Gold": "#ffd700", "Platinum": "#4ECDC4", "Diamond": "#358de6",
            "Master": "#9f35e6", "Predator": "#e31b39",
        }
        for name, info in rank_dist_data.items():
            if isinstance(info, dict) and "rankedThreshold" in info:
                entries.append(RankDistEntry(
                    name=name,
                    color=color_map.get(name, "#888"),
                    pct=info.get("playersInRank", 0),
                    count=info.get("playersInRank", 0),
                ))
        rank_dist_entries = entries if entries else None

    # Build profile data (mimicking cmd_stats)
    _lv = stats.level
    _pr = stats.prestige
    global_pct = stats.rank_top_pct

    profile_data = {
        "name": stats.name,
        "tag": stats.tag,
        "uid": stats.uid,
        "avatar_url": stats.avatar or "",
        "platform": PLATFORM,
        "online": stats.state,
        "level": _pr * 500 + _lv if _pr else _lv,
        "level_pct": stats.to_next_level_pct,
        "prestige": _pr,
        "level_icon": f"https://apexlegendsstatus.com/core/level_badge/?level={_pr * 500 + _lv if _pr else _lv}",
        "rank_name": stats.rank_name,
        "rank_div": stats.rank_div,
        "rank_score": stats.rank_score,
        "rank_img": stats.rank_img,
        "rank_top_pct": stats.rank_top_pct,
        "rank_top_pct_global": global_pct,
        "rank_ladder_pos": stats.rank_ladder_pos,
        "rp_delta": 0,
        "kills": stats.kills,
        "damage": stats.damage,
        "wins": stats.wins,
        "top_legends": [
            {
                "name": leg["name"],
                "kills": leg["kills"],
                "icon_url": leg.get("icon", ""),
            }
            for leg in stats.top_legends[:3]
        ],
        "selected_legend": stats.selected_legend_data,
        "season_badges": [],
        "special_badges": [],
        "rank_dist_entries": rank_dist_entries,
    }
    return profile_data


async def main():
    print("[1/4] Fetching API data...")
    try:
        raw_data = await fetch_api_data()
        print(f"  OK - name={raw_data.get('global',{}).get('name')} uid={raw_data.get('global',{}).get('uid')}")
    except Exception as e:
        print(f"  FAIL - API error: {e}")
        print("  Falling back to mock data...")
        raw_data = None

    print("[2/4] Fetching rank distribution...")
    rank_dist = None
    if raw_data:
        try:
            rank_dist = await fetch_rank_distribution()
            print(f"  OK - got {len(rank_dist)} entries")
        except Exception as e:
            print(f"  WARN - rank dist failed: {e}")

    print("[3/4] Building profile data...")
    if raw_data:
        profile_data = build_profile_data(raw_data, rank_dist)
    else:
        # Fallback mock data
        profile_data = {
            "name": "Liliumcordis", "tag": "YURI", "uid": "1000392976892",
            "avatar_url": "", "platform": "PC", "online": "offline",
            "level": 1601, "level_pct": 46, "prestige": 3,
            "level_icon": "https://apexlegendsstatus.com/core/level_badge/?level=1601",
            "rank_name": "Master", "rank_div": 0, "rank_score": 16378,
            "rank_img": "https://apexlegendsstatus.com/assets/ranks/Master.png",
            "rank_top_pct": 1.59, "rank_top_pct_global": 1.59, "rank_ladder_pos": 8430,
            "rp_delta": 0, "kills": 28226, "damage": 3613494, "wins": 419,
            "top_legends": [
                {"name": "Wraith", "kills": 8942, "icon_url": "https://apexlegendsstatus.com/assets/legends-select/wraith.png"},
                {"name": "Horizon", "kills": 1972, "icon_url": "https://apexlegendsstatus.com/assets/legends-select/horizon.png"},
                {"name": "Valkyrie", "kills": 766, "icon_url": "https://apexlegendsstatus.com/assets/legends-select/valkyrie.png"},
            ],
            "selected_legend": {
                "name": "Axle", "icon_url": "https://apexlegendsstatus.com/assets/legends-select/axle.png",
                "stats": [{"name": "代", "value": "120"}, {"name": "击杀数", "value": "345"}],
            },
            "season_badges": [], "special_badges": [], "rank_dist_entries": None,
        }

    # Debug output
    print(f"\n  selected_legend = {profile_data.get('selected_legend')}")
    print(f"  rank_dist_entries = {profile_data.get('rank_dist_entries')}")
    print(f"  rank_name = {profile_data.get('rank_name')}")
    print(f"  top_legends count = {len(profile_data.get('top_legends', []))}")

    print("\n[4/4] Rendering card...")
    from libs.playwright_renderer import _build_stats_html, _render_card_sync

    html = _build_stats_html(**profile_data)
    png = await _render_card_sync(html, 720)

    out = ROOT / "preview" / "stats.png"
    out.write_bytes(png)
    print(f"\n[DONE] Preview saved: {out} ({len(png)} bytes)")


if __name__ == "__main__":
    asyncio.run(main())
