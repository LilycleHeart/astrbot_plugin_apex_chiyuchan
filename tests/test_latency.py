"""Focused regressions for command latency and concurrent data loading."""

import asyncio
import importlib.util
import sys
import types
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

import httpx

from test_rp_window import ROOT
from libs import apex_client, playwright_manager, steamcharts_scraper
from libs.apex_client import PlayerStats
from libs import ttl_cache
from libs import als_scraper

spec = importlib.util.spec_from_file_location(
    "latency_test_plugin", ROOT / "main.py", submodule_search_locations=[str(ROOT)]
)
plugin = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = plugin
spec.loader.exec_module(plugin)


class ProfileTests(unittest.IsolatedAsyncioTestCase):
    async def test_inventory_modern_fields_and_rank_tooltip_stay_scoped(self):
        from bs4 import BeautifulSoup
        from html import escape

        tooltip = (
            '<p class="ranking-tooltip-subtitle">&gt;&gt; Global</p>'
            '<p class="ranking-tooltip-value">#<b>900</b> (top 2%)</p>'
            '<p class="ranking-tooltip-subtitle">&gt;&gt; PC only</p>'
            '<p class="ranking-tooltip-value">#<b>700</b> (top 1%)</p>'
        )
        html = (
            '<div class="v2-sb-stat--level"><strong class="v2-sb-stat__value">127</strong>'
            '<span>Prestige 2</span><img alt="level" src="/level?level=1127"></div>'
            '<div class="v2-sb-stat--rank"><strong class="v2-sb-stat__value">12,345 <em>RP</em></strong>'
            f'<span class="v2-sb-stat__pill--rank" title="{escape(tooltip, quote=True)}">Top <span>1%</span></span></div>'
            '<div class="v2-legend"><h2 class="profile-legend__name">Global</h2>'
            '<div class="v2-stat"><span class="v2-stat__label">Career Kills</span>'
            '<span class="amount__total">2,345</span></div></div>'
            '<div class="v2-legend"><h2 class="profile-legend__name">Other Legend</h2>'
            '<div class="v2-stat"><span class="v2-stat__label">BR Wins</span>'
            '<span class="amount__total">101</span><span>#123</span></div></div>'
        )
        result = als_scraper._parse_profile(
            BeautifulSoup(html, "html.parser"), "https://example.com/profile"
        )
        self.assertEqual((result["level"], result["prestige"]), (127, 2))
        self.assertEqual(
            (result["rankScore"], result["rankPos"], result["rankPcPos"]),
            (12345, 900, 700),
        )
        self.assertEqual((result["kills"], result["wins"]), (2345, 0))
        page = types.SimpleNamespace(content=AsyncMock(return_value=html))
        with patch.object(
            als_scraper,
            "_load_profile",
            AsyncMock(return_value="https://example.com/profile"),
        ):
            self.assertEqual(await als_scraper._do_fetch(page, "123", "PC"), result)

    async def test_inventory_preserves_all_media_and_limits_only_card_display(self):
        from bs4 import BeautifulSoup
        from libs.playwright_renderer import _build_stats_html

        names = ["shared_rs1", "shared_rs2"] + [f"badge_{i}" for i in range(5)]
        urls = [f"https://example.com/badges/badges_new/{name}.png" for name in names]
        html = "".join(f'<img src="{url}">' for url in urls + urls[:1])
        result = als_scraper._parse_profile(
            BeautifulSoup(html, "html.parser"), "https://example.com/profile"
        )
        self.assertEqual({item["badge_url"] for item in result["special"]}, set(urls))
        self.assertEqual(len(result["special"]), 7)
        rendered = _build_stats_html(
            name="Player", uid="123", special_badges=result["special"]
        )
        self.assertEqual(sum(url in rendered for url in urls), 5)
        self.assertIn(urls[0], rendered)
        self.assertNotIn(urls[1], rendered)

    async def test_public_bootstrap_preserves_uid_query_and_media_base(self):
        url = "https://apexlegendsstatus.com/profile/uid/PC/123"
        document = """<script>let token = "public&token";
        fetchApiData("/core/interface-v2?token="+token+"&platform=PC&uid=123");</script>"""
        fragment = '<div class="als-v2"><img src="/badge.png"></div><script>unexpected()</script>'
        responses = [
            httpx.Response(200, text=document, request=httpx.Request("GET", url)),
            httpx.Response(200, text=fragment, request=httpx.Request("GET", url)),
        ]
        client = types.SimpleNamespace(get=AsyncMock(side_effect=responses))
        with patch("libs.http_client.get_async_client", AsyncMock(return_value=client)):
            soup, base = await als_scraper._get_profile_soup("123", "PC")
        request = httpx.URL(client.get.call_args_list[1].args[0])
        self.assertEqual(
            dict(request.params),
            {"token": "public&token", "platform": "PC", "uid": "123"},
        )
        self.assertEqual(base, url)
        self.assertEqual(soup.select_one("img")["src"], "/badge.png")

    async def test_unknown_bootstrap_falls_back_to_live_browser(self):
        from contextlib import asynccontextmanager

        url = "https://apexlegendsstatus.com/profile/PC/Some%20Player"
        response = httpx.Response(
            200,
            text="<script>fetchApiData(newContract)</script>",
            request=httpx.Request("GET", url),
        )
        client = types.SimpleNamespace(get=AsyncMock(return_value=response))
        marker = object()

        @asynccontextmanager
        async def browser_page():
            yield marker

        result = {"seasons": [], "special": [], "rankTopPct": 1.2}
        with (
            patch("libs.http_client.get_async_client", AsyncMock(return_value=client)),
            patch.object(als_scraper, "run_with_page", browser_page),
            patch.object(
                als_scraper, "_do_fetch", AsyncMock(return_value=result)
            ) as fallback,
        ):
            actual = await als_scraper.fetch_badges("Some Player", force=True)
        self.assertEqual(actual, result)
        fallback.assert_awaited_once_with(marker, "Some Player", "PC")


