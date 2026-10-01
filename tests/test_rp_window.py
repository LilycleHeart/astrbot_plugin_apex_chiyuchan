"""Offline regressions: python -m unittest discover -s tests -v."""
import asyncio
import importlib.util
import logging
import sqlite3
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# AstrBot is supplied by the host in production. No bot, API, browser, or LLM is
# started by these tests; every data directory is an isolated temporary folder.
for name in (
    "astrbot", "astrbot.api", "astrbot.api.event", "astrbot.api.star",
    "astrbot.api.message_components", "astrbot.core", "astrbot.core.message",
    "astrbot.core.message.message_event_result", "astrbot.core.utils",
    "astrbot.core.utils.astrbot_path",
):
    sys.modules[name] = types.ModuleType(name)
sys.modules["astrbot.api"].logger = logging.getLogger("apex-tests")
sys.modules["astrbot.api"].AstrBotConfig = dict
sys.modules["astrbot.core.utils.astrbot_path"].get_astrbot_data_path = lambda: "unused"
decorator = lambda *a, **kw: lambda f: f
sys.modules["astrbot.api.event"].filter = types.SimpleNamespace(
    command=decorator, llm_tool=decorator, on_astrbot_loaded=decorator,
)
sys.modules["astrbot.api.event"].AstrMessageEvent = object
sys.modules["astrbot.api.star"].Context = object
sys.modules["astrbot.api.star"].Star = object
sys.modules["astrbot.api.star"].register = decorator
sys.modules["astrbot.core.message.message_event_result"].MessageChain = list
sys.modules["astrbot.api.message_components"].Image = object
sys.modules["astrbot.api.message_components"].Plain = str

from libs.database import Database
from libs.apex_client import PlayerStats
from libs.playwright_renderer import _build_rp_chart_html, _build_stats_html
from libs.rp_window import RPWindow, calculate_rp_window

NOW = datetime(2026, 9, 30, 18, 0, 0)
SEASON = "season30_split_2"


def row(score, age_hours, season=SEASON):
    return {"rank_score": score, "recorded_at": (NOW - timedelta(hours=age_hours)).strftime("%Y-%m-%d %H:%M:%S"), "rank_season": season}


