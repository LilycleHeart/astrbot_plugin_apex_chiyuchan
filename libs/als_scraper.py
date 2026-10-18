"""ALS 网站徽章抓取器 / 名字搜索 / 服务器状态"""

from __future__ import annotations

import re
import asyncio
from html import unescape
from dataclasses import dataclass, field
from urllib.parse import quote, urljoin

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from .playwright_manager import run_with_page
from .ttl_cache import get as cache_get, set as cache_set


# ══════════════════════════════════════════
#  服务器状态数据类型
# ══════════════════════════════════════════


@dataclass
class AlsServerEntry:
    name: str
    status: str  # UNSTABLE / UP / SLOW
    response_time: str  # "72 ms", "100% up", ""
    flag_class: str = ""  # e.g. "flag-icon-eu", "flag-icon-us"


@dataclass
class AlsServerSection:
    name: str
    status: str  # "Unstable / Slow", "UNSTABLE", "UP"
    entries: list[AlsServerEntry] = field(default_factory=list)


@dataclass
class AlsServerStatus:
    sections: list[AlsServerSection] = field(default_factory=list)
    alert_banner: str = ""  # overall alert text from the banner
    outage_announcement: bool = False


async def scrape_als_server_status() -> AlsServerStatus | None:
    """从 ALS 主页抓取服务器状态"""
    from .ttl_cache import get as cache_get, set as cache_set

    cache_key = "als_server_status"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    result = AlsServerStatus()

    async def _do_scrape(page):
        nonlocal result
        await page.route(
            "**/*",
            lambda route: (
                route.abort()
                if route.request.resource_type
                in ("image", "font", "media", "stylesheet")
                or "analytics" in (route.request.url or "")
                or "googletagmanager" in (route.request.url or "")
                or "cookieconsent" in (route.request.url or "")
                else route.continue_()
            ),
        )
        await page.goto(
            "https://apexlegendsstatus.com/",
            wait_until="domcontentloaded",
            timeout=20000,
        )

        content = await page.content()

        # Parse alert banner
        m = re.search(
            r'<div class="alert alert-danger tmpal"[^>]*>(.*?)</div>',
            content,
            re.DOTALL,
        )
        if m:
            text = re.sub(r"<[^>]+>", "", m.group(1)).strip()
            result.alert_banner = text

        # Parse outage announcement
        if "v2-alert--danger" in content and "Outage in progress" in content:
            result.outage_announcement = True

        # Parse status sections
        # Each section: v2-lb-card v2-status-card v2-status-card--xxx
        sec_pattern = re.compile(
            r'<div class="v2-lb-card v2-status-card[^"]*">(.*?)</div>\s*</div>',
            re.DOTALL,
        )
        for sec_match in sec_pattern.finditer(content):
            sec_html = sec_match.group(1)

            # Section name and pill status
            name_m = re.search(
                r"v2-status-card__name[^>]*>(?:<[^>]*>)*\s*([^<]+)",
                sec_html,
            )
            pill_m = re.search(
                r"v2-status-pill[^>]*>([^<]+)",
                sec_html,
            )
            if not name_m:
                continue

            section = AlsServerSection(
                name=name_m.group(1).strip(),
                status=pill_m.group(1).strip() if pill_m else "",
            )

            # Parse rows
            row_pattern = re.compile(
                r'<div class="v2-status-row">(.*?)</div>',
                re.DOTALL,
            )
            for row_match in row_pattern.finditer(sec_html):
                row_html = row_match.group(1)
                row_name_m = re.search(
                    r"v2-status-row__name[^>]*>([^<]+)",
                    row_html,
                )
                row_status_m = re.search(
                    r"v2-status-row__state[^>]*>([^<]+)",
                    row_html,
                )
                row_rt_m = re.search(
                    r"v2-status-row__rt[^>]*>([^<]+)",
                    row_html,
                )
                if row_name_m:
                    # Extract ALS flag class (e.g. "flag-icon-eu")
                    flag_m = re.search(r"flag-icon-(\w+)", row_html)
                    flag_cls = f"flag-icon-{flag_m.group(1)}" if flag_m else ""
                    section.entries.append(
                        AlsServerEntry(
                            name=row_name_m.group(1).strip(),
                            status=row_status_m.group(1).strip()
                            if row_status_m
                            else "",
                            response_time=row_rt_m.group(1).strip() if row_rt_m else "",
                            flag_class=flag_cls,
                        )
                    )

            result.sections.append(section)

        return result

    try:
        async with run_with_page() as page:
            await _do_scrape(page)
        await cache_set(cache_key, result, 120)
        return result
    except Exception:
        return None