class PoolTests(unittest.IsolatedAsyncioTestCase):
    async def test_context_scale_reuse_and_exception_cleanup(self):
        contexts = []

        async def new_context(**kwargs):
            context = types.SimpleNamespace(
                scale=kwargs["device_scale_factor"],
                new_page=AsyncMock(),
                close=AsyncMock(),
            )
            contexts.append(context)
            return context

        browser = types.SimpleNamespace(new_context=AsyncMock(side_effect=new_context))
        with (
            patch.object(playwright_manager, "_context_pools", {}),
            patch.object(
                playwright_manager, "get_browser", AsyncMock(return_value=browser)
            ),
        ):
            async with playwright_manager.run_with_page():
                pass
            with self.assertRaisesRegex(RuntimeError, "render failed"):
                async with playwright_manager.run_with_page(device_scale_factor=3):
                    raise RuntimeError("render failed")
            async with playwright_manager.run_with_page():
                pass
            async with playwright_manager.run_with_page(device_scale_factor=3):
                pass
            self.assertEqual([c.scale for c in contexts], [1, 3])
            self.assertEqual([c.new_page.await_count for c in contexts], [2, 2])
            for context in contexts:
                self.assertEqual(context.new_page.return_value.close.await_count, 2)
                await context.close()


class LoadingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        ttl_cache._cache.clear()

    async def test_predator_requests_overlap_and_cached_change_is_preserved(self):
        ready = asyncio.Event()
        active = 0

        async def arrive():
            nonlocal active
            active += 1
            if active == 2:
                ready.set()
            await asyncio.wait_for(ready.wait(), 1)

        async def get(*args):
            await arrive()
            return {"RP": {"PC": {"val": 17000, "totalMastersAndPreds": 123}}}

        async def changes(pred, client):
            await arrive()
            pred.platforms["PC"].rp_change_24h = 321

        client = apex_client.ApexClient("")
        with (
            patch.object(client, "_get", AsyncMock(side_effect=get)) as request,
            patch.object(client, "_get_client", AsyncMock(return_value=object())),
            patch.object(apex_client, "_fill_predator_changes", side_effect=changes),
        ):
            first = await client.get_predator()
            second = await client.get_predator()
        self.assertEqual(request.await_count, 1)
        self.assertEqual(first.platforms["PC"].rp_change_24h, 321)
        self.assertEqual(second.platforms["PC"].rp_change_24h, 321)
        self.assertEqual(second.platforms["PC"].predator_cap, 17000)

    async def test_steam_parallel_requests_keep_counts_when_chart_fails(self):
        ready = asyncio.Event()
        calls = 0
        html = "".join(
            f'<div class="app-stat"><span class="num">{value}</span><br>players</div>'
            for value in ("123,456", "234,567", "345,678")
        )

        async def get(url, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                ready.set()
            await asyncio.wait_for(ready.wait(), 1)
            if "chart-data" in url:
                raise httpx.ReadTimeout("chart unavailable")
            return httpx.Response(200, text=html, request=httpx.Request("GET", url))

        with patch(
            "libs.http_client.get_async_client",
            AsyncMock(return_value=types.SimpleNamespace(get=get)),
        ):
            result = await steamcharts_scraper.fetch_steamcharts()
        self.assertEqual(calls, 2)
        self.assertEqual((result.current_online, result.peak_24h), (123456, 234567))
        self.assertEqual(result.raw_7d_points, [])


class LFGTests(unittest.IsolatedAsyncioTestCase):
    async def test_command_and_tool_keep_order_with_three_player_limit(self):
        bot = plugin.XiaoChiyu.__new__(plugin.XiaoChiyu)
        bot._lfg_refresh_limit = asyncio.Semaphore(3)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        users = [
            dict(
                qq_id=str(i),
                uid=str(i),
                platform="PC",
                mode="ranked",
                qq_name=f"P{i}",
                name=f"Apex{i}",
                stats_updated_at=now,
                rank_score=i,
                level=100,
            )
            for i in range(4)
        ]
        bot.db = types.SimpleNamespace(list_lfg_users=AsyncMock(return_value=users))
        active = peak = 0
        gate = asyncio.Event()

        async def stats(uid, platform):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            if active == 3:
                gate.set()
            await asyncio.wait_for(gate.wait(), 1)
            await asyncio.sleep(0)
            active -= 1
            return PlayerStats(
                {"global": {"uid": uid}, "realtime": {"currentState": "online"}}
            )

        bot.apex = types.SimpleNamespace(
            get_stats=stats, get_rank_distribution=AsyncMock(return_value=None)
        )
        bot._resolve_admin_target = AsyncMock(return_value=("qq", "list", None))
        event = types.SimpleNamespace(
            get_sender_id=lambda: "qq",
            get_message_str=lambda: "/lfg list",
            unified_msg_origin="group",
            bot=object(),
            set_extra=lambda *args: None,
            plain_result=lambda text: text,
        )

        async def send_card(event, img):
            yield img

        bot._send_card = send_card
        with patch.object(
            plugin.renderer, "draw_lfg_card", AsyncMock(return_value=None)
        ) as render:
            await asyncio.wait_for(anext(bot.cmd_lfg(event)), 2)
            result = await asyncio.wait_for(anext(bot.llm_lfg(event)), 2)
        self.assertEqual(peak, 3)
        self.assertEqual(
            [entry["qq_id"] for entry in render.call_args_list[0].args[0]],
            ["0", "1", "2", "3"],
        )
        self.assertEqual(
            [entry["qq_id"] for entry in render.call_args_list[1].args[0]],
            ["0", "1", "2", "3"],
        )
        self.assertIn("当前找队友列表 (4 人)", result)
        self.assertLess(result.index("P0"), result.index("P3"))


if __name__ == "__main__":
    unittest.main()
