"""Material Design 卡片图片渲染引擎 — 5 种卡片类型"""

from __future__ import annotations

import io
import asyncio
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw, ImageFont, ImageSequence
import httpx

from .config import (
    SURFACE, CARD, PRIMARY, ON_SURFACE, MUTED, DIVIDER, ACCENT_GREEN, ACCENT_BLUE, SHADOW,
    PADDING, RADIUS, CARD_GAP,
    STATS_CARD_W, STATS_CARD_H, MAP_CARD_W, MAP_CARD_H,
    MASTER_CARD_W, MASTER_CARD_H, TEAM_CARD_W, TEAM_CARD_H, BIND_CARD_W, BIND_CARD_H,
    PROFILE_CARD_W, PROFILE_CARD_H,
    PLATFORM_COLORS,
    load_font, get_rank_color, FONT_SIZES,
)

_executor = ThreadPoolExecutor(max_workers=2)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def _draw_surface(draw: ImageDraw.Draw, w: int, h: int):
    draw.rectangle([0, 0, w, h], fill=SURFACE)


def _draw_shadow(draw: ImageDraw.Draw, x: int, y: int, w: int, h: int):
    draw.rounded_rectangle([x + 3, y + 5, x + w + 3, y + h + 5], radius=RADIUS, fill=SHADOW)


def _draw_card_bg(draw: ImageDraw.Draw, x: int, y: int, w: int, h: int):
    draw.rounded_rectangle([x, y, x + w, y + h], radius=RADIUS, fill=CARD)


