"""卡片图片渲染引擎 — 所有 draw_* 函数均通过 Playwright HTML→PNG 渲染"""

from __future__ import annotations

import io
import asyncio
from pathlib import Path
from PIL import Image, ImageSequence

# ══════════════════════════════════════════
#  Playwright 渲染器导入（必须）
# ══════════════════════════════════════════

try:
    from .playwright_renderer import draw_profile_card as _draw_profile_card_pw
    from .playwright_renderer import (
        draw_map_rotation_card as _draw_map_rotation_card_pw,
    )
    from .playwright_renderer import (
        draw_server_status_card as _draw_server_status_card_pw,
    )
    from .playwright_renderer import draw_predator_card as _draw_predator_card_pw
    from .playwright_renderer import draw_lfg_card as _draw_lfg_card_pw
    from .playwright_renderer import draw_lfg_mode_card as _draw_lfg_mode_card_pw
    from .playwright_renderer import draw_steamcharts_card as _draw_steamcharts_card_pw
    from .playwright_renderer import draw_bind_card_pw as _draw_bind_card_pw
    from .playwright_renderer import draw_unbind_card_pw as _draw_unbind_card_pw
    from .playwright_renderer import draw_team_card_pw as _draw_team_card_pw
    from .playwright_renderer import draw_team_list_card_pw as _draw_team_list_card_pw
    from .playwright_renderer import draw_stats_card_pw as _draw_stats_card_pw
    from .playwright_renderer import draw_season_card as _draw_season_card_pw
except Exception as _e:
    from astrbot.api import logger as _lg
    _lg.error(f"[ImageRenderer] Playwright 渲染器导入失败: {type(_e).__name__}: {_e}")
    raise  # Playwright 是必须依赖，导入失败直接崩溃


# ══════════════════════════════════════════
#  公开 draw_* 接口（全部走 Playwright）
#  失败时返回 None，调用方降级为纯文本
# ══════════════════════════════════════════


async def draw_stats_card(stats) -> bytes | None:
    """渲染战绩卡片 (Playwright)。失败返回 None。"""
    from astrbot.api import logger
    try:
        return await _draw_stats_card_pw(stats)
    except Exception as e:
        logger.error(f"[StatsCard] Playwright 渲染失败: {type(e).__name__}: {e}")
        return None


async def draw_profile_card(data: dict) -> bytes | None:
    """渲染玩家详情卡片 (Playwright)。失败返回 None。"""
    from astrbot.api import logger
    try:
        return await _draw_profile_card_pw(data)
    except Exception as e:
        logger.error(f"[ProfileCard] Playwright 渲染失败: {type(e).__name__}: {e}")
        return None


async def draw_map_card(rotation) -> bytes | None:
    """地图轮换 (Playwright)。失败返回 None。"""
    from astrbot.api import logger
    try:
        return await _draw_map_rotation_card_pw(rotation)
    except Exception as e:
        logger.error(f"[MapCard] Playwright 渲染失败: {type(e).__name__}: {e}")
        return None


async def draw_server_status_card(server_status) -> bytes | None:
    """服务器状态 (Playwright)。失败返回 None。"""
    from astrbot.api import logger
    try:
        return await _draw_server_status_card_pw(server_status)
    except Exception as e:
        logger.error(f"[ServerCard] Playwright 渲染失败: {type(e).__name__}: {e}")
        return None


async def draw_master_card(predator) -> bytes | None:
    """大师/猎杀 (Playwright)。失败返回 None。"""
    from astrbot.api import logger
    try:
        return await _draw_predator_card_pw(predator)
    except Exception as e:
        logger.error(f"[MasterCard] Playwright 渲染失败: {type(e).__name__}: {e}")
        return None


async def draw_team_card(team: dict) -> bytes | None:
    """队伍卡片 (Playwright)。失败返回 None。"""
    from astrbot.api import logger
    try:
        return await _draw_team_card_pw(team)
    except Exception as e:
        logger.error(f"[TeamCard] Playwright 渲染失败: {type(e).__name__}: {e}")
        return None


async def draw_team_list_card(teams: list[dict]) -> bytes | None:
    """队伍列表卡片 (Playwright)。失败返回 None。"""
    from astrbot.api import logger
    try:
        return await _draw_team_list_card_pw(teams)
    except Exception as e:
        logger.error(f"[TeamListCard] Playwright 渲染失败: {type(e).__name__}: {e}")
        return None


