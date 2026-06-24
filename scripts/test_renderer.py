#!/usr/bin/env python3
"""Standalone end-to-end preview: fetch real data ->  render all 4 Jinja cards ->  screenshot.
Can run without Astrbot environment. Requires: playwright, httpx, jinja2, Pillow."""

from __future__ import annotations

import json
import asyncio
import re
import sys
import time
import types
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ── ensure project root on sys.path ──
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── Patch astrbot before any lib imports ──
astrbot_pkg = types.ModuleType("astrbot")
astrbot_api = types.ModuleType("astrbot.api")
astrbot_api.logger = types.ModuleType("logger")


class _Logger:
    @staticmethod
    def info(msg, *a, **kw): print(f"[INFO] {msg}")
    @staticmethod
    def warning(msg, *a, **kw): print(f"[WARN] {msg}")
    @staticmethod
    def error(msg, *a, **kw): print(f"[ERR]  {msg}")
    @staticmethod
    def debug(msg, *a, **kw): pass


astrbot_api.logger = _Logger()
astrbot_pkg.api = astrbot_api
sys.modules["astrbot"] = astrbot_pkg
sys.modules["astrbot.api"] = astrbot_api
sys.modules["astrbot.api.logger"] = _Logger

# ── now safe to import project libs ──
from libs.playwright_renderer import (
    _build_server_status_html,
    _build_map_rotation_html,
    _build_predator_html,
    _render_steamcharts_html,
)
from libs.als_scraper import scrape_als_server_status, AlsServerStatus
from libs.steamcharts_scraper import fetch_steamcharts
from libs.playwright_manager import run_with_page

_OUT = ROOT / "data" / "preview_real"
_OUT.mkdir(parents=True, exist_ok=True)

_TZ_CST = timezone(timedelta(hours=8))

# ── API key from env / _conf_schema.json ──
_APEX_API_KEY = ""

def _load_api_key() -> str:
    """Try multiple sources for the API key, returning the first non-empty string found."""
    # 1. Environment variable (highest priority for CI/testing)
    key = __import__("os").environ.get("APEX_API_KEY", "")
    if key:
        return key
    # 2. Plugin config JSON (_conf_schema.json is the schema, look for plugin config dirs)
    #    AstrBot v4 stores plugin config at ASTRBOT_PLUGIN_CONFIG or similar.
    #    Check common paths:
    for candidate in [
        ROOT / "config.json",
        ROOT / "plugin_config.json",
        ROOT.parent / "config" / "astrbot_plugin_apex_chiyuchan.json",
    ]:
        if candidate.exists():
            try:
                import json as _json
                data = _json.loads(candidate.read_text(encoding="utf-8"))
                val = data.get("apex_api_key", "")
                if isinstance(val, str) and val.strip():
                    return val.strip()
            except Exception:
                pass
    # 3. _conf_schema.json (least priority - schema values are types, check carefully)
    conf_path = ROOT / "_conf_schema.json"
    if conf_path.exists():
        try:
            import json as _json
            data = _json.loads(conf_path.read_text(encoding="utf-8"))
            val = data.get("apex_api_key", "")
            if isinstance(val, str) and val.strip():
                return val.strip()
        except Exception:
            pass
    return ""

_APEX_API_KEY = _load_api_key()

# ══════════════════════════════════════════════════════════
#  Data sources - fallback chain for each card
# ══════════════════════════════════════════════════════════


def _try_als_internal_json(endpoint: str, label: str) -> dict | list | None:
    """Try fetching JSON from ALS internal endpoints (no API key needed)."""
    import httpx
    url = f"https://apexlegendsstatus.com/{endpoint.lstrip('/')}"
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0",
                                   "Referer": "https://apexlegendsstatus.com/",
                                   "Accept": "application/json"}) as c:
            r = c.get(url)
            if r.status_code == 200 and r.text.strip():
                try:
                    return r.json()
                except json.JSONDecodeError:
                    _Logger.info(f"[{label}] Response not JSON (len={len(r.text)})")
                    return None
            _Logger.info(f"[{label}] HTTP {r.status_code}")
            return None
    except Exception as e:
        _Logger.info(f"[{label}] Request failed: {e}")
        return None