async def _block_noise(page):
    """拦截图片/字体/媒体/统计请求，加速页面加载"""
    await page.route(
        "**/*",
        lambda route: (
            route.abort()
            if route.request.resource_type in ("image", "font", "media", "stylesheet")
            or "analytics" in (route.request.url or "")
            or "googletagmanager" in (route.request.url or "")
            or "cookieconsent" in (route.request.url or "")
            else route.continue_()
        ),
    )


async def _get_profile_soup(name_or_uid: str, platform: str):
    """Fetch the public profile fragment using the site's own bootstrap.

    Args:
        name_or_uid: Player name or numeric UID.
        platform: Apex platform identifier.

    Returns:
        Parsed profile HTML and its base URL, with no browser resources loaded.
    """
    from bs4 import BeautifulSoup
    from .http_client import get_async_client

    profile_path = "profile/uid" if name_or_uid.isdigit() else "profile"
    url = f"https://apexlegendsstatus.com/{profile_path}/{platform}/{quote(name_or_uid, safe='')}"
    client = await get_async_client()
    response = await client.get(url, follow_redirects=True)
    response.raise_for_status()
    document, base_url = response.text, str(response.url)
    if "fetchApiData(" in document:
        token = re.search(
            r"""(?:let|const|var)\s+token\s*=\s*(["'])(.*?)\1""", document
        )
        fragment = re.search(
            r"""fetchApiData\(\s*["'](/core/interface-v2\?token=)["']\s*\+\s*token\s*\+\s*["']([^"']*)["']\s*\)""",
            document,
        )
        if not token or not fragment:
            raise ValueError("Unsupported profile bootstrap")
        fragment_url = urljoin(
            "https://apexlegendsstatus.com/",
            fragment[1] + quote(token[2], safe="") + unescape(fragment[2]),
        )
        response = await client.get(
            fragment_url,
            follow_redirects=True,
            headers={"X-Requested-With": "XMLHttpRequest", "Referer": base_url},
        )
        response.raise_for_status()
        document = response.text
    soup = BeautifulSoup(document, "html.parser")
    if not soup.select_one(".als-v2, .player-name"):
        raise ValueError("Profile fragment contains no player data")
    return soup, base_url


