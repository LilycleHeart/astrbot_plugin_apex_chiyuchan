"""Material Design 卡片图片渲染引擎 — 5 种卡片类型"""

from __future__ import annotations

import io
import asyncio
import httpx
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw, ImageFont, ImageSequence

from .config import (
    SURFACE,
    CARD,
    PRIMARY,
    ON_SURFACE,
    MUTED,
    DIVIDER,
    ACCENT_GREEN,
    ACCENT_BLUE,
    SHADOW,
    PADDING,
    RADIUS,
    CARD_GAP,
    STATS_CARD_W,
    STATS_CARD_H,
    MAP_CARD_W,
    MAP_CARD_H,
    MASTER_CARD_W,
    MASTER_CARD_H,
    TEAM_CARD_W,
    TEAM_CARD_H,
    BIND_CARD_W,
    BIND_CARD_H,
    PROFILE_CARD_W,
    PROFILE_CARD_H,
    PLATFORM_COLORS,
    load_font,
    get_rank_color,
    FONT_SIZES,
)

_executor = ThreadPoolExecutor(max_workers=2)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def _draw_surface(draw: ImageDraw.Draw, w: int, h: int):
    draw.rectangle([0, 0, w, h], fill=SURFACE)


def _draw_shadow(draw: ImageDraw.Draw, x: int, y: int, w: int, h: int):
    draw.rounded_rectangle(
        [x + 3, y + 5, x + w + 3, y + h + 5], radius=RADIUS, fill=SHADOW
    )


def _draw_card_bg(draw: ImageDraw.Draw, x: int, y: int, w: int, h: int):
    draw.rounded_rectangle([x, y, x + w, y + h], radius=RADIUS, fill=CARD)


def _text_bbox(
    draw: ImageDraw.Draw, text: str, font: ImageFont.FreeTypeFont
) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _truncate_text(
    draw: ImageDraw.Draw, text: str, font: ImageFont.FreeTypeFont, max_w: int
) -> str:
    if not text:
        return text
    tw, _ = _text_bbox(draw, text, font)
    if tw <= max_w:
        return text
    for i in range(len(text) - 1, 0, -1):
        trial = text[:i] + "\u2026"
        tw2, _ = _text_bbox(draw, trial, font)
        if tw2 <= max_w:
            return trial
    return "\u2026"


def _parse_rank_name(rank_img: str) -> str:
    """从段位图URL提取段位名，如 diamond4 → Diamond 4"""
    import re
    m = re.search(r"ranks/(\w+?)(\d+)\.png", rank_img)
    if not m:
        return ""
    tier = m.group(1).capitalize()
    div = m.group(2)
    rank_zh = {
        "Rookie": "Rookie", "Bronze": "Bronze", "Silver": "Silver",
        "Gold": "Gold", "Platinum": "Platinum", "Diamond": "Diamond",
        "Master": "Master", "Predator": "Predator",
    }
    tier = rank_zh.get(tier, tier)
    return f"{tier} {div}"


def _draw_centered_text(
    draw: ImageDraw.Draw,
    text: str,
    x: int,
    y: int,
    w: int,
    font: ImageFont.FreeTypeFont,
    fill: str = ON_SURFACE,
):
    tw, _ = _text_bbox(draw, text, font)
    draw.text((x + (w - tw) // 2, y), text, font=font, fill=fill)


def _draw_section_header(
    draw: ImageDraw.Draw,
    x: int,
    y: int,
    icon: str,
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: str = ON_SURFACE,
):
    full = f"{icon}  {text}" if icon else text
    draw.text((x, y), full, font=font, fill=fill)
    tw, th = _text_bbox(draw, full, font)
    return y + th + 12


def _draw_metric_bubble(
    draw: ImageDraw.Draw,
    x: int,
    y: int,
    w: int,
    h: int,
    label: str,
    value: str,
    value_color: str = ON_SURFACE,
):
    font_metric = load_font(FONT_SIZES["metric"], bold=True)
    font_label = load_font(FONT_SIZES["metric_label"])

    lw, lh = _text_bbox(draw, label, font_label)
    vw, vh = _text_bbox(draw, value, font_metric)

    label_x = x + (w - lw) // 2
    value_x = x + (w - vw) // 2
    label_y = y + (h - lh - vh - 6) // 2
    value_y = label_y + lh + 6

    draw.text((label_x, label_y), label, font=font_label, fill=MUTED)
    draw.text((value_x, value_y), value, font=font_metric, fill=value_color)


async def _fetch_image(url: str, size: tuple[int, int]) -> Image.Image | None:
    if not url:
        return None
    try:
        from .http_client import get_async_client

        client = await get_async_client()
        resp = await client.get(url)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content))
        img = img.resize(size, Image.LANCZOS)
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        return img
    except Exception:
        return None


