"""本地预览脚本 — 渲染 Steamcharts 日活卡片到 PNG 文件"""
import asyncio
import sys
import json
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# 跳过 astrbot 依赖：用一个假的 logger 模块
import types
if "astrbot" not in sys.modules:
    astrbot_mod = types.ModuleType("astrbot")
    api_mod = types.ModuleType("astrbot.api")
    class _FakeLogger:
        @staticmethod
        def info(*a, **k): pass
        @staticmethod
        def warning(*a, **k): pass
        @staticmethod
        def error(*a, **k): pass
    api_mod.logger = _FakeLogger
    astrbot_mod.api = api_mod
    sys.modules["astrbot"] = astrbot_mod
    sys.modules["astrbot.api"] = api_mod

from libs.steamcharts_scraper import fetch_steamcharts, _bucket_last_7_days, SteamchartsData, MonthEntry
from libs.playwright_renderer import draw_steamcharts_card


def _http_get(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read()


async def main():
    print("正在抓取 steamcharts 数据...")
    data = await fetch_steamcharts()
    if not data:
        print("fetch_steamcharts 返回 None，尝试手动抓取 chart-data.json 构造数据...")
        # 手动构造一个最小 data 对象用于预览
        data = SteamchartsData(
            current_online=84883,
            peak_24h=194089,
            peak_all_time=624473,
            months=[MonthEntry("Last 30 Days", 113920.9, -15003.2, -11.63, 292553)],
        )
        try:
            raw = json.loads(_http_get("https://steamcharts.com/app/1172470/chart-data.json").decode())
            data.seven_day_buckets = _bucket_last_7_days(raw)
            print(f"  chart-data.json 抓取成功，{len(data.seven_day_buckets)} 个桶")
        except Exception as e:
            print(f"  chart-data.json 抓取失败: {e}")

    print(f"当前在线: {data.current_online:,}")
    print(f"24h 峰值: {data.peak_24h:,}")
    print(f"历史峰值: {data.peak_all_time:,}")
    print(f"7 天桶数: {len(data.seven_day_buckets)}")
    if data.seven_day_buckets:
        print(f"  桶值示例: {[int(b.avg_players) for b in data.seven_day_buckets[:3]]}...")

    print("正在渲染卡片...")
    img = await draw_steamcharts_card(data)
    out = Path(__file__).parent / "preview_steamcharts.png"
    out.write_bytes(img)
    print(f"已保存: {out} ({len(img):,} bytes)")


if __name__ == "__main__":
    asyncio.run(main())

