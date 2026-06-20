"""ALS 网站徽章抓取器 / 名字搜索 / 服务器状态"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import quote

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
            lambda route: route.abort()
            if route.request.resource_type in ("image", "font", "media", "stylesheet")
            or "analytics" in (route.request.url or "")
            or "googletagmanager" in (route.request.url or "")
            or "cookieconsent" in (route.request.url or "")
            else route.continue_(),
        )
        await page.goto("https://apexlegendsstatus.com/", wait_until="domcontentloaded", timeout=20000)

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
        if 'v2-alert--danger' in content and 'Outage in progress' in content:
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
                r'v2-status-card__name[^>]*>(?:<[^>]*>)*\s*([^<]+)',
                sec_html,
            )
            pill_m = re.search(
                r'v2-status-pill[^>]*>([^<]+)',
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
                    r'v2-status-row__name[^>]*>([^<]+)',
                    row_html,
                )
                row_status_m = re.search(
                    r'v2-status-row__state[^>]*>([^<]+)',
                    row_html,
                )
                row_rt_m = re.search(
                    r'v2-status-row__rt[^>]*>([^<]+)',
                    row_html,
                )
                if row_name_m:
                    section.entries.append(AlsServerEntry(
                        name=row_name_m.group(1).strip(),
                        status=row_status_m.group(1).strip() if row_status_m else "",
                        response_time=row_rt_m.group(1).strip() if row_rt_m else "",
                    ))

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
        lambda route: route.abort()
        if route.request.resource_type in ("image", "font", "media", "stylesheet")
        or "analytics" in (route.request.url or "")
        or "googletagmanager" in (route.request.url or "")
        or "cookieconsent" in (route.request.url or "")
        else route.continue_(),
    )


async def _do_fetch(page, name_or_uid: str, platform: str) -> dict:
    url = f"https://apexlegendsstatus.com/profile/{platform}/{name_or_uid}"
    await _block_noise(page)
    await page.goto(url, wait_until="domcontentloaded", timeout=15000)
    try:
        await page.wait_for_selector(".player-name", timeout=5000)
    except Exception:
        pass
    # 段位 pill 是 fetchApiData 异步加载后才插入 DOM 的，必须等它出现
    try:
        await page.wait_for_selector(".v2-sb-stat__pill--rank", timeout=8000)
    except Exception:
        pass
    return await page.evaluate("""() => {
        const colors = {
            bronze:'#cd7f32',silver:'#c0c0c0',gold:'#ffd700',
            platinum:'#4ECDC4',diamond:'#358de6',
            master:'#9f35e6',predator:'#e31b39'
        };
        const seasons = [];
        document.querySelectorAll('img[src*="you_re_tiering_me_apart"]').forEach(img => {
            const m = img.src.match(/you_re_tiering_me_apart_(\\w+)_rs(\\d+)/);
            if (m) seasons.push({
                season: 'S' + m[2],
                tier: m[1],
                badge_url: img.src,
                color: colors[m[1]] || '#666'
            });
        });
        const special = [];
        const seen = new Set();
        document.querySelectorAll('img[src*="badges"]').forEach(img => {
            const src = img.src;
            if (src.includes('you_re_tiering_me_apart')) return;
            const m = src.match(/badges\\/badges_new\\/(.+?)\\.png/);
            if (m) {
                let nm = m[1].replace(/_/g,' ').replace(/\\b\\w/g,c=>c.toUpperCase());
                nm = nm.replace(/ Rs\\d+/,'')
                       .replace(/ Iv$/,' IV').replace(/ Iii$/,' III')
                       .replace(/ Ii$/,' II').replace(/ Vi$/,' VI');
                if (!seen.has(nm) && nm.length < 40) {
                    seen.add(nm);
                    special.push({name:nm, color:'#b1f4fa'});
                }
            }
        });
        const text = document.body.innerText;
        const gIdx = text.indexOf('\\nGlobal\\n');
        let kills = 0, wins = 0, rankScore = 0;
        if (gIdx >= 0) {
            const gSection = text.substring(gIdx, gIdx + 500);
            const ck = gSection.match(/Career Kills\\s*\\n([\\d,]+)\\n/);
            if (ck) kills = parseInt(ck[1].replace(/,/g,''));
            const cw = gSection.match(/Wins\\s*\\n([\\d,]+)\\n/);
            if (cw) wins = parseInt(cw[1].replace(/,/g,''));
        }
        let level = 0, prestige = 0;
        const lv = text.match(/LEVEL\\s*\\n(\\d+)\\s*\\nPRESTIGE\\s*(\\d+)/);
        if (lv) { level = parseInt(lv[1]); prestige = parseInt(lv[2]); }
        let rankPos = 0;
        const brRank = text.match(/BR Rank[\\s\\S]*?#([\\d,]{1,12})\\b/);
        if (brRank) rankPos = parseInt(brRank[1].replace(/,/g,''));
        const brScore = text.match(/BR Rank[\\s\\S]*?([\\d,]+)\\s*RP/);
        if (brScore) rankScore = parseInt(brScore[1].replace(/,/g,''));
        let rankTopPct = 0, rankPcPos = 0;
        const rp = document.querySelector('.v2-sb-stat__pill--rank');
        if (rp) {
            const sp = rp.querySelector('span');
            const raw = sp ? sp.textContent.trim() : rp.textContent.trim();
            const m = raw.replace('%','').match(/[\d.]+/);
            if (m) rankTopPct = parseFloat(m[0]);
        }
        const tp = document.querySelector('.v2-sb-stat__pill--top');
        if (tp) {
            const m2 = tp.textContent.trim().match(/#([\\d,]+)/);
            if (m2) rankPcPos = parseInt(m2[1].replace(/,/g,''));
        }
        return {seasons, special: special.slice(0, 5), kills, wins, level, prestige, rankPos, rankScore, rankTopPct, rankPcPos};
    }""")


async def fetch_badges(name_or_uid: str, platform: str = "PC", force: bool = False) -> dict:
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

    for attempt in range(2):
        try:
            async with run_with_page() as page:
                result = await _do_fetch(page, name_or_uid, platform)
                dt = time.time() - t0
                logger.info(f"[BadgeFetcher] 耗时: {dt:.1f}s (attempt={attempt+1}) rankTopPct={result.get('rankTopPct',0)} rankPcPos={result.get('rankPcPos',0)} rankPos={result.get('rankPos',0)}")
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
    encoded = quote(name, safe="")
    url = f"https://apexlegendsstatus.com/profile/{platform}/{encoded}"
    async with run_with_page() as page:
        try:
            await _block_noise(page)
            await page.goto(url, wait_until="commit", timeout=10000)
            logger.info(f"[SearchPlayers] 实际URL: {page.url} (请求: {url})")
            dt = time.time() - t0
            logger.info(f"[SearchPlayers] 页面加载耗时: {dt:.1f}s")
            try:
                await page.wait_for_selector(".player-name", timeout=5000)
            except Exception:
                pass
            result = await page.evaluate("""() => {
                const items = [];
                document.querySelectorAll('a[href*="profile/uid"]').forEach(a => {
                    const m = (a.href || '').match(/profile\\/uid\\/(\\w+)\\/(\\d+)/);
                    if (!m) return;
                    const pn = a.querySelector('.player-name');
                    const name = pn ? pn.textContent.trim() : a.textContent.trim().split(/Lvl|Prestige|Currently/)[0].trim();
                    const row = a.textContent;
                    const lv = (row.match(/Lvl\\s*(\\d+)/) || [])[1] || '';
                    const pr = (row.match(/Prestige\\s*(\\d+)/) || [])[1] || '';
                    const rp = (row.match(/([\\d,]+)\\s*RP/) || [])[1] || '';
                    const ri = a.querySelector('img[src*="ranks"]');
                    const rank_img = ri ? ri.src : '';
                    items.push({name, uid: m[2], platform: m[1], level: lv, prestige: pr, rp: rp.replace(/,/g,''), rank_img});
                });
                if (!items.length) {
                    const name = (document.querySelector('.player-name') || {}).textContent?.trim();
                    const uid = (document.getElementById('puid') || {}).value;
                    if (name && uid) items.push({name, uid, platform: '""" + platform + """'});
                }
                const seen = new Set();
                return items.filter(i => { const k = i.uid; if (seen.has(k)) return false; seen.add(k); return true; }).slice(0, 10);
            }""")
            if result:
                await cache_set(cache_key, result, 300)
            return result
        except Exception as e:
            logger.error(f"[SearchPlayers] Error: {e}")
            return []


async def fetch_lfg_stats(name_or_uid: str, platform: str = "PC") -> dict:
    """轻量版 Playwright 爬虫，只取 LFG 所需数据 (kills/level/prestige/rankPos)，跳过徽章

    先试 `/profile/{platform}/{name_or_uid}`；如果找不到 `.player-name`（如消歧页面），
    再试 `/profile/uid/{platform}/{name_or_uid}`（ALS 数字 UID 路径）。TTL 缓存 5 分钟。
    """
    from .playwright_manager import run_with_page
    from .ttl_cache import get as cache_get, set as cache_set

    cache_key = f"lfg_stats:{platform}:{name_or_uid}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    async def _scrape(page):
        try:
            await page.wait_for_selector(".player-name", timeout=5000)
        except Exception:
            pass
        if not await page.query_selector(".player-name"):
            return {}
        # 段位 pill 异步加载，等它出现
        try:
            await page.wait_for_selector(".v2-sb-stat__pill--rank", timeout=8000)
        except Exception:
            pass
        text = await page.evaluate("document.body.innerText")
        kills = 0; level = 0; prestige = 0; rankPos = 0; rankTopPct = 0; rankPcPos = 0
        gIdx = text.find("\nGlobal\n")
        if gIdx >= 0:
            sec = text[gIdx:gIdx + 500]
            import re
            ck = re.search(r"Career Kills\s*\n([\d,]+)\n", sec)
            if ck: kills = int(ck.group(1).replace(",", ""))
        lv = __import__("re").search(r"LEVEL\s*\n(\d+)\s*\nPRESTIGE\s*(\d+)", text)
        if lv: level = int(lv.group(1)); prestige = int(lv.group(2))
        br = __import__("re").search(r"BR Rank[\s\S]*?#([\d,]{1,12})\b", text)
        if br: rankPos = int(br.group(1).replace(",", ""))
        # DOM 方式提取排名百分比和位置
        rp_el = await page.query_selector('.v2-sb-stat__pill--rank span')
        if rp_el:
            try: rankTopPct = float((await rp_el.text_content()).strip().replace('%',''))
            except: pass
        tp_el = await page.query_selector('.v2-sb-stat__pill--top')
        if tp_el:
            import re
            m = re.search(r'#([\d,]+)', await tp_el.text_content())
            if m: rankPcPos = int(m.group(1).replace(',',''))
        return {"kills": kills, "level": level, "prestige": prestige, "rankPos": rankPos, "rankTopPct": rankTopPct, "rankPcPos": rankPcPos}

    async with run_with_page() as page:
        await _block_noise(page)
        is_uid = name_or_uid.isdigit()
        urls = [
            f"https://apexlegendsstatus.com/profile/uid/{platform}/{name_or_uid}" if is_uid
            else f"https://apexlegendsstatus.com/profile/{platform}/{name_or_uid}",
        ]
        # name 时再备一个 uid 路径
        if not is_uid:
            urls.append(f"https://apexlegendsstatus.com/profile/uid/{platform}/{name_or_uid}")
        result = {"kills": 0, "level": 0, "prestige": 0, "rankPos": 0}
        for url in urls:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            except Exception:
                continue
            r = await _scrape(page)
            if r and (r.get("kills") or r.get("level") or r.get("rankPos")):
                result = r
                break

        if result.get("kills") or result.get("level") or result.get("prestige"):
            await cache_set(cache_key, result, 300)
        return result