def _parse_profile(soup, base_url: str) -> dict:
    """Extract the same profile fields as the browser parser from real HTML.

    Args:
        soup: Parsed response from the public profile endpoint.
        base_url: Base URL for relative badge and level images.

    Returns:
        Badge media and the live profile counters used by cards and LFG.
    """
    colors = {
        "bronze": "#cd7f32",
        "silver": "#c0c0c0",
        "gold": "#ffd700",
        "platinum": "#4ECDC4",
        "diamond": "#358de6",
        "master": "#9f35e6",
        "predator": "#e31b39",
    }
    seasons, special, seen = [], [], set()
    for img in soup.select("img[src]"):
        src = urljoin(base_url, img["src"])
        match = re.search(r"you_re_tiering_me_apart_(\w+)_rs(\d+)", src)
        if match:
            seasons.append(
                {
                    "season": "S" + match[2],
                    "tier": match[1],
                    "badge_url": src,
                    "color": colors.get(match[1], "#666"),
                }
            )
        if "you_re_tiering_me_apart" in src:
            continue
        match = re.search(r"badges/badges_new/(.+?)\.png", src)
        if match:
            name = re.sub(r"\b\w", lambda m: m[0].upper(), match[1].replace("_", " "))
            name = re.sub(r" Rs\d+", "", name)
            for old, new in [
                (" Iv", " IV"),
                (" Iii", " III"),
                (" Ii", " II"),
                (" Vi", " VI"),
            ]:
                if name.endswith(old):
                    name = name[: -len(old)] + new
            if src not in seen:
                seen.add(src)
                special.append({"name": name, "color": "#b1f4fa", "badge_url": src})
    result = dict(
        seasons=seasons,
        special=special,
        kills=0,
        wins=0,
        level=0,
        prestige=0,
        rankPos=0,
        rankScore=0,
        rankTopPct=0,
        rankPcPos=0,
        level_icon="",
    )
    icon = soup.select_one('.v2-sb-stat--level img, img[alt="level"]')
    if icon and icon.get("src"):
        result["level_icon"] = urljoin(base_url, icon["src"])
    level_card = soup.select_one(".v2-sb-stat--level")
    if level_card:
        value = level_card.select_one(".v2-sb-stat__value")
        match = re.search(r"[\d,]+", value.get_text()) if value else None
        if match:
            result["level"] = int(match[0].replace(",", ""))
        match = re.search(
            r"Prestige\s*(\d+)", level_card.get_text(" ", strip=True), re.I
        )
        if match:
            result["prestige"] = int(match[1])
    # Global counters must stay inside their legend section; otherwise a missing
    # career tracker can accidentally consume the next legend's wins or kills.
    for legend in soup.select(".v2-legend"):
        heading = legend.select_one(".profile-legend__name")
        if not heading or heading.get_text(strip=True) != "Global":
            continue
        for stat in legend.select(".v2-stat"):
            label, amount = (
                stat.select_one(".v2-stat__label"),
                stat.select_one(".amount__total"),
            )
            if not label or not amount:
                continue
            field = {
                "career kills": "kills",
                "career wins": "wins",
                "wins": "wins",
            }.get(label.get_text(strip=True).casefold())
            match = re.search(r"[\d,]+", amount.get_text())
            if field and match:
                result[field] = int(match[0].replace(",", ""))
        break
    rank_card = soup.select_one(".v2-sb-stat--rank")
    if rank_card:
        value = rank_card.select_one(".v2-sb-stat__value")
        match = (
            re.search(r"([\d,]+)\s*RP", value.get_text(" ", strip=True))
            if value
            else None
        )
        if match:
            result["rankScore"] = int(match[1].replace(",", ""))
        pill = rank_card.select_one(".v2-sb-stat__pill--rank")
        if pill:
            span = pill.select_one("span")
            match = re.search(r"[\d.]+", (span or pill).get_text().replace("%", ""))
            if match:
                result["rankTopPct"] = float(match[0])
        top = rank_card.select_one(".v2-sb-stat__pill--top")
        match = re.search(r"#([\d,]+)", top.get_text()) if top else None
        if match:
            result["rankPcPos"] = int(match[1].replace(",", ""))
        # BR positions are supplied in encoded tooltip HTML. Text elsewhere on
        # the page contains unrelated tracker rankings and is not a fallback.
        from bs4 import BeautifulSoup

        for pill in rank_card.select("[title]"):
            tooltip = BeautifulSoup(pill["title"], "html.parser")
            for label in tooltip.select(".ranking-tooltip-subtitle"):
                value = label.find_next_sibling(class_="ranking-tooltip-value")
                match = (
                    re.search(r"#\s*([\d,]+)", value.get_text(" ", strip=True))
                    if value
                    else None
                )
                if not match:
                    continue
                scope = label.get_text(" ", strip=True).casefold()
                if "global" in scope:
                    result["rankPos"] = int(match[1].replace(",", ""))
                elif "only" in scope:
                    result["rankPcPos"] = int(match[1].replace(",", ""))
    return result