async def fetch_server_status_real():
    """Fetch real server status from ALS website scraping."""
    print("  ->  Fetching server status from ALS website...")
    data = await scrape_als_server_status()
    if data and data.sections:
        # wrap in object with .als attribute (as ServerStatus does)
        class _Wrapper:
            def __init__(self, als):
                self.als = als
        print(f"  [+] Got {len(data.sections)} sections, {sum(len(s.entries) for s in data.sections)} entries")
        return _Wrapper(data)
    print("  [x] ALS scraping returned no data, using fallback")
    return None


async def fetch_map_rotation_real():
    """Try ApexClient API first; fall back to ALS endpoints; then mock."""
    print("  -> Fetching map rotation...")

    # Priority 1: ApexClient API (needs key)
    if _APEX_API_KEY:
        try:
            from libs.apex_client import ApexClient
            client = ApexClient(_APEX_API_KEY)
            rot = await client.get_map_rotation()
            await client.close()
            if rot and hasattr(rot, 'br_current') and rot.br_current and rot.br_current.map:
                print(f"  [+] Got map rotation via API: BR={rot.br_current.map}, Ranked={rot.ranked_current.map}")
                return rot
        except Exception as e:
            print(f"  [x] ApexClient map rotation failed: {e}")
    for endpoint in [
        "lib/php/checkrotation.php",
        "includes/ajax.php?action=map_rotation",
        "api/v1/map",
    ]:
        raw = _try_als_internal_json(endpoint, "MapRotation")
        if raw:
            print(f"  [+] Got map data from {endpoint}")
            # Parse into MapRotation-like object
            return _parse_map_rotation(raw)

    # Try 2: Playwright-based scraping of ALS page
    print("  ->  Trying Playwright-based ALS page scraping...")
    try:
        rot = await _scrape_map_rotation_playwright()
        if rot:
            print("  [+] Got map data via Playwright")
            return rot
    except Exception as e:
        print(f"  [x] Playwright scraping failed: {e}")

    print("  [x] No map rotation data available (works with ApexAPI key)")
    return None


async def _scrape_map_rotation_playwright():
    """Try to scrape map rotation from ALS current-map page using Playwright."""
    async with run_with_page() as page:
        await page.route("**/*", lambda route: route.abort()
                         if route.request.resource_type in ("image", "font", "media", "stylesheet")
                         or "analytics" in route.request.url
                         or "googletagmanager" in route.request.url
                         else route.continue_())
        await page.goto("https://apexlegendsstatus.com/current-map",
                        wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)
        # Extract text and try to find map names + timers
        text = await page.evaluate("() => document.body.innerText")
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        print(f"  Page lines (sampled): {lines[:20]}")
    return None


def _parse_map_rotation(raw: any):
    """Try to parse raw JSON into a map rotation object."""
    # We don't need to be too strict - the renderer just needs
    # br_current/br_next/ranked_current/ranked_next with .map/.remaining_timer
    from libs.apex_client import MapRotation, MapData, LTMMode

    if isinstance(raw, dict):
        # Try direct format: {"battle_royale": {"current": {...}, "next": {...}}, ...}
        br = raw.get("battle_royale") or raw.get("battleRoyale") or raw.get("br") or {}
        ranked = raw.get("ranked") or raw.get("ranked_royale") or {}
        ltm = raw.get("ltm") or raw.get("ltm_mode") or {}
        wildcard = raw.get("wildcard", {})

        if br and isinstance(br, dict):
            # Convert MapData for br_current
            cur_raw = br.get("current", {})
            nxt_raw = br.get("next", {})
            if cur_raw and isinstance(cur_raw, dict) and cur_raw.get("map"):
                return MapRotation({
                    "battle_royale": br,
                    "ranked": ranked,
                    "ltm": ltm,
                    "wildcard": wildcard,
                })
    return None