def _draw_round_avatar(img: Image.Image, size: int) -> Image.Image:
    img = img.resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.ellipse((0, 0, size, size), fill=255)
    output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    output.paste(img, (0, 0), mask)
    return output


FONT_TITLE = load_font(FONT_SIZES["title"], bold=True)
FONT_SUBTITLE = load_font(FONT_SIZES["subtitle"], bold=True)
FONT_BODY = load_font(FONT_SIZES["body"])
FONT_CAPTION = load_font(FONT_SIZES["caption"])
FONT_SMALL = load_font(FONT_SIZES["small"])


# ── Moe Counter 数字图片缓存 ──
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
                logger.warning(
                    f"[image_renderer] Failed to load Moe digit {d}.gif: {e}"
                )
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


def _paste_moe_number_frame(
    draw: ImageDraw.Draw, number: int, x: int, y: int, max_height: int, frame_idx: int
) -> int:
    """将数字用萌娘图片第 frame_idx 帧贴到卡片上，返回占用总宽度"""
    if not _moe_digit_frames:
        _load_moe_digits()

    digits = str(number)
    scale = max_height / 100.0
    dw = int(45 * scale)
    total_w = 0

    for ch in digits:
        frames = _moe_digit_frames.get(ch, [])
        if not frames:
            continue
        f = frames[frame_idx % len(frames)]
        resized = f.resize((dw, max_height), Image.LANCZOS)
        draw._image.paste(resized, (x + total_w, y), resized)
        total_w += dw

    return total_w


def _get_digit_width(number: int, max_height: int) -> int:
    """计算数字渲染总宽度（不实际绘制）"""
    digits = str(number)
    scale = max_height / 100.0
    dw = int(45 * scale)
    return dw * len(digits)


# ══════════════════════════════════════════
#  1. 战绩卡片 draw_stats_card
# ══════════════════════════════════════════


async def draw_stats_card(stats) -> bytes:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _draw_stats_sync, stats)