async def _load_profile(page, name_or_uid: str, platform: str) -> str:
    """Load the browser fallback when the direct public request is unavailable.

    Args:
        page: Page used for the existing browser flow.
        name_or_uid: Player name or numeric UID.
        platform: Apex platform identifier.

    Returns:
        The resolved profile URL.
    """
    profile_path = "profile/uid" if name_or_uid.isdigit() else "profile"
    url = f"https://apexlegendsstatus.com/{profile_path}/{platform}/{quote(name_or_uid, safe='')}"
    await _block_noise(page)
    await page.goto(url, wait_until="domcontentloaded", timeout=15000)
    await page.wait_for_function(
        """() => {
            const content = document.querySelector('[data-role="profile-content"]');
            if (content) return content.children.length > 0
                && !content.querySelector(':scope > .loading-indicator');
            return !!document.querySelector('.player-name');
        }""",
        timeout=15000,
    )
    return page.url


async def _do_fetch(page, name_or_uid: str, platform: str) -> dict:
    """Use the same extraction rules after the browser loads the profile.

    Args:
        page: Browser fallback page.
        name_or_uid: Player lookup value.
        platform: Apex platform identifier.

    Returns:
        Parsed profile fields from the completed browser DOM.
    """
    from bs4 import BeautifulSoup

    base_url = await _load_profile(page, name_or_uid, platform)
    return _parse_profile(BeautifulSoup(await page.content(), "html.parser"), base_url)


async def fetch_badges(
    name_or_uid: str, platform: str = "PC", force: bool = False
) -> dict:
    """从 ALS 个人页面抓取赛季徽章和特殊徽章（仅网络超时重试，空数据不重试，TTL 缓存1h）
    force=True 时跳过内存缓存，强制重新抓取。"""
    import time
    from astrbot.api import logger

    cache_key = f"badges:{platform}:{name_or_uid}"
    if not force:
        cached = await cache_get(cache_key)
        if cached is not None:
            logger.info(f"[BadgeFetcher] 缓存命中 {cache_key}")
            return cached

    t0 = time.time()

    try:
        soup, base_url = await asyncio.wait_for(
            _get_profile_soup(name_or_uid, platform), timeout=10
        )
        result = _parse_profile(soup, base_url)
        if result.get("seasons") or result.get("special"):
            await cache_set(cache_key, result, 3600)
        logger.info("[BadgeFetcher] HTTP profile %.2fs", time.time() - t0)
        return result
    except Exception as exc:
        logger.debug("[BadgeFetcher] Using browser fallback (%s)", type(exc).__name__)

    for attempt in range(2):
        try:
            async with run_with_page() as page:
                result = await _do_fetch(page, name_or_uid, platform)
                dt = time.time() - t0
                logger.info(
                    f"[BadgeFetcher] 耗时: {dt:.1f}s (attempt={attempt + 1}) rankTopPct={result.get('rankTopPct', 0)} rankPcPos={result.get('rankPcPos', 0)} rankPos={result.get('rankPos', 0)}"
                )
                if result.get("seasons") or result.get("special"):
                    await cache_set(cache_key, result, 3600)
                return result
        except PlaywrightTimeoutError:
            if attempt == 0:
                logger.warning(f"[BadgeFetcher] 网络超时，重试... {name_or_uid}")
                continue
            logger.error(f"[BadgeFetcher] 连续超时，放弃 {name_or_uid}")
        except Exception as e:
            if attempt == 0:
                logger.warning(f"[BadgeFetcher] 失败，重试... {e}")
                continue
            logger.error(f"[BadgeFetcher] Error: {e}")
            break

    return {"seasons": [], "special": []}