async def fetch_predator_real():
    """Try ApexClient API first; fall back to ALS endpoints; then mock."""
    print("  -> Fetching predator cap data...")

    # Priority 1: ApexClient API (needs key)
    if _APEX_API_KEY:
        try:
            from libs.apex_client import ApexClient
            client = ApexClient(_APEX_API_KEY)
            pred = await client.get_predator()
            await client.close()
            if pred and hasattr(pred, 'platforms') and pred.platforms:
                print(f"  [+] Got predator data via API: PC={pred.platforms.get('PC').predator_cap if pred.platforms.get('PC') else 'N/A'}")
                return pred
        except Exception as e:
            print(f"  [x] ApexClient predator failed: {e}")

    for endpoint in [
        "lib/php/predator.php",
        "includes/ajax.php?action=predator",
        "api/v1/predator",
    ]:
        raw = _try_als_internal_json(endpoint, "Predator")
        if raw:
            print(f"  [+] Got predator data from {endpoint}")
            return _parse_predator(raw)

    print("  [x] No predator data available (works with ApexAPI key)")
    return None


def _parse_predator(raw: any):
    """Try to parse raw JSON into a PredatorData object."""
    from libs.apex_client import PredatorData, PlatformData

    if isinstance(raw, dict):
        rp = raw.get("RP") or raw
        has_rp = all(p in rp for p in ("PC", "PS4", "X1", "SWITCH"))
        if has_rp:
            return PredatorData(raw)
        # try flat format: directly has PC/PS4 keys with val
        if "val" in raw or "totalMastersAndPreds" in raw:
            # single-platform? wrap.
            return PredatorData({"RP": {"PC": raw, "PS4": raw, "X1": raw, "SWITCH": raw}})
    return None


async def fetch_steamcharts_real():
    """Fetch real Steamcharts data (requires astrbot patch which we already applied)."""
    print("  ->  Fetching Steamcharts data...")
    data = await fetch_steamcharts()
    if data and data.current_online:
        print(f"  [+] Got data: {data.current_online:,} current, {data.peak_24h:,} peak 24h, {len(data.raw_7d_points or data.seven_day_buckets or [])} data points")
        return data
    print("  [x] Steamcharts returned no data")
    return None


# ══════════════════════════════════════════════════════════
#  Render helpers
# ══════════════════════════════════════════════════════════

def render_server_status(ss):
    """Render server status card, return HTML string."""
    return _build_server_status_html(ss)


def render_map_rotation(rot):
    """Render map rotation card, return HTML string."""
    return _build_map_rotation_html(rot)


def render_predator(pred):
    """Render predator card, return HTML string."""
    return _build_predator_html(pred)


def render_steamcharts(data):
    """Render steamcharts card, return HTML string."""
    return _render_steamcharts_html(data)


# ══════════════════════════════════════════════════════════
#  Screenshot with Playwright
# ══════════════════════════════════════════════════════════

async def screenshot_html(html: str, path: Path, width: int = 720):
    """Take a Playwright WebKit screenshot of rendered HTML."""
    from libs.playwright_renderer import _embed_images
    html = await _embed_images(html)
    async with run_with_page(viewport={"width": width, "height": 100}, device_scale_factor=3) as page:
        await page.set_content(html, wait_until="load", timeout=20000)
        try:
            await page.wait_for_function("() => document.fonts.ready", timeout=8000)
        except Exception:
            pass
        try:
            card = await page.query_selector(".card, .lfg-list")
        except Exception:
            card = None
        if card:
            png = await card.screenshot(type="png", omit_background=True)
        else:
            png = await page.screenshot(full_page=False, type="png")
        path.write_bytes(png)
    return path


# ══════════════════════════════════════════════════════════
#  Save HTML (for offline inspection)
# ══════════════════════════════════════════════════════════