def _draw_stats_sync(stats) -> bytes:
    w, h = STATS_CARD_W, STATS_CARD_H
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    _draw_surface(draw, w, h)

    card_x, card_y = PADDING, PADDING
    card_w = w - PADDING * 2
    card_h = h - PADDING * 2

    _draw_shadow(draw, card_x, card_y, card_w, card_h)
    _draw_card_bg(draw, card_x, card_y, card_w, card_h)

    cx = card_x + PADDING
    cy = card_y + PADDING
    cw = card_w - PADDING * 2

    # 头像 + 名字行
    avatar = None
    if stats.avatar:
        try:
            avatar = _fetch_avatar_sync(stats.avatar, 52)
        except Exception:
            pass

    if avatar:
        img.paste(avatar, (cx, cy), avatar)
        name_x = cx + 64
    else:
        name_x = cx

    draw.text((name_x, cy), stats.name or "Unknown", font=FONT_TITLE, fill=ON_SURFACE)

    status_color = ACCENT_GREEN if stats.state == "online" else MUTED
    status_text = "在线" if stats.state == "online" else "离线"
    status_str = f"Lv.{stats.level}  {stats.to_next_level_pct}%"
    tw, _ = _text_bbox(draw, status_str, FONT_CAPTION)
    draw.text(
        (name_x, cy + FONT_SIZES["title"] + 2),
        status_str,
        font=FONT_CAPTION,
        fill=MUTED,
    )

    dot_x = name_x + tw + 8
    dot_y = cy + FONT_SIZES["title"] + 6
    draw.ellipse([dot_x, dot_y, dot_x + 8, dot_y + 8], fill=status_color)
    draw.text(
        (dot_x + 12, cy + FONT_SIZES["title"] + 2),
        status_text,
        font=FONT_CAPTION,
        fill=status_color,
    )

    cy += FONT_SIZES["title"] + FONT_SIZES["caption"] + PADDING

    # 段位行
    rank_color = get_rank_color(stats.rank_name)
    rank_bar_x = cx - 4
    rank_bar_y = cy - 2
    rank_bar_h = 64
    draw.rectangle(
        [rank_bar_x, rank_bar_y, rank_bar_x + 4, rank_bar_y + rank_bar_h],
        fill=rank_color,
    )

    rank_name_full = stats.rank_name
    draw.text((cx + 14, cy), rank_name_full, font=FONT_SUBTITLE, fill=rank_color)
    draw.text(
        (cx + 14, cy + FONT_SIZES["subtitle"] + 4),
        f"RP {stats.rank_score:,}",
        font=FONT_BODY,
        fill=ON_SURFACE,
    )

    top_pct_str = f"全服 Top {stats.rank_top_pct}%"
    draw.text(
        (cx + 14, cy + FONT_SIZES["subtitle"] + FONT_SIZES["body"] + 6),
        top_pct_str,
        font=FONT_CAPTION,
        fill=MUTED,
    )

    cy += rank_bar_h + 8

    # 分隔线
    line_y = cy
    draw.line(
        [(cx, line_y), (cx + cw, line_y)],
        fill=_hex_to_rgb(DIVIDER.replace("rgba(", "").replace(")", ""))[:3],
    )

    cy = line_y + CARD_GAP

    # 生涯数据三列
    section_y = _draw_section_header(draw, cx, cy, "", "生涯数据总览", FONT_SUBTITLE)
    cy = section_y

    bubble_w = cw // 3
    bubble_h = 60

    _draw_metric_bubble(draw, cx, cy, bubble_w, bubble_h, "击杀", f"{stats.kills:,}")
    _draw_metric_bubble(
        draw, cx + bubble_w, cy, bubble_w, bubble_h, "伤害", f"{stats.damage:,}"
    )
    kd_str = f"{stats.kd:.2f}" if stats.kd is not None else "--"
    _draw_metric_bubble(draw, cx + bubble_w * 2, cy, bubble_w, bubble_h, "K/D", kd_str)

    cy += bubble_h + CARD_GAP

    # 常用英雄 TOP3
    if stats.top_legends:
        section_y = _draw_section_header(
            draw, cx, cy, "", "常用英雄 TOP3", FONT_SUBTITLE
        )
        cy = section_y

        legend_w = cw // 3
        legend_h = 56

        for i, legend in enumerate(stats.top_legends):
            lx = cx + i * legend_w
            _draw_legend_box(
                draw, lx, cy, legend_w, legend_h, legend["name"], legend["kills"]
            )

        cy += legend_h + CARD_GAP

    # 当前使用
    if stats.selected_legend:
        footer = f"当前选用: {stats.selected_legend}"
        draw.text((cx, cy), footer, font=FONT_CAPTION, fill=MUTED)

    # 数据来源 + 署名
    cy = card_y + card_h - PADDING - FONT_SIZES["small"]
    draw.text((card_x + PADDING, cy), "Data: apexlegendsstatus.com", font=FONT_SMALL, fill=MUTED)
    _draw_centered_text(draw, "auth.赤羽真白 · Apex Chiyuchan", card_x, cy, card_w, FONT_SMALL, fill=MUTED)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _fetch_avatar_sync(url: str, size: int) -> Image.Image | None:
    try:
        from .http_client import get_sync_client

        client = get_sync_client()
        resp = client.get(url)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content))
        return _draw_round_avatar(img, size)
    except Exception:
        return None