async def search_players(name: str, platform: str = "PC") -> list[dict]:
    """访问ALS玩家页面，从DOM提取数据（TTL 缓存5分钟）"""
    import time
    from astrbot.api import logger

    cache_key = f"search:{platform}:{name.lower().strip()}"
    cached = await cache_get(cache_key)
    if cached is not None:
        logger.info(f"[SearchPlayers] 缓存命中 {cache_key}")
        return cached

    t0 = time.time()
    try:
        soup, _ = await asyncio.wait_for(_get_profile_soup(name, platform), timeout=10)
        uid, player_name = soup.select_one("#puid"), soup.select_one("#pname")
        if uid and player_name and uid.get("value") and player_name.get("value"):
            pplat = soup.select_one("#pplat")
            result = [
                {
                    "name": player_name["value"],
                    "uid": uid["value"],
                    "platform": pplat.get("value", platform) if pplat else platform,
                }
            ]
        else:
            result, seen = [], set()
            for link in soup.select('a[href*="profile/uid"]'):
                match = re.search(r"profile/uid/(\w+)/(\d+)", link["href"])
                player_name = link.select_one(".player-name")
                if match and player_name and match[2] not in seen:
                    seen.add(match[2])
                    result.append(
                        {
                            "name": player_name.get_text(strip=True),
                            "uid": match[2],
                            "platform": match[1],
                        }
                    )
            result = result[:10]
        if result:
            await cache_set(cache_key, result, 300)
        logger.info("[SearchPlayers] HTTP profile %.2fs", time.time() - t0)
        return result
    except Exception as exc:
        logger.debug("[SearchPlayers] Using browser fallback (%s)", type(exc).__name__)
    async with run_with_page() as page:
        try:
            url = await _load_profile(page, name, platform)
            logger.info(f"[SearchPlayers] Profile URL: {url}")
            dt = time.time() - t0
            logger.info(f"[SearchPlayers] 页面加载耗时: {dt:.1f}s")
            result = await page.evaluate(
                """(platform) => {
                const uid = document.getElementById('puid')?.value;
                const name = document.getElementById('pname')?.value
                    || document.querySelector('.player-name')?.textContent?.trim();
                if (name && uid) return [{name, uid,
                    platform: document.getElementById('pplat')?.value || platform}];
                const items = [];
                document.querySelectorAll('a[href*="profile/uid"]').forEach(a => {
                    const m = (a.href || '').match(/profile\\/uid\\/(\\w+)\\/(\\d+)/);
                    if (!m) return;
                    const pn = a.querySelector('.player-name');
                    if (!pn) return;
                    const name = pn ? pn.textContent.trim() : a.textContent.trim().split(/Lvl|Prestige|Currently/)[0].trim();
                    const row = a.textContent;
                    const lv = (row.match(/Lvl\\s*(\\d+)/) || [])[1] || '';
                    const pr = (row.match(/Prestige\\s*(\\d+)/) || [])[1] || '';
                    const rp = (row.match(/([\\d,]+)\\s*RP/) || [])[1] || '';
                    const ri = a.querySelector('img[src*="ranks"]');
                    const rank_img = ri ? ri.src : '';
                    items.push({name, uid: m[2], platform: m[1], level: lv, prestige: pr, rp: rp.replace(/,/g,''), rank_img});
                });
                const seen = new Set();
                return items.filter(i => { const k = i.uid; if (seen.has(k)) return false; seen.add(k); return true; }).slice(0, 10);
            }""",
                platform,
            )
            if result:
                await cache_set(cache_key, result, 300)
            return result
        except Exception as e:
            logger.error(f"[SearchPlayers] Error: {e}")
            return []


async def fetch_lfg_stats(name_or_uid: str, platform: str = "PC") -> dict:
    """Read live LFG fields after the complete profile fragment arrives.

    Args:
        name_or_uid: Player name or numeric UID.
        platform: Apex platform identifier.

    Returns:
        LFG counters and ranks, or an empty dict when the source fails.
    """
    cache_key = f"lfg_stats:{platform}:{name_or_uid}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        profile = await fetch_badges(name_or_uid, platform, force=True)
        fields = ("kills", "level", "prestige", "rankPos", "rankTopPct", "rankPcPos")
        result = {key: profile.get(key, 0) for key in fields}
        if any(result.values()):
            await cache_set(cache_key, result, 300)
        return result
    except Exception:
        from astrbot.api import logger

        logger.warning("[LFGFetcher] Failed to load profile", exc_info=True)
        return {}