def save_html(html: str, filename: str):
    path = _OUT / filename
    path.write_text(html, encoding="utf-8")
    print(f"  [HTML] {path}")
    return path


# ══════════════════════════════════════════════════════════
#  Mock fallbacks (used when real data unavailable)
# ══════════════════════════════════════════════════════════

def _make_mock_server_status():
    """Create mock ServerStatus with .als attribute matching template expectations."""
    als = AlsServerStatus()
    # 3 sections with regions
    from libs.als_scraper import AlsServerSection, AlsServerEntry

    s1 = AlsServerSection("Crossplay auth (any platform)", "UP")
    s1.entries.append(AlsServerEntry("PC Login", "UP", "32 ms"))
    s1.entries.append(AlsServerEntry("Console Login", "UP", "45 ms"))
    s1.entries.append(AlsServerEntry("Steam Login", "UP", "28 ms"))
    s1.entries.append(AlsServerEntry("EA App Login", "UP", "56 ms"))
    s1.entries.append(AlsServerEntry("Mobile Login", "UP", "67 ms"))

    s2 = AlsServerSection("Lobby/Matchmaking servers", "UNSTABLE / SLOW")
    s2.entries.append(AlsServerEntry("Tokyo", "UNSTABLE", "120 ms"))
    s2.entries.append(AlsServerEntry("London", "UP", "28 ms"))
    s2.entries.append(AlsServerEntry("Dallas", "SLOW", "850 ms"))
    s2.entries.append(AlsServerEntry("Frankfurt", "UP", "22 ms"))
    s2.entries.append(AlsServerEntry("Singapore", "UP", "35 ms"))

    s3 = AlsServerSection("PSN/Xbox Live status", "DOWN")
    s3.entries.append(AlsServerEntry("PlayStation Network", "DOWN", "timeout"))
    s3.entries.append(AlsServerEntry("Xbox Live", "UP", "18 ms"))

    als.sections.extend([s1, s2, s3])
    als.alert_banner = ""

    class MockSS:
        def __init__(self, als):
            self.als = als
    return MockSS(als)


def _make_mock_rotation():
    """Create mock MapRotation with data matching the template."""
    from libs.apex_client import MapRotation, MapData, LTMMode
    rot = MapRotation({
        "battle_royale": {
            "current": {"map": "Kings Canyon", "remainingTimer": "12:34:56", "remainingMins": 754},
            "next": {"map": "World's Edge", "remainingTimer": "", "remainingMins": 0},
        },
        "ranked": {
            "current": {"map": "Storm Point", "remainingTimer": "08:15:30", "remainingMins": 495},
            "next": {"map": "Broken Moon", "remainingTimer": "", "remainingMins": 0},
        },
        "ltm": {
            "current": {"map": "Skull Town", "remainingTimer": "02:10:00", "remainingMins": 130, "eventName": "闪回大乱斗"},
            "next": {"map": "Olympus", "remainingTimer": "", "remainingMins": 0, "eventName": ""},
        },
        "wildcard": {
            "current": {"map": "Habitat", "remainingTimer": "04:30:00", "remainingMins": 270},
            "next": {"map": "Royalty", "remainingTimer": "", "remainingMins": 0},
        },
    })
    return rot


def _make_mock_predator():
    """Create mock PredatorData matching the template."""
    from libs.apex_client import PredatorData, PlatformData
    pred = PredatorData({
        "RP": {
            "PC": {"val": 15234, "totalMastersAndPreds": 28756},
            "PS4": {"val": 13890, "totalMastersAndPreds": 25432},
            "X1": {"val": 12567, "totalMastersAndPreds": 22345},
            "SWITCH": {"val": 8901, "totalMastersAndPreds": 15678},
        }
    })
    # 填充模拟变动值
    for plat_key, chg in [("PC", 3374), ("PS4", 2324), ("X1", 1632), ("SWITCH", 0)]:
        plat = pred.platforms.get(plat_key)
        if plat:
            plat.rp_change_24h = chg
    return pred


