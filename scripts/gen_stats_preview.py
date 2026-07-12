#!/usr/bin/env python3
"""Generate stats card preview with mock data."""
import sys, types, asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

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

from libs.playwright_renderer import _build_stats_html, _render_card_sync

# Mock stats data
mock_stats = {
    "name": "TSM_ImperialHal", "tag": "", "uid": "123456789",
    "avatar_url": "", "platform": "PC", "online": "online",
    "level": 500, "level_pct": 65, "prestige": 3,
    "level_icon": "https://apexlegendsstatus.com/assets/level_badges/500.svg",
    "rank_name": "Master", "rank_div": 0, "rank_score": 15200,
    "rank_img": "https://apexlegendsstatus.com/assets/ranks/Master.png",
    "rank_top_pct": 0.1, "rank_top_pct_global": 0.1,
    "rank_ladder_pos": 150, "rp_delta": 200,
    "kills": 25000, "damage": 8500000, "wins": 1200,
    "top_legends": [
        {"name": "Horizon", "icon_url": "https://apexlegendsstatus.com/assets/legends-select/horizon.png", "kills": 8500},
        {"name": "Seer", "icon_url": "https://apexlegendsstatus.com/assets/legends-select/seer.png", "kills": 6200},
        {"name": "Alter", "icon_url": "https://apexlegendsstatus.com/assets/legends-select/alter.png", "kills": 4100},
        {"name": "Wraith", "icon_url": "https://apexlegendsstatus.com/assets/legends-select/wraith.png", "kills": 3200},
    ],
    "selected_legend": {
        "name": "Horizon", "icon_url": "https://apexlegendsstatus.com/assets/legends-select/horizon.png",
        "stats": [{"name": "击杀", "value": "8,500"}, {"name": "胜场", "value": "420"}],
    },
    "season_badges": [{"badge_url": "", "season": "S29", "color": "#B184FF", "tier": "master"}],
    "special_badges": [],
}


async def main():
    html = _build_stats_html(**mock_stats)
    png = await _render_card_sync(html, 720)
    out = ROOT / "preview" / "stats.png"
    out.write_bytes(png)
    print(f"[OK] {out} ({len(png)} bytes)")


if __name__ == "__main__":
    asyncio.run(main())