def _draw_legend_box(
    draw: ImageDraw.Draw, x: int, y: int, w: int, h: int, name: str, kills: int
):
    nw, _ = _text_bbox(draw, name, FONT_CAPTION)
    kw, kh = _text_bbox(draw, f"{kills:,}", FONT_BODY)

    name_x = x + (w - nw) // 2
    kills_x = x + (w - kw) // 2

    draw.text((name_x, y), name, font=FONT_CAPTION, fill=MUTED)
    draw.text(
        (kills_x, y + FONT_SIZES["caption"] + 4),
        f"{kills:,}",
        font=FONT_BODY,
        fill=ON_SURFACE,
    )


# ══════════════════════════════════════════
#  2. 地图轮换卡片 draw_map_card — 纯 Playwright 渲染
# ══════════════════════════════════════════


# ══════════════════════════════════════════
#  3. 大师数据卡片 draw_master_card — 纯 Playwright
# ══════════════════════════════════════════


# ══════════════════════════════════════════
#  4. 队伍卡片 draw_team_card
# ══════════════════════════════════════════


async def draw_team_card(team: dict) -> bytes:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _draw_team_sync, team)


def _draw_team_sync(team: dict) -> bytes:
    w, h = TEAM_CARD_W, TEAM_CARD_H
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    _draw_surface(draw, w, h)

    card_x, card_y = PADDING, PADDING
    card_w = w - PADDING * 2
    card_h = h - PADDING * 2

    _draw_shadow(draw, card_x, card_y, card_w, card_h)
    _draw_card_bg(draw, card_x, card_y, card_w, card_h)

    cx = card_x + PADDING
    cy = card_y + PADDING
    card_w - PADDING * 2

    draw.text((cx, cy), f"{team['name']}", font=FONT_TITLE, fill=ON_SURFACE)
    cy += FONT_SIZES["title"] + 4
    draw.text((cx, cy), f"队长: {team['owner_qq']}", font=FONT_CAPTION, fill=MUTED)
    cy += FONT_SIZES["caption"] + CARD_GAP

    draw.text(
        (cx, cy),
        f"成员 ({team['member_count']}/3)",
        font=FONT_SUBTITLE,
        fill=ON_SURFACE,
    )
    cy += FONT_SIZES["subtitle"] + 8

    for m in team.get("members", []):
        crown = " " if m != team["owner_qq"] else " (队长)"
        draw.text((cx + 12, cy), f"{m}{crown}", font=FONT_BODY, fill=ON_SURFACE)
        cy += FONT_SIZES["body"] + 4

    for _ in range(3 - team["member_count"]):
        draw.text((cx + 12, cy), "(空位)", font=FONT_BODY, fill=MUTED)
        cy += FONT_SIZES["body"] + 4

    cy += CARD_GAP

    ttl_hours = team.get("ttl_hours", 12)
    draw.text((cx, cy), f"{ttl_hours} 小时后自动解散", font=FONT_CAPTION, fill=MUTED)

    _draw_centered_text(draw, "auth.赤羽真白 · Apex Chiyuchan", card_x, card_y + card_h - FONT_SIZES["caption"] - 8, card_w, FONT_CAPTION, fill=MUTED)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def draw_team_list_card(teams: list[dict]) -> bytes:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _draw_team_list_sync, teams)


def _draw_team_list_sync(teams: list[dict]) -> bytes:
    count = len(teams)
    item_h = 36
    padding_h = PADDING * 2 + FONT_SIZES["title"] + CARD_GAP
    h = padding_h + count * item_h + PADDING * 2 + FONT_SIZES["small"] + 20
    h = max(h, 200)
    w = TEAM_CARD_W

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    _draw_surface(draw, w, h)

    card_x, card_y = PADDING, PADDING
    card_w = w - PADDING * 2
    card_h = h - PADDING * 2

    _draw_shadow(draw, card_x, card_y, card_w, card_h)
    _draw_card_bg(draw, card_x, card_y, card_w, card_h)

    cx = card_x + PADDING
    cy = card_y + PADDING

    draw.text((cx, cy), f"活跃队伍 ({count})", font=FONT_TITLE, fill=ON_SURFACE)
    cy += FONT_SIZES["title"] + CARD_GAP

    if count == 0:
        draw.text((cx, cy), "暂无活跃队伍", font=FONT_BODY, fill=MUTED)
    else:
        for t in teams:
            draw.text(
                (cx, cy),
                f"{t['name']}  {t['member_count']}/3  队长:{t['owner_qq']}",
                font=FONT_BODY,
                fill=ON_SURFACE,
            )
            cy += item_h

    _draw_centered_text(draw, "auth.赤羽真白 · Apex Chiyuchan", card_x, card_y + card_h - FONT_SIZES["caption"] - 8, card_w, FONT_CAPTION, fill=MUTED)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ══════════════════════════════════════════