async def draw_bind_card(uid: str, name: str, platform: str) -> bytes | None:
    """绑定确认卡片 (Playwright)。失败返回 None。"""
    from astrbot.api import logger
    try:
        return await _draw_bind_card_pw(uid, name, platform)
    except Exception as e:
        logger.error(f"[BindCard] Playwright 渲染失败: {type(e).__name__}: {e}")
        return None


async def draw_unbind_card() -> bytes | None:
    """解绑确认卡片 (Playwright)。失败返回 None。"""
    from astrbot.api import logger
    try:
        return await _draw_unbind_card_pw()
    except Exception as e:
        logger.error(f"[UnbindCard] Playwright 渲染失败: {type(e).__name__}: {e}")
        return None


async def draw_player_list_card(
    players: list[dict], hint: str = ""
) -> bytes:
    """玩家列表卡片 (Playwright)"""
    from astrbot.api import logger
    import time
    from .playwright_manager import run_with_page

    plat_icons = {
        "PC": '<i class="fab fa-steam" style="color:#6DA8FF;"></i>',
        "PS4": '<i class="fab fa-playstation" style="color:#64C3D3;"></i>',
        "PS5": '<i class="fab fa-playstation" style="color:#64C3D3;"></i>',
        "X1": '<i class="fab fa-xbox" style="color:#4CE5B1;"></i>',
        "SWITCH": '<i class="fas fa-gamepad" style="color:#FF6B6B;"></i>',
    }
    rank_colors = {
        "Rookie": "#89A0B0", "Bronze": "#CD7F32", "Silver": "#C0C0C0",
        "Gold": "#FFD700", "Platinum": "#4ECDC4", "Diamond": "#74B9FF",
        "Master": "#A855F7", "Predator": "#DA292A",
    }
    from .playwright_renderer import _parse_rank_name, _escape_html

    C_CARD = "#171A22"
    C_CARD2 = "#1D222C"
    C_OUTLINE = "#444C5C"
    C_TEXT = "#DDE4F3"
    C_MUTED = "#BFC7DA"
    C_PRIMARY = "#6DA8FF"

    cards_html = ""
    for i, r in enumerate(players):
        name = _escape_html(r.get("name", "?"))
        uid = _escape_html(r.get("uid", "?"))
        plat = r.get("platform", "PC").upper()
        level = str(r.get("level", ""))
        prestige = str(r.get("prestige", "0"))
        rp_val = str(r.get("rp", ""))
        rank_img = r.get("rank_img", "")
        rank_name = _parse_rank_name(rank_img)
        plat_icon = plat_icons.get(plat, plat_icons["PC"])

        lvl_str = f"{level}" if level else "?"
        if prestige and prestige != "0":
            lvl_str += f" (P{prestige})"

        rank_img_html = f'<img src="{rank_img}" style="width:28px;height:28px;vertical-align:middle;">' if rank_img else ""
        rp_html = ""
        if rp_val and rp_val.isdigit():
            rp_html = f'<span class="rp-val">{int(rp_val):,} RP</span>'
        elif rp_val:
            rp_html = f'<span class="rp-val">{rp_val}</span>'

        rank_name_html = ""
        if rank_name:
            rc = rank_colors.get(rank_name.split()[0] if rank_name else "", C_MUTED)
            rank_name_html = f'<div class="rank-name" style="color:{rc};">{rank_name}</div>'

        cards_html += f"""<div class="player-card">
            <div class="num">{i+1}</div>
            <div class="name-row">
                <span class="name">{name}</span>
                <span class="plat">{plat_icon}</span>
            </div>
            <div class="divider"></div>
            <div class="lvl">Lv. <b>{lvl_str}</b></div>
            {rank_name_html}
            <div class="rp-row">{rank_img_html} {rp_html}</div>
            <div class="uid">{uid}</div>
        </div>"""

    n = len(players)
    title = f"找到 {n} 个玩家"
    hint_html = f'<div class="hint">{_escape_html(hint)}</div>' if hint else ""

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
    background: transparent; font-family: "Segoe UI", "Noto Sans SC", "Microsoft YaHei", sans-serif;
    display: flex; justify-content: center; padding: 16px; -webkit-font-smoothing: antialiased;
}}
.card-container {{
    width: 720px; background: {C_CARD}; border-radius: 24px;
    padding: 24px; box-shadow: 0 10px 20px rgba(0,0,0,0.4);
    border: 1px solid {C_OUTLINE};
}}
.title {{
    text-align: center; font-size: 20px; font-weight: 700;
    color: {C_PRIMARY}; margin-bottom: 20px; letter-spacing: 0.5px;
}}
.grid {{
    display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;
}}
.player-card {{
    position: relative; text-align: center; background: {C_CARD2}; border-radius: 16px;
    padding: 16px 12px; display: flex; flex-direction: column; align-items: center; gap: 4px;
    border: 1px solid {C_OUTLINE};
}}
.num {{
    position: absolute; top: 8px; left: 12px;
    font-size: 11px; font-weight: 700; color: {C_PRIMARY}; opacity: 0.7;
}}
.name-row {{
    display: flex; align-items: center; gap: 6px; justify-content: center;
}}
.name {{
    font-size: 14px; font-weight: 600; color: {C_TEXT};
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 160px;
}}
.plat {{ font-size: 13px; }}
.divider {{
    width: 80%; border-top: 1px solid {C_OUTLINE}; margin: 6px 0 4px;
}}
.lvl {{ font-size: 12px; color: {C_MUTED}; }}
.lvl b {{ color: {C_TEXT}; font-weight: 600; }}
.rank-name {{ font-size: 11px; font-weight: 600; }}
.rp-row {{
    display: flex; align-items: center; gap: 6px; justify-content: center;
    font-size: 13px; margin-top: 2px;
}}
.rp-val {{ color: {C_TEXT}; font-weight: 700; }}
.uid {{ font-size: 10px; color: {C_MUTED}; opacity: 0.6; margin-top: 2px; }}
.hint {{
    text-align: center; font-size: 12px; color: {C_MUTED};
    margin-top: 18px; padding-top: 14px; border-top: 1px solid {C_OUTLINE};
}}
.watermark {{ text-align: center; font-size: 11px; color: {C_MUTED}; opacity: 0.5; margin-top: 12px; }}
</style>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
</head><body><div class="card-container">
    <div class="title">{title}</div>
    <div class="grid">{cards_html}</div>
    {hint_html}
    <div class="watermark">auth.赤羽真白 · Apex Chiyuchan</div>