def _make_mock_steamcharts():
    """Create mock SteamchartsData (same as preview_jinja)."""
    from libs.steamcharts_scraper import SteamchartsData, HourlyBucket
    data = SteamchartsData()
    data.current_online = 112345
    data.peak_24h = 145678
    data.peak_all_time = 624189
    now_ms = int(time.time() * 1000)
    data.raw_7d_points = [
        [int(now_ms - i * 3600 * 1000), 98000 + int((i % 5) * 5000 + (i * 137) % 3000)]
        for i in range(168, 0, -1)
    ]
    return data


# ══════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════

async def main():
    print("=" * 60)
    print("  Standalone Renderer Test - Real Data Preview")
    print("  Output: " + str(_OUT))
    print("=" * 60)

    # ── Step 1: Fetch real data ──
    print("\n" + "-" * 40)
    print("DATA FETCH")
    print("-" * 40)

    real_ss, real_rot, real_pred, real_steam = None, None, None, None

    tasks = [
        fetch_server_status_real(),
        fetch_map_rotation_real(),
        fetch_predator_real(),
        fetch_steamcharts_real(),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    real_ss = results[0] if not isinstance(results[0], Exception) and results[0] else None
    real_rot = results[1] if not isinstance(results[1], Exception) and results[1] else None
    real_pred = results[2] if not isinstance(results[2], Exception) and results[2] else None
    real_steam = results[3] if not isinstance(results[3], Exception) and results[3] else None

    # Log any exceptions
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            print(f"  [x]  Source {i} error: {r}")

    # Apply fallbacks
    ss_data = real_ss if real_ss else (print("\n  [FALLBACK] Server status ->  using mock data") or _make_mock_server_status())
    rot_data = real_rot if real_rot else (print("  [FALLBACK] Map rotation ->  using mock data") or _make_mock_rotation())
    pred_data = real_pred if real_pred else (print("  [FALLBACK] Predator ->  using mock data") or _make_mock_predator())
    steam_data = real_steam if real_steam else (print("  [FALLBACK] Steamcharts ->  using mock data") or _make_mock_steamcharts())

    # ── Step 2: Render HTML ──
    print("\n" + "-" * 40)
    print("RENDER HTML")
    print("-" * 40)

    cards = [
        ("server_status", lambda: render_server_status(ss_data)),
        ("map_rotation", lambda: render_map_rotation(rot_data)),
        ("predator", lambda: render_predator(pred_data)),
        ("steamcharts", lambda: render_steamcharts(steam_data)),
    ]

    html_files = []
    for name, render_fn in cards:
        try:
            html = render_fn()
            path = save_html(html, f"{name}.html")
            html_files.append(path)
        except Exception as e:
            print(f"  [x]  {name} render FAILED: {e}")
            import traceback
            traceback.print_exc()

    # ── Step 3: Screenshot ──
    print("\n" + "-" * 40)
    print("SCREENSHOT (Playwright WebKit)")
    print("-" * 40)

    for html_path in html_files:
        name = html_path.stem
        png_path = _OUT / f"{name}.png"
        try:
            html = html_path.read_text(encoding="utf-8")
            w = 720 if name != "lfg" else 1328
            await screenshot_html(html, png_path, width=w)
            size = png_path.stat().st_size
            print(f"  [+]  {name}.png  ({size / 1024:.0f} KB)")
        except Exception as e:
            print(f"  [x]  {name}.png FAILED: {e}")

    # ── Summary ──
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print(f"  Data sources: server_status={'REAL' if real_ss else 'mock'} | "
          f"map_rotation={'REAL' if real_rot else 'mock'} | "
          f"predator={'REAL' if real_pred else 'mock'} | "
          f"steamcharts={'REAL' if real_steam else 'mock'}")
    print(f"  Output: {_OUT}/")
    html_count = len(list(_OUT.glob("*.html")))
    png_count = len(list(_OUT.glob("*.png")))
    print(f"  Files: {html_count} HTML, {png_count} PNG")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