class WindowTests(unittest.TestCase):
    def test_exact_boundary(self):
        result = calculate_rp_window([row(1000, 24)], 1500, NOW, SEASON)
        self.assertEqual((result.delta, result.status), (500, "exact"))

    def test_near_boundary_is_estimated(self):
        result = calculate_rp_window([row(1000, 25)], 1500, NOW, SEASON)
        self.assertEqual((result.delta, result.status), (500, "estimated"))
        self.assertEqual(result.text, "▲ ≈+500 · 24h")

    def test_six_hour_gap_limit_inclusive(self):
        self.assertEqual(calculate_rp_window([row(1000, 30)], 1500, NOW, SEASON).delta, 500)
        self.assertIsNone(calculate_rp_window([row(1000, 30.01)], 1500, NOW, SEASON).delta)

    def test_new_short_and_long_gap_history(self):
        for rows in ([], [row(1000, 23)], [row(1000, 72)]):
            with self.subTest(rows=rows):
                result = calculate_rp_window(rows, 1500, NOW, SEASON)
                self.assertIsNone(result.delta)
                self.assertEqual(result.text, "24h 暂无")

    def test_normal_large_loss_is_not_reset(self):
        result = calculate_rp_window([row(20000, 24)], 10000, NOW, SEASON)
        self.assertEqual((result.delta, result.status), (-10000, "exact"))

    def test_known_reset_not_reported_as_loss(self):
        result = calculate_rp_window([row(20000, 24, "season30_split_1")], 8000, NOW, SEASON)
        self.assertEqual(result.status, "reset")
        self.assertIsNone(result.delta)

    def test_missing_season_not_assigned_to_new_season(self):
        baseline = row(1000, 24, None)
        result = calculate_rp_window([baseline], 1500, NOW, SEASON)
        self.assertEqual((result.delta, result.status), (500, "estimated"))
        self.assertIsNone(baseline["rank_season"])

    def test_legacy_missing_metadata_and_loss_remain_supported(self):
        result = calculate_rp_window([row(1000, 24, None)], 950, NOW, None)
        self.assertEqual((result.delta, result.status), (-50, "estimated"))

    def test_current_missing_season_is_estimated(self):
        result = calculate_rp_window([row(1000, 24)], 1500, NOW, None)
        self.assertEqual((result.delta, result.status), (500, "estimated"))

    def test_legacy_baseline_with_known_current_preserves_loss(self):
        result = calculate_rp_window([row(20000, 24, None)], 10000, NOW, SEASON)
        self.assertEqual((result.delta, result.status), (-10000, "estimated"))

    def test_known_change_after_legacy_baseline_is_rejected(self):
        result = calculate_rp_window(
            [row(9000, 12, "season30_split_1"), row(10000, 24, None)],
            8000, NOW, SEASON,
        )
        self.assertEqual(result.status, "reset")
        self.assertIsNone(result.delta)

    def test_matching_endpoints_do_not_hide_intervening_season_change(self):
        result = calculate_rp_window(
            [row(9000, 12, "season30_split_1"), row(10000, 24)],
            10500, NOW, SEASON,
        )
        self.assertEqual(result.status, "reset")
        self.assertIsNone(result.delta)

    def test_known_change_detected_without_current_season(self):
        result = calculate_rp_window(
            [row(9000, 12), row(20000, 24, "season30_split_1")],
            9500, NOW, None,
        )
        self.assertEqual(result.status, "reset")

    def test_before_baseline_and_future_seasons_are_ignored(self):
        result = calculate_rp_window(
            [row(9000, -1, "future"), row(1000, 24), row(20000, 25, "old")],
            1500, NOW, SEASON,
        )
        self.assertEqual((result.delta, result.status), (500, "exact"))

    def test_invalid_timestamp_skipped(self):
        result = calculate_rp_window(
            [{"recorded_at": "bad", "rank_score": 99999, "rank_season": SEASON}, row(1000, 24)],
            1500, NOW, SEASON,
        )
        self.assertEqual(result.delta, 500)

    def test_zero_is_displayed_without_up_arrow(self):
        html = _build_rp_chart_html([], RPWindow(delta=0, status="exact"))
        self.assertIn("+0 · 24h", html)
        self.assertNotIn("rp-up", html)
        self.assertNotIn("▲", html)

    def test_renderer_does_not_guess_from_two_points(self):
        entries = [{"score": 1000, "at": "2026-09-30 10:00:00"}, {"score": 1200, "at": "2026-09-30 11:00:00"}]
        self.assertNotIn("24h", _build_rp_chart_html(entries))
        html = _build_rp_chart_html(entries, RPWindow(delta=700, status="estimated"))
        self.assertIn("▲ ≈+700 · 24h", html)
        self.assertNotIn("+200", html)
        self.assertNotIn("净变化", html)

    def test_compact_card_text_and_original_delta_style(self):
        for delta, text, cls in ((500, "▲ +500 · 24h", "rp-up"), (-50, "▼ -50 · 24h", "rp-down")):
            with self.subTest(delta=delta):
                html = _build_stats_html(rank_score=1500, rp_24h=RPWindow(delta=delta, status="exact"), rp_delta=50)
                self.assertIn(text, html)
                self.assertIn(f'<span class="{cls}" style="font-size:11px;font-weight:700;">', html)
                self.assertIn('<span class="rp-up" style="font-size:13px;margin-left:8px;">+50 RP</span>', html)
                for extra in ("较上次", "净变化", "缺少同赛季", "估算"):
                    self.assertNotIn(extra, html)

    def test_card_displays_insufficient_without_two_chart_points(self):
        html = _build_stats_html(rank_score=1500, rp_24h=RPWindow(), rp_delta=50)
        self.assertIn("24h 暂无", html)
        self.assertIn("+50 RP", html)

    def test_api_rank_season_optional(self):
        self.assertEqual(PlayerStats({"global": {"rank": {"rankedSeason": SEASON}}}).rank_season, SEASON)
        for season in (None, "", 0, {}):
            self.assertIsNone(PlayerStats({"global": {"rank": {"rankedSeason": season}}}).rank_season)


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path_patch = patch("libs.database.get_astrbot_data_path", return_value=self.temp.name)
        self.path_patch.start()
        self.db = Database()
        await self.db.init()

    async def asyncTearDown(self):
        await self.db.close()
        self.path_patch.stop()
        self.temp.cleanup()

    async def seed(self, score, age, *, uid="player", platform="PC", season=SEASON):
        await self.db.save_rp(uid, platform, score, now=NOW - timedelta(hours=age), rank_season=season)

    async def snapshot(self, score=1500, now=NOW):
        return await self.db.record_rp_snapshot("player", "PC", score, now=now, rank_season=SEASON)

    async def test_multiple_changes_are_not_last_query_delta(self):
        await self.seed(1000, 24)
        await self.seed(1400, 10)
        await self.seed(1200, 2)
        result = await self.snapshot()
        self.assertEqual(result["rp_24h"].delta, 500)
        self.assertEqual(result["rp_delta"], 300)

    async def test_baseline_independent_of_chart_limit(self):
        await self.seed(1000, 24)
        for i in range(23, 0, -1):
            await self.seed(1500 - i, i)
        result = await self.snapshot()
        self.assertEqual(len(result["rp_history"]), 12)
        self.assertEqual(result["rp_24h"].delta, 500)
        self.assertEqual(result["rp_history"][-1], {"score": 1500, "at": "2026-09-30 18:00:00"})

    async def test_unchanged_scores_persist_and_old_gain_expires(self):
        await self.seed(1000, 25)
        await self.seed(1500, 24)
        for age in (18, 12, 6):
            await self.seed(1500, age)
        result = await self.snapshot()
        self.assertEqual(result["rp_24h"].delta, 0)
        self.assertEqual(len(await self.db.get_rp_history("player", "PC")), 6)
        self.assertEqual(result["rp_history"][-1]["at"], "2026-09-30 18:00:00")

    async def test_stale_gain_after_days_is_insufficient(self):
        await self.seed(1000, 73)
        await self.seed(1500, 72)
        result = await self.snapshot()
        self.assertIsNone(result["rp_24h"].delta)
        self.assertEqual(result["rp_history"][-1]["at"], "2026-09-30 18:00:00")

    async def test_boundary_uses_latest_at_or_before_not_after(self):
        await self.seed(900, 25)
        await self.seed(1000, 24)
        await self.seed(1400, 23.99)
        self.assertEqual((await self.snapshot())["rp_24h"].delta, 500)

    async def test_equal_timestamps_tie_break_by_id(self):
        await self.seed(900, 24, season="season30_split_1")
        await self.seed(1000, 24)
        self.assertEqual((await self.snapshot())["rp_24h"].delta, 500)

    async def test_window_checks_intervening_seasons_not_just_endpoints(self):
        await self.seed(1000, 24, season=None)
        await self.seed(1200, 12, season="season30_split_1")
        await self.seed(1400, 1)
        result = await self.snapshot()
        self.assertEqual(result["rp_24h"].status, "reset")
        self.assertIsNone(result["rp_24h"].delta)

    async def test_season_evidence_is_player_platform_and_time_isolated(self):
        await self.seed(1000, 24, season=None)
        await self.seed(1200, 12, uid="other", season="old")
        await self.seed(1200, 12, platform="PS4", season="old")
        await self.seed(20000, 25, season="old")
        await self.seed(20000, -1, season="future")
        result = await self.snapshot()
        self.assertEqual((result["rp_24h"].delta, result["rp_24h"].status), (500, "estimated"))

    async def test_time_order_not_insertion_order_for_window(self):
        await self.seed(1000, 24)
        await self.seed(900, 25)
        self.assertEqual((await self.snapshot())["rp_24h"].delta, 500)

    async def test_player_and_platform_isolation(self):
        await self.seed(5, 24, uid="other")
        await self.seed(6, 24, platform="PS4")
        self.assertIsNone((await self.snapshot())["rp_24h"].delta)

    async def test_first_query_has_no_invented_gain(self):
        result = await self.snapshot()
        self.assertIsNone(result["rp_delta"])
        self.assertIsNone(result["rp_24h"].delta)
        self.assertEqual(len(result["rp_history"]), 1)

    async def test_reset_metadata_persists_after_reopen(self):
        await self.seed(20000, 24, season="season30_split_1")
        await self.db.close()
        self.db = Database()
        await self.db.init()
        result = await self.snapshot(8000)
        self.assertEqual(result["rp_24h"].status, "reset")

    async def test_latest_observation_committed_before_return(self):
        await self.snapshot()
        await self.db.close()
        self.db = Database()
        await self.db.init()
        self.assertEqual(await self.db.get_rp_delta("player", "PC", 1600), 100)

    async def test_background_sampling_saves_same_score(self):
        await self.seed(1500, 24)
        await self.seed(1500, 12)
        self.assertEqual(len(await self.db.get_rp_history("player", "PC")), 2)

    async def test_parallel_snapshots_do_not_lose_observations(self):
        await self.seed(1000, 24)
        results = await asyncio.gather(self.snapshot(1400), self.snapshot(1500))
        self.assertEqual([r["rp_delta"] for r in results], [400, 100])
        self.assertEqual(len(await self.db.get_rp_history("player", "PC")), 3)

    async def test_migration_preserves_legacy_local_timestamp(self):
        await self.db.close()
        with sqlite3.connect(self.db.db_path) as conn:
            conn.execute("DROP TABLE rp_history")
            conn.execute("CREATE TABLE rp_history (uid TEXT, platform TEXT, rank_score INTEGER, recorded_at TEXT, PRIMARY KEY (uid, platform))")
            conn.execute("INSERT INTO rp_history VALUES ('player', 'PC', 1000, '2026-09-29 18:00:00')")
        await self.db.init()
        await self.db.init()  # migration must be idempotent
        history = await self.db.get_rp_history("player", "PC")
        self.assertEqual(history, [{"score": 1000, "at": "2026-09-29 18:00:00"}])
        self.assertEqual((await self.db.get_rp_window("player", "PC", 1500, now=NOW)).delta, 500)
        result = (await self.snapshot())["rp_24h"]
        self.assertEqual((result.delta, result.status), (500, "estimated"))
        await self.db.close()
        self.db = Database()
        await self.db.init()
        conn = await self.db._get_conn()
        async with conn.execute("SELECT rank_season, recorded_at FROM rp_history ORDER BY id") as cursor:
            rows = await cursor.fetchall()
        self.assertIsNone(rows[0]["rank_season"])
        self.assertEqual(rows[0]["recorded_at"], "2026-09-29 18:00:00")
        self.assertEqual((await self.snapshot())["rp_24h"].delta, 500)

    async def test_append_only_legacy_migration_keeps_rows_and_season_unknown(self):
        await self.db.close()
        with sqlite3.connect(self.db.db_path) as conn:
            conn.execute("DROP TABLE rp_history")
            conn.execute("CREATE TABLE rp_history (id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT, platform TEXT, rank_score INTEGER, recorded_at TEXT)")
            conn.executemany("INSERT INTO rp_history (uid, platform, rank_score, recorded_at) VALUES ('player', 'PC', ?, ?)", [
                (1000, "2026-09-29 18:00:00"),
                (1200, "2026-09-30 16:00:00"),
            ])
        await self.db.init()
        await self.db.init()
        result = await self.snapshot()
        self.assertEqual((result["rp_24h"].delta, result["rp_24h"].status), (500, "estimated"))
        self.assertEqual(result["rp_delta"], 300)
        conn = await self.db._get_conn()
        async with conn.execute("SELECT rank_season FROM rp_history WHERE id <= 2 ORDER BY id") as cursor:
            self.assertEqual([r[0] for r in await cursor.fetchall()], [None, None])

    async def test_command_and_llm_share_window_and_persistence(self):
        spec = importlib.util.spec_from_file_location("apex_test_plugin", ROOT / "main.py", submodule_search_locations=[str(ROOT)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        stats = PlayerStats({"global": {"uid": "player", "rank": {"rankScore": 1500, "rankedSeason": SEASON}}})
        bot = module.XiaoChiyu.__new__(module.XiaoChiyu)
        bot.db = self.db
        bot.apex = types.SimpleNamespace(get_stats=AsyncMock(return_value=stats), get_rank_distribution=AsyncMock(return_value=None))
        bot._get_badges_cached = AsyncMock(return_value={})
        bot._extract_at_target = lambda event, rest: ("", rest)
        bot._calc_global_pct = lambda *args: 0
        bot._profile_cache = {}
        bot._last_search = {}
        async def send_card(event, image):
            yield "card"
        bot._send_card = send_card
        event = types.SimpleNamespace(get_sender_id=lambda: "qq", get_message_str=lambda: "/stats", plain_result=lambda text: text)
        await self.db.upsert_user("qq", "player", "Player", "PC")
        await self.seed(1000, 24)
        await self.seed(1200, 2)
        original = self.db.record_rp_snapshot
        async def fixed_snapshot(*args, **kwargs):
            return await original(*args, now=NOW, **kwargs)
        with patch.object(self.db, "record_rp_snapshot", side_effect=fixed_snapshot), patch.object(module.renderer, "draw_profile_card", new=AsyncMock(return_value=None)) as render:
            _ = [result async for result in bot.cmd_stats(event)]
            text = [result async for result in bot.llm_stats(event)]
        first, second = [call.args[0] for call in render.call_args_list]
        self.assertEqual(first["rp_24h"].delta, 500)
        self.assertEqual(second["rp_24h"].delta, 500)
        self.assertEqual(first["rp_delta"], 300)
        self.assertEqual(second["rp_delta"], 0)
        self.assertIn("▲ +500 · 24h", text[0])
        self.assertIn("(+0 RP)", text[0])
        self.assertNotIn("较上次", text[0])


if __name__ == "__main__":
    unittest.main()