</div></body></html>"""

    t0 = time.time()
    try:
        async with run_with_page(viewport={"width": 780, "height": 800}, device_scale_factor=3) as page:
            await page.set_content(html, wait_until="domcontentloaded")
            card = await page.query_selector(".card-container")
            if card:
                png = await card.screenshot(type="png", omit_background=True)
            else:
                png = await page.screenshot(type="png", full_page=True, omit_background=True)
            dt = time.time() - t0
            logger.info(f"[PW卡片] 渲染耗时: {dt:.1f}s ({n}个玩家)")
            return png
    except Exception as e:
        logger.error(f"[PlayerListCard] Playwright 渲染失败: {type(e).__name__}: {e}")
        return await _draw_text_card_pw("渲染错误", f"player_list 渲染失败: {e}", is_error=True)


async def draw_lfg_mode_card() -> bytes:
    """LFG 模式选择卡片 (Playwright)"""
    from astrbot.api import logger
    try:
        return await _draw_lfg_mode_card_pw()
    except Exception as e:
        logger.error(f"[LfgModeCard] Playwright 渲染失败: {type(e).__name__}: {e}")
        return await _draw_text_card_pw("渲染错误", f"lfg_mode_card 渲染失败: {e}", is_error=True)


async def draw_lfg_card(entries: list[dict]) -> bytes:
    """LFG 找队友卡片 (Playwright)"""
    from astrbot.api import logger
    try:
        return await _draw_lfg_card_pw(entries)
    except Exception as e:
        logger.error(f"[LfgCard] Playwright 渲染失败: {type(e).__name__}: {e}")
        return await _draw_text_card_pw("渲染错误", f"lfg_card 渲染失败: {e}", is_error=True)


async def draw_steamcharts_card(data) -> bytes:
    """渲染 Steamcharts 日活卡片 PNG (Playwright)"""
    if _draw_steamcharts_card_pw is None:
        raise RuntimeError("Playwright 渲染器未导入，无法渲染 Steamcharts 卡片")
    return await _draw_steamcharts_card_pw(data)


async def draw_season_card(season_info, meta_top5: list) -> bytes | None:
    """赛季信息卡片 (Playwright)。失败返回 None。"""
    from astrbot.api import logger
    try:
        return await _draw_season_card_pw(season_info, meta_top5)
    except Exception as e:
        logger.error(f"[SeasonCard] Playwright 渲染失败: {type(e).__name__}: {e}")
        return None


# ══════════════════════════════════════════
#  Moe Counter 数字图片缓存（PIL 仅用于 GIF 帧处理）
# ══════════════════════════════════════════

_MOE_DIGIT_BASE = "https://raw.githubusercontent.com/journey-ad/Moe-Counter/master/assets/theme/moebooru"
_moe_digit_frames: dict[str, list[Image.Image]] = {}
_moe_cache_dir: Path | None = None
_moe_loaded = False


def _get_moe_cache_dir() -> Path:
    global _moe_cache_dir
    if _moe_cache_dir is None:
        _moe_cache_dir = Path(__file__).parent.parent / "assets" / "moe_digits"
        _moe_cache_dir.mkdir(parents=True, exist_ok=True)
    return _moe_cache_dir


def _load_moe_digits_from_disk() -> bool:
    """从本地磁盘加载缓存的 GIF 帧"""
    global _moe_digit_frames, _moe_loaded
    if _moe_loaded:
        return bool(_moe_digit_frames)

    cache_dir = _get_moe_cache_dir()
    _moe_digit_frames.clear()

    for d in "0123456789":
        cache_file = cache_dir / f"{d}.png"
        if not cache_file.exists():
            return False
        try:
            frames = []
            img = Image.open(cache_file)
            for frame in ImageSequence.Iterator(img):
                f = frame.copy()
                if f.mode != "RGBA":
                    f = f.convert("RGBA")
                frames.append(f)
            _moe_digit_frames[d] = frames
        except Exception:
            return False

    _moe_loaded = True
    _normalize_moe_frames()
    return True


def _normalize_moe_frames():
    if not _moe_digit_frames:
        return
    max_frames = max(len(v) for v in _moe_digit_frames.values())
    for d, frames in _moe_digit_frames.items():
        while len(frames) < max_frames:
            frames.append(frames[-1])


async def _download_moe_digits_async():
    """异步从 GitHub 下载并缓存 Moe 数字 GIF"""
    global _moe_digit_frames, _moe_loaded
    from .http_client import get_async_client

    client = await get_async_client()
    cache_dir = _get_moe_cache_dir()

    async def fetch_one(d: str):
        try:
            r = await client.get(f"{_MOE_DIGIT_BASE}/{d}.gif")
            r.raise_for_status()
            data = r.content
            cache_file = cache_dir / f"{d}.png"
            cache_file.write_bytes(data)
            img = Image.open(io.BytesIO(data))
            frames = []
            for frame in ImageSequence.Iterator(img):
                f = frame.copy()
                if f.mode != "RGBA":
                    f = f.convert("RGBA")
                frames.append(f)
            return d, frames
        except Exception as e:
            logger = None
            try:
                from astrbot.api import logger as _log
                logger = _log
            except Exception:
                pass
            if logger:
                logger.warning(f"[image_renderer] Failed to load Moe digit {d}.gif: {e}")
            return d, []

    results = await asyncio.gather(
        *[fetch_one(d) for d in "0123456789"], return_exceptions=True
    )
    for result in results:
        if isinstance(result, Exception):
            continue
        d, frames = result
        if frames:
            _moe_digit_frames[d] = frames

    if _moe_digit_frames:
        _normalize_moe_frames()
    _moe_loaded = True


def _load_moe_digits():
    """优先磁盘缓存，无缓存直接跳过（不阻塞下载）"""
    global _moe_loaded
    if _moe_loaded:
        return
    if not _load_moe_digits_from_disk():
        _moe_loaded = True  # 标记已尝试，不重复检查磁盘