def _text_bbox(draw: ImageDraw.Draw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _draw_centered_text(draw: ImageDraw.Draw, text: str, x: int, y: int, w: int,
                        font: ImageFont.FreeTypeFont, fill: str = ON_SURFACE):
    tw, _ = _text_bbox(draw, text, font)
    draw.text((x + (w - tw) // 2, y), text, font=font, fill=fill)


def _draw_section_header(draw: ImageDraw.Draw, x: int, y: int, icon: str, text: str,
                         font: ImageFont.FreeTypeFont, fill: str = ON_SURFACE):
    full = f"{icon}  {text}" if icon else text
    draw.text((x, y), full, font=font, fill=fill)
    tw, th = _text_bbox(draw, full, font)
    return y + th + 12


def _draw_metric_bubble(draw: ImageDraw.Draw, x: int, y: int, w: int, h: int,
                        label: str, value: str, value_color: str = ON_SURFACE):
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
_MOE_DIGIT_BASE = "https://raw.githubusercontent.com/journey-ad/Moe-Counter/master/assets/theme/rule34"
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

    results = await asyncio.gather(*[fetch_one(d) for d in "0123456789"], return_exceptions=True)
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
    """同步加载 Moe 数字（先磁盘缓存，失败则跳过）"""
    global _moe_loaded
    if _moe_loaded:
        return
    if _load_moe_digits_from_disk():
        return
    # 磁盘缓存不可用，同步下载兜底
    from .http_client import get_sync_client
    client = get_sync_client()
    for d in "0123456789":
        try:
            r = client.get(f"{_MOE_DIGIT_BASE}/{d}.gif")
            r.raise_for_status()
            data = r.content
            cache_dir = _get_moe_cache_dir()
            try:
                (cache_dir / f"{d}.png").write_bytes(data)
            except Exception:
                pass
            img = Image.open(io.BytesIO(data))
            frames = []
            for frame in ImageSequence.Iterator(img):
                f = frame.copy()
                if f.mode != "RGBA":
                    f = f.convert("RGBA")
                frames.append(f)
            _moe_digit_frames[d] = frames
        except Exception as e:
            logger = None
            try:
                from astrbot.api import logger as _log
                logger = _log
            except Exception:
                pass
            if logger:
                logger.warning(f"[image_renderer] Failed to load Moe digit {d}.gif: {e}")
    if _moe_digit_frames:
        _normalize_moe_frames()
    _moe_loaded = True


def _paste_moe_number_frame(draw: ImageDraw.Draw, number: int, x: int, y: int,
                            max_height: int, frame_idx: int) -> int:
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
    draw.text((name_x, cy + FONT_SIZES["title"] + 2), status_str, font=FONT_CAPTION, fill=MUTED)

    dot_x = name_x + tw + 8
    dot_y = cy + FONT_SIZES["title"] + 6
    draw.ellipse([dot_x, dot_y, dot_x + 8, dot_y + 8], fill=status_color)
    draw.text((dot_x + 12, cy + FONT_SIZES["title"] + 2), status_text, font=FONT_CAPTION, fill=status_color)

    cy += FONT_SIZES["title"] + FONT_SIZES["caption"] + PADDING

    # 段位行
    rank_color = get_rank_color(stats.rank_name)
    rank_bar_x = cx - 4
    rank_bar_y = cy - 2
    rank_bar_h = 64
    draw.rectangle([rank_bar_x, rank_bar_y, rank_bar_x + 4, rank_bar_y + rank_bar_h], fill=rank_color)

    rank_name_full = stats.rank_name
    draw.text((cx + 14, cy), rank_name_full, font=FONT_SUBTITLE, fill=rank_color)
    draw.text((cx + 14, cy + FONT_SIZES["subtitle"] + 4),
              f"RP {stats.rank_score:,}", font=FONT_BODY, fill=ON_SURFACE)

    top_pct_str = f"全服 Top {stats.rank_top_pct}%"
    draw.text((cx + 14, cy + FONT_SIZES["subtitle"] + FONT_SIZES["body"] + 6),
              top_pct_str, font=FONT_CAPTION, fill=MUTED)

    cy += rank_bar_h + 8

    # 分隔线
    line_y = cy
    draw.line([(cx, line_y), (cx + cw, line_y)], fill=_hex_to_rgb(DIVIDER.replace("rgba(", "").replace(")", ""))[:3])

    cy = line_y + CARD_GAP

    # 生涯数据三列
    section_y = _draw_section_header(draw, cx, cy, "", "生涯数据总览", FONT_SUBTITLE)
    cy = section_y

    bubble_w = cw // 3
    bubble_h = 60

    _draw_metric_bubble(draw, cx, cy, bubble_w, bubble_h, "击杀", f"{stats.kills:,}")
    _draw_metric_bubble(draw, cx + bubble_w, cy, bubble_w, bubble_h, "伤害", f"{stats.damage:,}")
    kd_str = f"{stats.kd:.2f}" if stats.kd is not None else "--"
    _draw_metric_bubble(draw, cx + bubble_w * 2, cy, bubble_w, bubble_h, "K/D", kd_str)

    cy += bubble_h + CARD_GAP

    # 常用英雄 TOP3
    if stats.top_legends:
        section_y = _draw_section_header(draw, cx, cy, "", "常用英雄 TOP3", FONT_SUBTITLE)
        cy = section_y

        legend_w = cw // 3
        legend_h = 56

        for i, legend in enumerate(stats.top_legends):
            lx = cx + i * legend_w
            _draw_legend_box(draw, lx, cy, legend_w, legend_h, legend["name"], legend["kills"])

        cy += legend_h + CARD_GAP

    # 当前使用
    if stats.selected_legend:
        footer = f"当前选用: {stats.selected_legend}"
        draw.text((cx, cy), footer, font=FONT_CAPTION, fill=MUTED)

    # 数据来源
    cy = card_y + card_h - PADDING - FONT_SIZES["small"]
    _draw_centered_text(draw, "Data: apexlegendsstatus.com", card_x, cy, card_w, FONT_SMALL, fill=MUTED)

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


def _draw_legend_box(draw: ImageDraw.Draw, x: int, y: int, w: int, h: int, name: str, kills: int):
    nw, _ = _text_bbox(draw, name, FONT_CAPTION)
    kw, kh = _text_bbox(draw, f"{kills:,}", FONT_BODY)

    name_x = x + (w - nw) // 2
    kills_x = x + (w - kw) // 2

    draw.text((name_x, y), name, font=FONT_CAPTION, fill=MUTED)
    draw.text((kills_x, y + FONT_SIZES["caption"] + 4), f"{kills:,}", font=FONT_BODY, fill=ON_SURFACE)


# ══════════════════════════════════════════
#  2. 地图轮换卡片 draw_map_card
# ══════════════════════════════════════════

async def _draw_map_card_pillow(rotation) -> bytes:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _draw_map_sync, rotation)


def _draw_map_sync(rotation) -> bytes:
    w, h = MAP_CARD_W, MAP_CARD_H
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

    draw.text((cx, cy), "地图轮换", font=FONT_TITLE, fill=ON_SURFACE)
    cy += FONT_SIZES["title"] + CARD_GAP

    # 匹配
    cy = _draw_map_section(draw, cx, cy, cw, "匹配", rotation.br_current, rotation.br_next)
    cy += 4

    # 排位
    cy = _draw_map_section(draw, cx, cy, cw, "排位", rotation.ranked_current, rotation.ranked_next)
    cy += 4

    # LTM
    ltm_current = rotation.ltm_current
    if ltm_current and ltm_current.event_name:
        ltm_text = f"限时模式  {ltm_current.event_name} · {ltm_current.map} · 剩余 {ltm_current.remaining_timer}"
        draw.text((cx, cy), ltm_text, font=FONT_BODY, fill=ACCENT_GREEN)
        cy += FONT_SIZES["body"] + 4

    # 数据来源
    bottom_y = card_y + card_h - PADDING - FONT_SIZES["small"]
    _draw_centered_text(draw, "Data: apexlegendsstatus.com", card_x, bottom_y, card_w, FONT_SMALL, fill=MUTED)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _draw_map_section(draw, x: int, y: int, w: int, label: str, current, next_) -> int:
    font_h = FONT_SIZES["subtitle"]

    mode_colors = {"匹配": ACCENT_BLUE, "排位": ACCENT_GREEN}
    color = mode_colors.get(label, ACCENT_BLUE)

    prefix = "🎮" if label == "匹配" else "🏆" if label == "排位" else "⚡"
    draw.text((x, y), f"{prefix} {label}", font=FONT_SUBTITLE, fill=color)
    y += font_h + 6

    current_str = f"当前: {current.map}"
    if current.remaining_timer:
        current_str += f"  (剩余 {current.remaining_timer})"
    draw.text((x + 16, y), current_str, font=FONT_BODY, fill=ON_SURFACE)
    y += FONT_SIZES["body"] + 4

    if next_ and next_.map:
        draw.text((x + 16, y), f"下一张: {next_.map}", font=FONT_BODY, fill=MUTED)
        y += FONT_SIZES["body"] + 4

    y += 8
    line_y = y
    draw.line([(x, line_y), (x + w, line_y)], fill=_hex_to_rgb(DIVIDER))
    y += CARD_GAP
    return y


# ══════════════════════════════════════════
#  3. 大师数据卡片 draw_master_card (animated GIF, Material Design)
# ══════════════════════════════════════════

async def _draw_master_card_pillow(predator) -> bytes:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _draw_master_sync, predator)


def _draw_master_sync(predator) -> bytes:
    _load_moe_digits()

    DIGIT_H = 52
    COL_GAP = 20
    CELL_PAD = 18

    w, h = MASTER_CARD_W, MASTER_CARD_H
    card_x = PADDING
    card_y = PADDING
    card_w = w - PADDING * 2
    card_h = h - PADDING * 2
    cx = card_x + PADDING
    cy0 = card_y + PADDING + 4  # top padding inside card

    # 2-col grid layout
    col_w = (card_w - PADDING * 2 - COL_GAP) // 2
    cell_w = col_w

    platforms_order = ["PC", "PS4", "X1", "SWITCH"]

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    _draw_surface(draw, w, h)
    _draw_shadow(draw, card_x, card_y, card_w, card_h)
    _draw_card_bg(draw, card_x, card_y, card_w, card_h)

    # Title
    draw.text((cx, cy0), "大师 / 猎杀 数据", font=FONT_TITLE, fill=ON_SURFACE)

    grid_top = cy0 + FONT_SIZES["title"] + CARD_GAP + 4

    for idx, platform in enumerate(platforms_order):
        pd = predator.platforms.get(platform)
        if not pd:
            continue
        plat_color = PLATFORM_COLORS.get(platform, ON_SURFACE)

        col = idx % 2
        row = idx // 2
        cell_x = cx + col * (col_w + COL_GAP)
        cell_y = grid_top + row * 190  # height per cell

        _draw_platform_cell(draw, cell_x, cell_y, cell_w,
                           platform, pd.predator_cap, pd.masters_and_preds,
                           plat_color, DIGIT_H, CELL_PAD, 0)

    # Footer
    bottom_y = card_y + card_h - PADDING - FONT_SIZES["small"] - 2
    _draw_centered_text(draw, "Data: apexlegendsstatus.com", card_x, bottom_y,
                        card_w, FONT_SMALL, fill=MUTED)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _draw_platform_cell(
    draw: ImageDraw.Draw, x: int, y: int, w: int,
    platform: str, cap: int, count: int, plat_color: str,
    digit_h: int, pad: int, frame_idx: int,
) -> None:
    """Material Design 卡片式平台单元格"""
    cell_h = 180

    # 卡片背景 + 阴影
    draw.rounded_rectangle([x + 2, y + 3, x + w + 2, y + cell_h + 3],
                           radius=12, fill=SHADOW)
    draw.rounded_rectangle([x, y, x + w, y + cell_h],
                           radius=12, fill="#162230")

    ix = x + pad
    iy = y + pad

    # 平台芯片
    plat_lw, plat_th = _text_bbox(draw, platform, FONT_SUBTITLE)
    chip_w = plat_lw + 20
    chip_h = plat_th + 10
    draw.rounded_rectangle(
        [ix, iy, ix + chip_w, iy + chip_h], radius=8, fill=plat_color)
    draw.text((ix + (chip_w - plat_lw) // 2, iy + 5),
              platform, font=FONT_SUBTITLE, fill=ON_SURFACE)

    iy += chip_h + 14

    # 猎杀线行
    label = "猎杀线"
    lw, lh = _text_bbox(draw, label, FONT_BODY)
    draw.text((ix, iy + (digit_h - lh) // 2 + 2), label, font=FONT_BODY, fill=MUTED)
    label_x = ix + lw + 12
    _paste_moe_number_frame(draw, cap, label_x, iy, digit_h, frame_idx)

    iy += digit_h + 10

    # 分隔线
    draw.line([(ix, iy), (x + w - pad, iy)], fill=_hex_to_rgb(DIVIDER))
    iy += 10

    # 大师人数行
    label2 = "大师人数"
    lw2, lh2 = _text_bbox(draw, label2, FONT_BODY)
    draw.text((ix, iy + (digit_h - lh2) // 2 + 2), label2, font=FONT_BODY, fill=MUTED)
    label_x2 = ix + lw2 + 12
    _paste_moe_number_frame(draw, count, label_x2, iy, digit_h, frame_idx)


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
    cw = card_w - PADDING * 2

    draw.text((cx, cy), f"{team['name']}", font=FONT_TITLE, fill=ON_SURFACE)
    cy += FONT_SIZES["title"] + 4
    draw.text((cx, cy), f"队长: {team['owner_qq']}", font=FONT_CAPTION, fill=MUTED)
    cy += FONT_SIZES["caption"] + CARD_GAP

    draw.text((cx, cy), f"成员 ({team['member_count']}/3)", font=FONT_SUBTITLE, fill=ON_SURFACE)
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
            draw.text((cx, cy),
                      f"{t['name']}  {t['member_count']}/3  队长:{t['owner_qq']}",
                      font=FONT_BODY, fill=ON_SURFACE)
            cy += item_h

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

    cx = card_x + PADDING
    cy = card_y + PADDING
    cw = card_w - PADDING * 2

    _draw_centered_text(draw, "绑定成功", card_x, cy, card_w, FONT_TITLE, fill=ACCENT_GREEN)
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
            _draw_centered_text(draw, line, card_x, cy, card_w, FONT_BODY, fill=ON_SURFACE if lines.index(line) < 3 else MUTED)
        cy += FONT_SIZES["body"] + 6

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

    cx = card_x + PADDING
    cy = card_y + PADDING + 20

    _draw_centered_text(draw, "已解绑", card_x, cy, card_w, FONT_TITLE, fill=ACCENT_GREEN)
    cy += FONT_SIZES["title"] + CARD_GAP
    _draw_centered_text(draw, "Apex 账号已与本 QQ 解除绑定", card_x, cy, card_w, FONT_BODY, fill=MUTED)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ══════════════════════════════════════════
#  6. 玩家详情渲染 — 优先 playwright，回退 Pillow
# ══════════════════════════════════════════

# 尝试导入 playwright 渲染器
try:
    from .playwright_renderer import draw_profile_card as _draw_profile_card_pw
    from .playwright_renderer import draw_map_rotation_card as _draw_map_rotation_card_pw
    from .playwright_renderer import draw_server_status_card as _draw_server_status_card_pw
    from .playwright_renderer import draw_predator_card as _draw_predator_card_pw
except Exception:
    _draw_profile_card_pw = None
    _draw_map_rotation_card_pw = None
    _draw_server_status_card_pw = None
    _draw_predator_card_pw = None


async def draw_profile_card(data: dict) -> bytes:
    """渲染玩家详情卡片 (优先 playwright，回退 Pillow)"""
    if _draw_profile_card_pw is not None:
        try:
            return await _draw_profile_card_pw(data)
        except Exception:
            pass  # playwright 失败则回退
    return await draw_player_profile_card(data)


async def draw_map_card(rotation) -> bytes:
    """地图轮换 (优先 playwright，回退 Pillow)"""
    if _draw_map_rotation_card_pw is not None:
        try:
            return await _draw_map_rotation_card_pw(rotation)
        except Exception:
            pass
    return await _draw_map_card_pillow(rotation)


async def draw_server_status_card(server_status) -> bytes:
    """服务器状态 (优先 playwright，回退 Pillow)"""
    if _draw_server_status_card_pw is not None:
        try:
            return await _draw_server_status_card_pw(server_status)
        except Exception:
            pass
    return await _draw_server_status_card_pillow(server_status)


async def draw_master_card(predator) -> bytes:
    """大师/猎杀 (优先 playwright，回退 Pillow)"""
    if _draw_predator_card_pw is not None:
        try:
            return await _draw_predator_card_pw(predator)
        except Exception:
            pass
    return await _draw_master_card_pillow(predator)


async def _draw_server_status_card_pillow(server_status) -> bytes:
    """服务器状态 Pillow 回退 — 简洁文本卡片"""
    lines = []
    for s in server_status.servers:
        dot = "●" if s.is_up else "○"
        lines.append(f"{dot} {s.display_name}  {s.status_text}  {s.response_time}ms")
    return await draw_text_card("服务器状态", "\n".join(lines) if lines else "无数据")


# ══════════════════════════════════════════
#  6b. Pillow 版玩家详情卡片 (回退/兼容)
# ══════════════════════════════════════════

async def draw_player_profile_card(data: dict) -> bytes:
    loop = asyncio.get_running_loop()

    # ── 并行下载所有图片 ──
    tasks = []

    # 段位图标
    rank_url = data.get("rank_icon_url", "")
    rank_task = _fetch_image(rank_url, (80, 80))
    tasks.append(("rank_icon", rank_url, rank_task))

    # 头像
    avatar_url = data.get("avatar_url", "")
    avatar_task = _fetch_image(avatar_url, (56, 56))
    tasks.append(("avatar", avatar_url, avatar_task))

    # 赛季徽章
    badge_urls = []
    for b in data.get("season_badges", []):
        url = b.get("badge_url", "")
        if url:
            badge_urls.append((b["season"], url))

    # 特殊徽章
    special_urls = []
    for b in data.get("special_badges", []):
        url = b.get("url", "")
        if url:
            special_urls.append((b["name"], url))

    # 英雄图标
    legend_urls = []
    for leg in data.get("top_legends", []):
        url = leg.get("icon_url", "")
        if url and url not in [u for _, u in legend_urls]:
            legend_urls.append((leg["name"], url))

    # 合并所有下载任务
    badge_tasks = [(f"badge_{s}", url, _fetch_image(url, (36, 36))) for s, url in badge_urls]
    special_tasks = [(f"special_{n}", url, _fetch_image(url, (36, 36))) for n, url in special_urls]
    legend_tasks = [(f"legend_{n}", url, _fetch_image(url, (32, 32))) for n, url in legend_urls]

    all_tasks = tasks + badge_tasks + special_tasks + legend_tasks
    results = await asyncio.gather(*[t[2] for t in all_tasks], return_exceptions=True)

    # ── 组装结果 ──
    rank_icon = None
    avatar = None
    badge_imgs: dict[str, Image.Image] = {}
    special_badge_imgs: dict[str, Image.Image] = {}
    legend_icon_map: dict[str, Image.Image] = {}

    for i, (key, url, _) in enumerate(all_tasks):
        img = results[i]
        if isinstance(img, Exception) or img is None:
            continue
        if key == "rank_icon":
            rank_icon = img
        elif key == "avatar":
            avatar = _draw_round_avatar(img, 56)
        elif key.startswith("badge_"):
            season = key[6:]
            badge_imgs[season] = img
        elif key.startswith("special_"):
            name = key[8:]
            special_badge_imgs[name] = img
        elif key.startswith("legend_"):
            name = key[7:]
            legend_icon_map[name] = img

    return await loop.run_in_executor(
        _executor, _draw_profile_sync, data, rank_icon, avatar,
        badge_imgs, special_badge_imgs, legend_icon_map,
    )


def _draw_profile_sync(
    data: dict,
    rank_icon: Image.Image | None,
    avatar: Image.Image | None,
    badge_imgs: dict[str, Image.Image],
    special_badge_imgs: dict[str, Image.Image],
    legend_icon_map: dict[str, Image.Image],
) -> bytes:
    w, h = PROFILE_CARD_W, PROFILE_CARD_H
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

    # ── Header: Avatar + Name + Tag ──
    name = data.get("name", "Unknown")
    tag = data.get("tag", "")
    alias = data.get("alias", "")
    platform = data.get("platform", "PC")
    online = data.get("online_status", "offline")

    if avatar:
        img.paste(avatar, (cx, cy), avatar)
        header_x = cx + 68
    else:
        header_x = cx

    display_name = f"{name} [{tag}]" if tag else name
    draw.text((header_x, cy - 2), display_name, font=FONT_TITLE, fill=ON_SURFACE)

    alias_y = cy + FONT_SIZES["title"] + 2
    if alias:
        draw.text((header_x, alias_y), f"aka {alias}", font=FONT_CAPTION, fill=MUTED)
        alias_y += FONT_SIZES["caption"] + 4

    online_color = ACCENT_GREEN if online == "online" else MUTED
    dot_x, dot_y = header_x, alias_y
    draw.ellipse([dot_x, dot_y + 2, dot_x + 8, dot_y + 10], fill=online_color)
    status_map = {"online": "在线", "offline": "离线", "in_game": "游戏中", "offline": "离线"}
    draw.text((dot_x + 12, dot_y), f"{platform} · {status_map.get(online, online)}",
              font=FONT_CAPTION, fill=online_color)

    cy = dot_y + FONT_SIZES["caption"] + PADDING

    # ── Rank Section ──
    rank_name = data.get("rank_name", "Unranked")
    rank_div = data.get("rank_div", 0)
    rank_score = data.get("rank_score", 0)
    rank_top_pct = data.get("rank_top_pct", "--")
    rank_top_pct_global = data.get("rank_top_pct_global", "--")
    rank_color = get_rank_color(rank_name)

    draw.line([(cx, cy), (cx + cw, cy)], fill=_hex_to_rgb(DIVIDER))
    cy += CARD_GAP

    rank_icon_x = cx
    rank_icon_y = cy
    if rank_icon:
        img.paste(rank_icon, (rank_icon_x, rank_icon_y), rank_icon)
        rank_text_x = rank_icon_x + 92
    else:
        rank_text_x = rank_icon_x

    rank_full = f"{rank_name}{' ' + _rank_div_label(rank_div) if rank_div else ''}"
    draw.text((rank_text_x, cy - 2), rank_full, font=FONT_TITLE, fill=rank_color)

    draw.text((rank_text_x, cy + FONT_SIZES["title"] + 4),
              f"{rank_score:,} RP", font=FONT_SUBTITLE, fill=ON_SURFACE)

    draw.text((rank_text_x, cy + FONT_SIZES["title"] + FONT_SIZES["subtitle"] + 8),
              f"ALS Top {rank_top_pct}%  |  Global Top {rank_top_pct_global}%",
              font=FONT_CAPTION, fill=MUTED)

    cy += 90

    # ── Level Bar ──
    level = data.get("level", 1)
    prestige = data.get("prestige", 0)
    level_pct = data.get("level_pct", 0)
    uid = data.get("uid", "")

    lvl_text = f"Lv.{level}"
    if prestige:
        lvl_text += f"  P{prestige}"

    lvl_tw, _ = _text_bbox(draw, lvl_text, FONT_SUBTITLE)
    draw.text((cx, cy), lvl_text, font=FONT_SUBTITLE, fill=ON_SURFACE)

    uid_str = f"UID: {uid}"
    draw.text((cx, cy + FONT_SIZES["subtitle"] + 4), uid_str, font=FONT_CAPTION, fill=MUTED)

    bar_x = cx + max(lvl_tw, _text_bbox(draw, uid_str, FONT_CAPTION)[0]) + CARD_GAP + 40
    bar_y = cy + FONT_SIZES["subtitle"] // 2 - 3
    bar_w = cw - (bar_x - cx)
    bar_h = 6

    draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h],
                           radius=3, fill="#222E3F")
    fill_w = int(bar_w * level_pct / 100)
    if fill_w > 0:
        draw.rounded_rectangle([bar_x, bar_y, bar_x + fill_w, bar_y + bar_h],
                               radius=3, fill=PRIMARY)

    pct_str = f"{level_pct}%"
    draw.text((bar_x + bar_w + 8, bar_y - 6), pct_str, font=FONT_CAPTION, fill=MUTED)

    cy += FONT_SIZES["subtitle"] + FONT_SIZES["caption"] + CARD_GAP + 4

    # ── Divider ──
    draw.line([(cx, cy), (cx + cw, cy)], fill=_hex_to_rgb(DIVIDER))
    cy += CARD_GAP

    # ── Core Stats ──
    kills = data.get("kills", 0)
    damage = data.get("damage", 0)
    wins = data.get("wins", 0)

    col_w = cw // 3
    stat_h = 52
    _draw_metric_bubble(draw, cx, cy, col_w, stat_h, "生涯击杀", f"{kills:,}")
    _draw_metric_bubble(draw, cx + col_w, cy, col_w, stat_h, "BR 总伤害", f"{damage:,}")
    _draw_metric_bubble(draw, cx + col_w * 2, cy, col_w, stat_h, "BR 胜场", f"{wins:,}")

    cy += stat_h + CARD_GAP
    draw.line([(cx, cy), (cx + cw, cy)], fill=_hex_to_rgb(DIVIDER))
    cy += CARD_GAP

    # ── Selected Legend ──
    selected = data.get("selected_legend")
    if selected:
        sel_name = selected.get("name", "")
        sel_stats = selected.get("stats", [])

        sel_icon = legend_icon_map.get(sel_name) if sel_name in legend_icon_map else None

        draw.text((cx, cy), "当前选用", font=FONT_CAPTION, fill=MUTED)
        cy += FONT_SIZES["caption"] + 6

        sel_x = cx
        if sel_icon:
            img.paste(sel_icon, (sel_x, cy), sel_icon)
            sel_name_x = sel_x + 42
        else:
            sel_name_x = sel_x

        draw.text((sel_name_x, cy), sel_name, font=FONT_SUBTITLE, fill=ON_SURFACE)

        for i, st in enumerate(sel_stats):
            sname = st.get("name", "")
            sval = st.get("value", "")
            sx = sel_name_x + 160 + i * 200
            draw.text((sx, cy + 2), sname, font=FONT_CAPTION, fill=MUTED)
            draw.text((sx, cy + FONT_SIZES["caption"] + 4), sval,
                      font=FONT_BODY, fill=ON_SURFACE)

        cy += 42 + CARD_GAP
        draw.line([(cx, cy), (cx + cw, cy)], fill=_hex_to_rgb(DIVIDER))
        cy += CARD_GAP

    # ── Top Legends ──
    top_legends = data.get("top_legends", [])
    if top_legends:
        draw.text((cx, cy), "常用英雄", font=FONT_CAPTION, fill=MUTED)
        cy += FONT_SIZES["caption"] + 6

        slot_w = (cw - CARD_GAP * 3) // 4
        slot_h = 56

        for i, leg in enumerate(top_legends[:4]):
            lx = cx + i * (slot_w + CARD_GAP)
            icon = legend_icon_map.get(leg["name"])

            ldraw = draw
            icon_size = 28

            _draw_small_legend_box(ldraw, img, lx, cy, slot_w, slot_h,
                                   icon, leg["name"], leg.get("kills", 0),
                                   icon_size)

        cy += slot_h + CARD_GAP
        draw.line([(cx, cy), (cx + cw, cy)], fill=_hex_to_rgb(DIVIDER))
        cy += CARD_GAP

    # ── Season Badges ──
    season_badges = data.get("season_badges", [])
    if season_badges:
        draw.text((cx, cy), "赛季徽章", font=FONT_CAPTION, fill=MUTED)
        cy += FONT_SIZES["caption"] + 4

        per_row = 6
        badge_size = 36
        badge_gap = 6
        cols = min(len(season_badges), per_row)

        for ri in range((len(season_badges) + per_row - 1) // per_row):
            row_badges = season_badges[ri * per_row: (ri + 1) * per_row]
            for ci, b in enumerate(row_badges):
                bx = cx + ci * (badge_size + badge_gap)
                by = cy + ri * (badge_size + 4)
                badge_img = badge_imgs.get(b["season"])
                if badge_img:
                    img.paste(badge_img, (bx, by), badge_img)
                draw.text((bx, by + badge_size + 2),
                          f"S{b['season']}", font=FONT_SMALL, fill=MUTED)
            cy += badge_size + 4

        cy += FONT_SMALL_SIZE + CARD_GAP

    # ── Special Badges ──
    special_badges = data.get("special_badges", [])
    if special_badges:
        cy += 4
        for sb in special_badges:
            sbi = special_badge_imgs.get(sb["name"])
            if sbi:
                img.paste(sbi, (cx, cy), sbi)
                draw.text((cx + 40, cy + 6), sb["name"],
                          font=FONT_CAPTION, fill=ON_SURFACE)
                cy += 36 + 4

    # ── Footer ──
    bottom_y = card_y + card_h - PADDING - FONT_SIZES["small"]
    _draw_centered_text(
        draw, "Data: apexlegendsstatus.com", card_x, bottom_y,
        card_w, FONT_SMALL, fill=MUTED,
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _rank_div_label(div: int) -> str:
    mapping = {0: "IV", 1: "III", 2: "II", 3: "I"}
    return mapping.get(div, str(div))


FONT_SMALL_SIZE = FONT_SIZES["small"]


def _draw_small_legend_box(
    draw: ImageDraw.Draw, img: Image.Image,
    x: int, y: int, w: int, h: int,
    icon: Image.Image | None, name: str, kills: int, icon_size: int,
):
    nx, _ = _text_bbox(draw, name, FONT_CAPTION)
    kx, kh = _text_bbox(draw, f"{kills:,}", FONT_BODY)

    name_y = y + 4
    kills_y = name_y + FONT_SIZES["caption"]

    if icon:
        icon_y = name_y + (h - icon_size) // 2
        img.paste(icon, (x + 2, icon_y), icon)
        name_x = x + icon_size + 8
    else:
        name_x = x + 4

    draw.text((name_x, name_y), name, font=FONT_CAPTION, fill=MUTED)
    draw.text((name_x, kills_y), f"{kills:,}", font=FONT_BODY, fill=ON_SURFACE)


# ══════════════════════════════════════════
#  通用纯文本卡片（错误/提示）
# ══════════════════════════════════════════

async def draw_text_card(title: str, message: str, is_error: bool = False) -> bytes:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _draw_text_sync, title, message, is_error)


def _draw_text_sync(title: str, message: str, is_error: bool = False) -> bytes:
    w = BIND_CARD_W
    h = PADDING * 6 + FONT_SIZES["title"] + FONT_SIZES["body"] + CARD_GAP + 20

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    _draw_surface(draw, w, h)

    card_x, card_y = PADDING, PADDING
    card_w = w - PADDING * 2
    card_h = h - PADDING * 2

    _draw_shadow(draw, card_x, card_y, card_w, card_h)
    _draw_card_bg(draw, card_x, card_y, card_w, card_h)

    cx = card_x + PADDING
    cy = card_y + PADDING + 10

    title_color = PRIMARY if is_error else ACCENT_GREEN
    _draw_centered_text(draw, title, card_x, cy, card_w, FONT_TITLE, fill=title_color)
    cy += FONT_SIZES["title"] + CARD_GAP
    _draw_centered_text(draw, message, card_x, cy, card_w, FONT_BODY, fill=MUTED)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