#  5. 绑定确认卡片 draw_bind_card
# ══════════════════════════════════════════


async def draw_bind_card(uid: str, name: str, platform: str) -> bytes:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _draw_bind_sync, uid, name, platform)


def _draw_bind_sync(uid: str, name: str, platform: str) -> bytes:
    w, h = BIND_CARD_W, BIND_CARD_H
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    _draw_surface(draw, w, h)

    card_x, card_y = PADDING, PADDING
    card_w = w - PADDING * 2
    card_h = h - PADDING * 2

    _draw_shadow(draw, card_x, card_y, card_w, card_h)
    _draw_card_bg(draw, card_x, card_y, card_w, card_h)

    card_x + PADDING
    cy = card_y + PADDING
    card_w - PADDING * 2

    _draw_centered_text(
        draw, "绑定成功", card_x, cy, card_w, FONT_TITLE, fill=ACCENT_GREEN
    )
    cy += FONT_SIZES["title"] + CARD_GAP

    lines = [
        f"玩家  {name}",
        f"平台  {platform}",
        f"UID   {uid}",
        "",
        "现在可以使用 /stats 查询战绩",
    ]
    for line in lines:
        if line:
            _draw_centered_text(
                draw,
                line,
                card_x,
                cy,
                card_w,
                FONT_BODY,
                fill=ON_SURFACE if lines.index(line) < 3 else MUTED,
            )
        cy += FONT_SIZES["body"] + 6

    _draw_centered_text(draw, "auth.赤羽真白 · Apex Chiyuchan", card_x, card_y + card_h - FONT_SIZES["caption"] - 8, card_w, FONT_CAPTION, fill=MUTED)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def draw_unbind_card() -> bytes:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _draw_unbind_sync)


def _draw_unbind_sync() -> bytes:
    w, h = BIND_CARD_W, BIND_CARD_H - 80
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    _draw_surface(draw, w, h)

    card_x, card_y = PADDING, PADDING
    card_w = w - PADDING * 2
    card_h = h - PADDING * 2

    _draw_shadow(draw, card_x, card_y, card_w, card_h)
    _draw_card_bg(draw, card_x, card_y, card_w, card_h)

    card_x + PADDING
    cy = card_y + PADDING + 20

    _draw_centered_text(
        draw, "已解绑", card_x, cy, card_w, FONT_TITLE, fill=ACCENT_GREEN
    )
    cy += FONT_SIZES["title"] + CARD_GAP
    _draw_centered_text(
        draw, "Apex 账号已与本 QQ 解除绑定", card_x, cy, card_w, FONT_BODY, fill=MUTED
    )

    _draw_centered_text(draw, "auth.赤羽真白 · Apex Chiyuchan", card_x, card_y + card_h - FONT_SIZES["caption"] - 8, card_w, FONT_CAPTION, fill=MUTED)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ══════════════════════════════════════════
#  6. 玩家详情渲染 — 优先 playwright，回退 Pillow
# ══════════════════════════════════════════

# 尝试导入 playwright 渲染器（必须，无回退）
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
    from .playwright_renderer import draw_text_card_pw as _draw_text_card_pw
except Exception as _e:
    from astrbot.api import logger as _lg
    _lg.error(f"[ImageRenderer] Playwright 渲染器导入失败: {type(_e).__name__}: {_e}")
    raise  # Playwright 是必须依赖，导入失败直接崩溃


async def draw_profile_card(data: dict) -> bytes:
    """渲染玩家详情卡片 (仅 Playwright)"""
    from astrbot.api import logger
    try:
        logger.info("[ProfileCard] 使用 Playwright 渲染")
        return await _draw_profile_card_pw(data)
    except Exception as e:
        logger.error(f"[ProfileCard] Playwright 渲染失败: {type(e).__name__}: {e}")
        return await _draw_text_card_pw("渲染错误", f"profile_card 渲染失败: {e}", is_error=True)


