#!/usr/bin/env python3
"""Generate HTML with real API data for ancallbelle."""
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
from libs.playwright_renderer import _build_stats_html

API_KEY = '796c7ebc049ebf34b1b4c7b93b8a0960'

async def main():
    client = ApexClient(API_KEY)

    print('[1] Fetching player stats for AncallBelle...')
    stats = await client.get_stats('1000392976892', 'PC')
    if not stats:
        print('ERROR: Could not fetch player stats')
        return
    print(f'  name={stats.name}, rank={stats.rank_name}, level={stats.level}')
    print(f'  kills={stats.kills}, damage={stats.damage}, wins={stats.wins}')
    print(f'  selected_legend={stats.selected_legend_data}')
    print(f'  top_legends count={len(stats.top_legends)}')
    for leg in stats.top_legends[:3]:
        print(f'    {leg["name"]}: {leg["kills"]} kills')

    print('\n[2] Fetching rank distribution...')
    rank_dist = await client.get_rank_distribution()
    if rank_dist:
        print(f'  Got {len(rank_dist.entries)} entries')
        for e in rank_dist.entries:
            print(f'    {e.name}: {e.pct}% ({e.count} players)')
    else:
        print('  WARN: rank_dist is None')

    print('\n[3] Building profile data...')
    _lv = stats.level
    _pr = stats.prestige
    rd_entries = rank_dist.entries if rank_dist else None

    profile_data = {
        'name': stats.name,
        'tag': stats.tag,
        'uid': stats.uid,
        'avatar_url': stats.avatar or '',
        'platform': 'PC',
        'online': stats.state,
        'level': _pr * 500 + _lv if _pr else _lv,
        'level_pct': stats.to_next_level_pct,
        'prestige': _pr,
        'level_icon': 'https://apexlegendsstatus.com/core/level_badge/?level={}'.format(_pr * 500 + _lv if _pr else _lv),
        'rank_name': stats.rank_name,
        'rank_div': stats.rank_div,
        'rank_score': stats.rank_score,
        'rank_img': stats.rank_img,
        'rank_top_pct': stats.rank_top_pct,
        'rank_top_pct_global': stats.rank_top_pct,
        'rank_ladder_pos': stats.rank_ladder_pos,
        'rp_delta': 0,
        'kills': stats.kills,
        'damage': stats.damage,
        'wins': stats.wins,
        'top_legends': [
            {'name': leg['name'], 'kills': leg['kills'], 'icon_url': leg.get('icon', '')}
            for leg in stats.top_legends[:3]
        ],
        'selected_legend': stats.selected_legend_data,
        'season_badges': [],
        'special_badges': [],
        'rank_dist_entries': rd_entries,
    }
    rd_count = len(rd_entries) if rd_entries else 0
    print(f'  rank_dist_entries count: {rd_count}')

    print('\n[4] Generating HTML...')
    html = _build_stats_html(**profile_data)
    out = ROOT / 'preview' / 'stats_debug.html'
    out.write_text(html, encoding='utf-8')
    print(f'  HTML saved to {out} ({len(html)} bytes)')

    # 5. Also render PNG
    print('\n[5] Rendering PNG...')
    from libs.playwright_renderer import _render_card_sync
    png = await _render_card_sync(html, 720)
    png_out = ROOT / 'preview' / 'stats.png'
    png_out.write_bytes(png)
    print(f'  PNG saved to {png_out} ({len(png)} bytes)')

asyncio.run(main())
