#!/usr/bin/env python3
"""Generate light theme preview with real API data."""
import asyncio, sys, types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

astrbot_pkg = types.ModuleType('astrbot')
astrbot_api = types.ModuleType('astrbot.api')
class _L:
    @staticmethod
    def info(msg, *a, **kw): pass
    @staticmethod
    def warning(msg, *a, **kw): pass
    @staticmethod
    def error(msg, *a, **kw): pass
astrbot_api.logger = _L()
astrbot_pkg.api = astrbot_api
sys.modules['astrbot'] = astrbot_pkg
sys.modules['astrbot.api'] = astrbot_api

from libs.apex_client import ApexClient
from libs.playwright_renderer import _build_stats_html, _render_card_sync

API_KEY = '796c7ebc049ebf34b1b4c7b93b8a0960'

async def main():
    client = ApexClient(API_KEY)

    print('[1] Fetching player stats...')
    stats = await client.get_stats('1000392976892', 'PC')
    if not stats:
        print('ERROR: Could not fetch player stats')
        return
    print(f'  name={stats.name}, rank={stats.rank_name}')

    print('[2] Fetching rank distribution...')
    rank_dist = await client.get_rank_distribution()
    rd_entries = rank_dist.entries if rank_dist else None

    print('[3] Building HTML (forced light theme)...')
    _lv = stats.level
    _pr = stats.prestige
    profile_data = {
        'name': stats.name, 'tag': stats.tag, 'uid': stats.uid,
        'avatar_url': stats.avatar or '', 'platform': 'PC', 'online': stats.state,
        'level': _pr * 500 + _lv if _pr else _lv, 'level_pct': stats.to_next_level_pct,
        'prestige': _pr,
        'level_icon': 'https://apexlegendsstatus.com/core/level_badge/?level={}'.format(_pr * 500 + _lv if _pr else _lv),
        'rank_name': stats.rank_name, 'rank_div': stats.rank_div, 'rank_score': stats.rank_score,
        'rank_img': stats.rank_img, 'rank_top_pct': stats.rank_top_pct,
        'rank_top_pct_global': stats.rank_top_pct, 'rank_ladder_pos': stats.rank_ladder_pos,
        'rp_delta': 0, 'kills': stats.kills, 'damage': stats.damage, 'wins': stats.wins,
        'top_legends': [{'name': leg['name'], 'kills': leg['kills'], 'icon_url': leg.get('icon', '')} for leg in stats.top_legends[:3]],
        'selected_legend': stats.selected_legend_data,
        'season_badges': [], 'special_badges': [],
        'rank_dist_entries': rd_entries,
    }

    html = _build_stats_html(**profile_data)
    # Force light theme
    html = html.replace('body class=""', 'body class="light"')

    out = ROOT / 'preview' / 'stats_light_debug.html'
    out.write_text(html, encoding='utf-8')
    print(f'  HTML saved to {out}')

    print('[4] Rendering PNG...')
    png = await _render_card_sync(html, 720)
    png_out = ROOT / 'preview' / 'stats_light.png'
    png_out.write_bytes(png)
    print(f'  PNG saved to {png_out} ({len(png)} bytes)')

asyncio.run(main())