async def draw_map_card(rotation) -> bytes:
    """地图轮换 (仅 Playwright)"""
    from astrbot.api import logger
    try:
        return await _draw_map_rotation_card_pw(rotation)
    except Exception as e:
        logger.error(f"[MapCard] Playwright 渲染失败: {type(e).__name__}: {e}")
        return await _draw_text_card_pw("渲染错误", f"map_card 渲染失败: {e}", is_error=True)


async def draw_server_status_card(server_status) -> bytes:
    """服务器状态 (仅 Playwright)"""
    from astrbot.api import logger
    try:
        return await _draw_server_status_card_pw(server_status)
    except Exception as e:
        logger.error(f"[ServerCard] Playwright 渲染失败: {type(e).__name__}: {e}")
        return await _draw_text_card_pw("渲染错误", f"server_card 渲染失败: {e}", is_error=True)


async def draw_master_card(predator) -> bytes:
    """大师/猎杀 (仅 Playwright)"""
    from astrbot.api import logger
    try:
        return await _draw_predator_card_pw(predator)
    except Exception as e:
        logger.error(f"[MasterCard] Playwright 渲染失败: {type(e).__name__}: {e}")
        return await _draw_text_card_pw("渲染错误", f"master_card 渲染失败: {e}", is_error=True)


_PL_SECTION_NAMES = {
    "Crossplay auth (any platform)": "跨平台认证",
    "Lobby/Matchmaking servers": "大厅/匹配服务器",
    "PC/Desktop logins": "PC 登录",
    "Player accounts": "玩家账户",
    "ALS website": "ALS 网站",
    "PSN/Xbox Live status": "PSN/Xbox Live 状态",
}
_PL_STATUS_MAP = {
    "UNSTABLE": "不稳定",
    "UP": "正常",
    "RUNNING": "正常",
    "SLOW": "缓慢",
    "DOWN": "宕机",
    "UNSTABLE / SLOW": "不稳定 / 缓慢",
    "MOSTLY OPERATIONAL": "正常",
    "OPERATIONAL": "正常",
}


def _pl_status(s: str) -> str:
    return _PL_STATUS_MAP.get(s.strip().upper(), s) if s else s

def _pl_name(n: str) -> str:
    return _PL_SECTION_NAMES.get(n.strip(), n)


async def draw_player_list_card(
    players: list[dict], hint: str = ""
) -> bytes:
    """使用 Playwright 渲染玩家列表卡片"""
    import time
    from .playwright_manager import run_with_page
    t0 = time.time()

    plat_colors = {
        "PC": "#4DABF7", "PS4": "#4ECDC4", "X1": "#4CE5B1",
    }
    rank_colors = {
        "Rookie": "#89A0B0", "Bronze": "#CD7F32", "Silver": "#C0C0C0",
        "Gold": "#FFD700", "Platinum": "#4ECDC4", "Diamond": "#74B9FF",
        "Master": "#A855F7", "Predator": "#DA292A",
    }

    plat_icons = {
        "PC": '<i class="fab fa-steam" style="color:#6DA8FF;"></i>',
        "PS4": '<i class="fab fa-playstation" style="color:#64C3D3;"></i>',
        "PS5": '<i class="fab fa-playstation" style="color:#64C3D3;"></i>',
        "X1": '<i class="fab fa-xbox" style="color:#4CE5B1;"></i>',
        "SWITCH": '<i class="fas fa-gamepad" style="color:#FF6B6B;"></i>',
    }

    # MD3 配色（Diamond 主题）
    C_SURFACE = "#0F1218"
    C_CARD = "#171A22"
    C_CARD2 = "#1D222C"
    C_CARD3 = "#272D39"
    C_TEXT = "#DDE4F3"
    C_MUTED = "#BFC7DA"
    C_OUTLINE = "#444C5C"
    C_PRIMARY = "#6DA8FF"

    cards_html = ""
    for i, r in enumerate(players):
        name = r.get("name", "?")
        uid = r.get("uid", "?")
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
    hint_html = f'<div class="hint">{hint}</div>' if hint else ""

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

    try:
        async with run_with_page(viewport={"width": 780, "height": 800}, device_scale_factor=1.5) as page:
            await page.set_content(html, wait_until="domcontentloaded")
            card = await page.query_selector(".card-container")
            if card:
                png = await card.screenshot(type="png", omit_background=True)
            else:
                png = await page.screenshot(type="png", full_page=True, omit_background=True)
            dt = time.time() - t0
            from astrbot.api import logger
            logger.info(f"[PW卡片] 渲染耗时: {dt:.1f}s ({len(players)}个玩家)")
            return png
    except Exception:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, _draw_player_list_sync, players, hint)


