#!/usr/bin/env python3
"""Generate light theme preview."""
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

from libs.playwright_renderer import _build_stats_html, _render_card_sync

async def main():
    html = _build_stats_html(
        name='AncallBelle', tag='', uid='1000392976892',
        avatar_url='', platform='PC', online='offline',
        level=1601, level_pct=46, prestige=3,
        level_icon='https://apexlegendsstatus.com/core/level_badge/?level=1601',
        rank_name='Platinum', rank_div=1, rank_score=1324,
        rank_img='https://apexlegendsstatus.com/assets/ranks/platinum1.png',
        rank_top_pct=16.86, rank_top_pct_global=16.86, rank_ladder_pos=0,
        rp_delta=0, kills=12429, damage=3613494, wins=419,
        top_legends=[
            {'name': 'Wraith', 'kills': 8950, 'icon_url': 'https://apexlegendsstatus.com/assets/legends-select/wraith.png'},
            {'name': 'Horizon', 'kills': 1972, 'icon_url': 'https://apexlegendsstatus.com/assets/legends-select/horizon.png'},
            {'name': 'Valkyrie', 'kills': 766, 'icon_url': 'https://apexlegendsstatus.com/assets/legends-select/valkyrie.png'},
        ],
        selected_legend={
            'name': 'Ballistic', 'icon_url': 'https://apexlegendsstatus.com/assets/legends-select/ballistic.png',
            'stats': [],
        },
        season_badges=[], special_badges=[], rank_dist_entries=None,
    )
    # Force light theme
    html = html.replace('body class=""', 'body class="light"')
    out = ROOT / 'preview' / 'stats_light.html'
    out.write_text(html, encoding='utf-8')
    print(f'Light theme HTML saved to {out}')

    png = await _render_card_sync(html, 720)
    png_out = ROOT / 'preview' / 'stats_light.png'
    png_out.write_bytes(png)
    print(f'Light theme PNG saved to {png_out} ({len(png)} bytes)')

asyncio.run(main())
