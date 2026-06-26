#!/usr/bin/env python3
"""Generate all rank theme previews (dark + light)."""
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

RANKS = [
    ("Rookie", 0, 0, ""),
    ("Bronze", 1, 800, "https://apexlegendsstatus.com/assets/ranks/bronze1.png"),
    ("Silver", 1, 1200, "https://apexlegendsstatus.com/assets/ranks/silver1.png"),
    ("Gold", 1, 2000, "https://apexlegendsstatus.com/assets/ranks/gold1.png"),
    ("Platinum", 1, 3000, "https://apexlegendsstatus.com/assets/ranks/platinum1.png"),
    ("Diamond", 1, 4000, "https://apexlegendsstatus.com/assets/ranks/diamond1.png"),
    ("Master", 0, 5000, "https://apexlegendsstatus.com/assets/ranks/master.png"),
    ("Predator", 0, 6000, "https://apexlegendsstatus.com/assets/ranks/predator.png"),
]

async def main():
    out_dir = ROOT / 'preview' / 'themes'
    out_dir.mkdir(exist_ok=True)

    for rank_name, div, score, img in RANKS:
        for theme in ['dark', 'light']:
            html = _build_stats_html(
                name='TestPlayer', tag='', uid='123456',
                avatar_url='', platform='PC', online='online',
                level=500, level_pct=50, prestige=1,
                level_icon='',
                rank_name=rank_name, rank_div=div, rank_score=score,
                rank_img=img,
                rank_top_pct=5.0, rank_top_pct_global=5.0, rank_ladder_pos=0,
                rp_delta=0, kills=25000, damage=8500000, wins=1200,
                top_legends=[
                    {'name': 'Wraith', 'kills': 8500, 'icon_url': 'https://apexlegendsstatus.com/assets/legends-select/wraith.png'},
                    {'name': 'Horizon', 'kills': 6200, 'icon_url': 'https://apexlegendsstatus.com/assets/legends-select/horizon.png'},
                    {'name': 'Octane', 'kills': 4100, 'icon_url': 'https://apexlegendsstatus.com/assets/legends-select/octane.png'},
                ],
                selected_legend={
                    'name': 'Wraith', 'icon_url': 'https://apexlegendsstatus.com/assets/legends-select/wraith.png',
                    'stats': [{'name': '击杀', 'value': '8,500'}, {'name': '胜场', 'value': '420'}],
                },
                season_badges=[], special_badges=[], rank_dist_entries=None,
            )
            # Force theme
            if theme == 'light':
                html = html.replace('body class=""', 'body class="light"')
            else:
                html = html.replace('body class="light"', 'body class=""')

            fname = f'{rank_name.lower()}_{theme}'
            png = await _render_card_sync(html, 720)
            (out_dir / f'{fname}.png').write_bytes(png)
            print(f'  {fname}.png ({len(png)} bytes)')

    print(f'\nAll done! {len(RANKS) * 2} previews saved to {out_dir}')

asyncio.run(main())