def _draw_player_list_sync(players: list[dict], hint: str) -> bytes:
    # ── MD3 常量 ──
    SURFACE_VARIANT = "#1D2E3F"
    PILL_RADIUS = 10
    CARD_GAP_SM = 10
    ITEM_CARD_H = 88
    ITEM_CARD_PAD = 14

    n = len(players)
    title_h = FONT_SIZES["title"] + CARD_GAP
    body_h = n * (ITEM_CARD_H + CARD_GAP_SM)
    hint_h = (FONT_SIZES["caption"] + 20) if hint else 0

    w = BIND_CARD_W
    h = PADDING * 3 + title_h + body_h + hint_h + 20

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    _draw_surface(draw, w, h)

    card_x0, card_y0 = PADDING // 2, PADDING // 2
    card_w0 = w - PADDING
    card_h0 = h - PADDING
    _draw_shadow(draw, card_x0, card_y0, card_w0, card_h0)
    _draw_card_bg(draw, card_x0, card_y0, card_w0, card_h0)

    cx = card_x0 + PADDING
    cy = card_y0 + PADDING

    title_text = f"找到 {n} 个玩家"
    _draw_centered_text(draw, title_text, card_x0, cy, card_w0, FONT_TITLE, fill=ACCENT_GREEN)
    cy += FONT_SIZES["title"] + CARD_GAP + 4

    for i, r in enumerate(players):
        name = r.get("name", "?")
        uid = r.get("uid", "?")
        plat = r.get("platform", "PC")
        plat_color = PLATFORM_COLORS.get(plat, MUTED)
        level = str(r.get("level", ""))
        prestige = str(r.get("prestige", ""))

        item_left = cx
        item_top = cy
        item_w = card_w0 - PADDING * 2
        item_h = ITEM_CARD_H

        draw.rounded_rectangle(
            [item_left, item_top, item_left + item_w, item_top + item_h],
            radius=PILL_RADIUS,
            fill=SURFACE_VARIANT,
        )

        badge_size = 36
        badge_x = item_left + ITEM_CARD_PAD
        badge_y = item_top + (item_h - badge_size) // 2
        draw.ellipse(
            [badge_x, badge_y, badge_x + badge_size, badge_y + badge_size],
            fill=ACCENT_GREEN,
        )
        num_str = str(i + 1)
        num_w2, num_h2 = _text_bbox(draw, num_str, FONT_SUBTITLE)
        draw.text(
            (badge_x + (badge_size - num_w2) // 2, badge_y + (badge_size - num_h2) // 2 - 1),
            num_str, font=FONT_SUBTITLE, fill=SURFACE,
        )

        pw, ph = _text_bbox(draw, plat, FONT_CAPTION)
        pill_pad_x = 10
        pill_pad_y = 4
        pill_w = pw + pill_pad_x * 2
        pill_h = ph + pill_pad_y * 2
        pill_x = item_left + item_w - ITEM_CARD_PAD - pill_w
        pill_y = item_top + (item_h - pill_h) // 2 + 1
        r2, g2, b2 = _hex_to_rgb(plat_color)
        draw.rounded_rectangle(
            [pill_x, pill_y, pill_x + pill_w, pill_y + pill_h],
            radius=PILL_RADIUS // 2,
            fill=(r2, g2, b2, 60),
        )
        draw.text(
            (pill_x + pill_pad_x, pill_y + pill_pad_y),
            plat, font=FONT_CAPTION, fill=plat_color,
        )

        name_x = badge_x + badge_size + 14
        name_y = item_top + 12

        lvl_label = f"Lv.{level}" if level else ""
        lvl_w, _ = _text_bbox(draw, lvl_label, FONT_CAPTION) if lvl_label else (0, 0)

        name_max_w = pill_x - name_x - 12 - lvl_w - 8
        name_trunc = _truncate_text(draw, name, FONT_SUBTITLE, max(name_max_w, 40))
        draw.text((name_x, name_y), name_trunc, font=FONT_SUBTITLE, fill=ON_SURFACE)

        if lvl_label:
            nw_drawn, _ = _text_bbox(draw, name_trunc, FONT_SUBTITLE)
            lvl_x = name_x + nw_drawn + 8
            draw.text((lvl_x, name_y + 2), lvl_label, font=FONT_CAPTION, fill=MUTED)

        rank_y = name_y + FONT_SIZES["subtitle"] + 2
        rank_line = ""
        rank_name = _parse_rank_name(r.get("rank_img", ""))
        rp_val = str(r.get("rp", ""))
        if rank_name:
            rank_line = rank_name
        if rp_val:
            rp_fmt = f"{int(rp_val):,} RP" if rp_val.isdigit() else rp_val
            rank_line = (rank_line + "  ·  " + rp_fmt) if rank_line else rp_fmt
        if rank_line:
            rank_trunc = _truncate_text(draw, rank_line, FONT_CAPTION, pill_x - name_x - 12)
            draw.text((name_x, rank_y), rank_trunc, font=FONT_CAPTION, fill=ON_SURFACE)

        uid_label = f"UID: {uid}"
        uid_y = rank_y + (FONT_SIZES["caption"] + 4 if rank_line else 0)
        uid_max_w = item_w - ITEM_CARD_PAD * 2 - badge_size - 14 - pill_w - 12
        uid_trunc = _truncate_text(draw, uid_label, FONT_CAPTION, uid_max_w)
        draw.text((name_x, uid_y), uid_trunc, font=FONT_CAPTION, fill=MUTED)

        cy += ITEM_CARD_H + CARD_GAP_SM

    if hint:
        cy += 4
        _draw_centered_text(
            draw, hint, card_x0, cy, card_w0, FONT_CAPTION, fill=MUTED
        )

    _draw_centered_text(draw, "auth.赤羽真白 · Apex Chiyuchan", card_x0, card_y0 + card_h0 - FONT_SIZES["caption"] - 8, card_w0, FONT_CAPTION, fill=MUTED)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def draw_lfg_mode_card() -> bytes:
    """LFG 模式选择卡片 (仅 Playwright)"""
    from astrbot.api import logger
    try:
        return await _draw_lfg_mode_card_pw()
    except Exception as e:
        logger.error(f"[LfgModeCard] Playwright 渲染失败: {type(e).__name__}: {e}")
        return await _draw_text_card_pw("渲染错误", f"lfg_mode_card 渲染失败: {e}", is_error=True)


async def draw_lfg_card(entries: list[dict]) -> bytes:
    """LFG 找队友卡片 (仅 Playwright)"""
    from astrbot.api import logger
    try:
        return await _draw_lfg_card_pw(entries)
    except Exception as e:
        logger.error(f"[LfgCard] Playwright 渲染失败: {type(e).__name__}: {e}")
        return await _draw_text_card_pw("渲染错误", f"lfg_card 渲染失败: {e}", is_error=True)



# ══════════════════════════════════════════
#  Steamcharts 日活卡片（仅 Playwright，无 Pillow 回退）
# ══════════════════════════════════════════


async def draw_steamcharts_card(data) -> bytes:
    """渲染 Steamcharts 日活卡片 PNG (Jinja 模板 + Chart.js，仅 Playwright)"""
    if _draw_steamcharts_card_pw is None:
        raise RuntimeError("Playwright 渲染器未导入，无法渲染 Steamcharts 卡片")
    return await _draw_steamcharts_card_pw(data)
