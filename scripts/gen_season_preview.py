"""本地预览赛季信息卡片：真实数据 → Jinja HTML → Playwright PNG。

用法（仓库根目录）：
    python scripts/gen_season_preview.py [--live-meta]

默认使用固定的 META 样例数据，避免依赖 ALS meta 页面；加 --live-meta 时
尝试真实抓取，失败自动回退样例。输出：
    data/preview_season/season.html
    data/preview_season/season.png
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

_OUT = _ROOT / "data" / "preview_season"

# 样例 META（真实抓取失败时使用；图标使用 ALS 公共资源路径）
SAMPLE_META = [
    {"name": "恶灵", "en": "Wraith", "win_rate": "55.1%", "pick_rate": "32.2%"},
    {"name": "地平线", "en": "Horizon", "win_rate": "54.7%", "pick_rate": "28.4%"},
    {"name": "探路者", "en": "Pathfinder", "win_rate": "53.9%", "pick_rate": "19.8%"},
    {"name": "寻血猎犬", "en": "Bloodhound", "win_rate": "53.2%", "pick_rate": "17.5%"},
    {"name": "命脉", "en": "Lifeline", "win_rate": "52.8%", "pick_rate": "15.1%"},
    {"name": "导管", "en": "Conduit", "win_rate": "52.1%", "pick_rate": "12.6%"},
]


def _fallback_meta():
    from libs.season_scraper import SeasonMetaLegend

    return [
        SeasonMetaLegend(
            name=m["name"],
            en=m["en"],
            icon=(
                "https://apexlegendsstatus.com/assets/legends-select/"
                f"{m['en'].lower().replace(' ', '')}.png"
            ),
            win_rate=m["win_rate"],
            pick_rate=m["pick_rate"],
        )
        for m in SAMPLE_META
    ]


async def main() -> int:
    from libs import season_scraper
    from libs.playwright_renderer import _build_season_html, draw_season_card

    _OUT.mkdir(parents=True, exist_ok=True)

    season = await season_scraper.fetch_season_info()
    if season is None:
        print("[ERR] fetch_season_info() 返回 None")
        return 1

    meta = []
    if "--live-meta" in sys.argv:
        try:
            meta = await season_scraper.fetch_meta_top5()
            print(f"[INFO] live meta: {len(meta)} 条")
        except Exception as exc:  # noqa: BLE001 - 预览脚本，失败回退即可
            print(f"[WARN] live meta 失败，回退样例: {type(exc).__name__}: {exc}")
    if not meta:
        meta = _fallback_meta()
        print(f"[INFO] sample meta: {len(meta)} 条")

    html = _build_season_html(season, meta)
    html_path = _OUT / "season.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"[OK] HTML -> {html_path}")

    png = await draw_season_card(season, meta)
    if not png:
        print("[ERR] draw_season_card() 返回空")
        return 1
    png_path = _OUT / "season.png"
    png_path.write_bytes(png)
    print(f"[OK] PNG  -> {png_path} ({len(png)} bytes)")

    print("\n── 卡片数据 ──")
    print(
        f"第{season.season_number}赛季 {season.season_name} | {season.split_label} | "
        f"倒计时 {season.days_left}d {season.hours_left}h {season.minutes_left}m | "
        f"结束 {season.season_end} | 开始 {season.season_start}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
