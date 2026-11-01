"""新版卡片的公共设计组件：Material 图标、数字字体、段位配色、段位进度。

所有卡片共用这里的设计规则，保证一套卡片看起来是一家人。
"""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

_FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

# ── Material Icons（Apache 2.0）24px 几何路径，统一用 currentColor 填充 ──
ICON_PATHS = {
    "trending_up": "M16 6l2.29 2.29-4.88 4.88-4-4L2 16.59 3.41 18l6-6 4 4 6.3-6.29L22 12V6z",
    "trending_down": "M16 18l2.29-2.29-4.88-4.88-4 4L2 7.41 3.41 6l6 6 4-4 6.3 6.29L22 12v6z",
    "trending_flat": "M22 12l-4-4v3H3v2h15v3z",
    "show_chart": "M3.5 18.49l6-6.01 4 4L22 6.92l-1.41-1.41-7.09 7.97-4-4L2 16.99z",
    "leaderboard": "M7.5 21H2V9h5.5v12zm7.25-18h-5.5v18h5.5V3zM22 11h-5.5v10H22V11z",
    "bar_chart": "M5 9.2h3V19H5zM10.6 5h2.8v14h-2.8zm5.6 8H19v6h-2.8z",
    "gps_fixed": (
        "M12 8c-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4-1.79-4-4-4zm8.94 3c-.46-4.17-3.77-7.48-7.94-7.94V1h-2v2.06"
        "C6.83 3.52 3.52 6.83 3.06 11H1v2h2.06c.46 4.17 3.77 7.48 7.94 7.94V23h2v-2.06c4.17-.46 7.48-3.77 7.94-7.94"
        "H23v-2h-2.06zM12 19c-3.87 0-7-3.13-7-7s3.13-7 7-7 7 3.13 7 7-3.13 7-7 7z"
    ),
    "bolt": (
        "M11 21h-1l1-7H7.5c-.58 0-.57-.32-.38-.66.19-.34.05-.08.07-.12C8.48 10.94 10.42 7.54 13 3h1l-1 7h3.5"
        "c.49 0 .56.33.47.51l-.07.15C12.96 17.55 11 21 11 21z"
    ),
    "emoji_events": (
        "M19 5h-2V3H7v2H5c-1.1 0-2 .9-2 2v1c0 2.55 1.92 4.63 4.39 4.94.63 1.5 1.98 2.63 3.61 2.96V19H7v2h10v-2h-4"
        "v-3.1c1.63-.33 2.98-1.46 3.61-2.96C19.08 12.63 21 10.55 21 8V7c0-1.1-.9-2-2-2zM5 8V7h2v3.82C5.84 10.4 5 9.3 5 8z"
        "m14 0c0 1.3-.84 2.4-2 2.82V7h2v1z"
    ),
    "star": "M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z",
    "group": (
        "M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3"
        "S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0"
        "c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z"
    ),
    "person": "M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z",
    "military_tech": (
        "M17 10.43V2H7v8.43c0 .35.18.68.49.86l4.18 2.51-.99 2.34-3.41.29 2.59 2.24L9.07 22 12 20.23 14.93 22"
        "l-.78-3.33 2.59-2.24-3.41-.29-.99-2.34 4.18-2.51c.3-.18.48-.5.48-.86zm-4 1.8l-1 .6-1-.6V3h2v9.23z"
    ),
    "workspace_premium": (
        "M9.68 13.69 12 11.93l2.31 1.76-.88-2.85L15.75 9h-2.84L12 6.19 11.09 9H8.25l2.31 1.84-.88 2.85zM20 10"
        "c0-4.42-3.58-8-8-8s-8 3.58-8 8c0 2.03.76 3.87 2 5.28V23l6-2 6 2v-7.72c1.24-1.41 2-3.25 2-5.28zm-8-6"
        "c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6 2.69-6 6-6zm0 15-4 1.02v-3.1c1.18.68 2.54 1.08 4 1.08"
        "s2.82-.4 4-1.08v3.1L12 19z"
    ),
    "history": (
        "M13 3c-4.97 0-9 4.03-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7"
        "c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42C8.27 19.99 10.51 21 13 21c4.97 0 9-4.03 9-9s-4.03-9-9-9zm-1 5v5"
        "l4.28 2.54.72-1.21-3.5-2.08V8H12z"
    ),
    "flag": "M14.4 6L14 4H5v17h2v-7h5.6l.4 2h7V6z",
    "schedule": (
        "M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58"
        "-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z"
    ),
    "check_circle": "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z",
    "warning": "M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z",
    "cancel": (
        "M12 2C6.47 2 2 6.47 2 12s4.47 10 10 10 10-4.47 10-10S17.53 2 12 2zm5 13.59L15.59 17 12 13.41 8.41 17 7 15.59"
        " 10.59 12 7 8.41 8.41 7 12 10.59 15.59 7 17 8.41 13.41 12 17 15.59z"
    ),
}


def icon(name: str, cls: str = "") -> str:
    """内联 SVG 图标，大小跟随字号（1em），颜色跟随文字颜色。"""
    d = ICON_PATHS.get(name)
    if not d:
        return ""
    extra = f" {cls}" if cls else ""
    return f'<svg class="ic{extra}" viewBox="0 0 24 24" aria-hidden="true"><path d="{d}"/></svg>'


@lru_cache(maxsize=1)
def font_face_css() -> str:
    """把数字字体内嵌成 base64，渲染时不依赖外网字体。"""
    faces = []
    for weight, filename in ((600, "BarlowCondensed-SemiBold.woff2"), (700, "BarlowCondensed-Bold.woff2")):
        path = _FONT_DIR / filename
        if not path.exists():
            continue
        data = base64.b64encode(path.read_bytes()).decode()
        faces.append(
            "@font-face{font-family:'Barlow Condensed';font-style:normal;"
            f"font-weight:{weight};font-display:block;"
            f"src:url(data:font/woff2;base64,{data}) format('woff2');}}"
        )
    return "\n".join(faces)


# ── 段位：中文名、暗色强调色、亮色强调色、高清徽章、铭牌（小段数字）位置 ──
_RANK_ASSET = "https://api.mozambiquehe.re/assets/ranks/{}.png"

TIERS = {
    "Rookie": {"zh": "菜鸟", "bright": "#A9B2BF", "deep": "#5B6472", "hd": "", "plate": 0},
    "Bronze": {"zh": "青铜", "bright": "#E39A62", "deep": "#9A5626", "hd": "bronze", "plate": 84},
    "Silver": {"zh": "白银", "bright": "#C9D3DF", "deep": "#5E6A7A", "hd": "silver", "plate": 84},
    "Gold": {"zh": "黄金", "bright": "#F4C552", "deep": "#9E7200", "hd": "gold", "plate": 84},
    "Platinum": {"zh": "白金", "bright": "#4FD6C7", "deep": "#0D8A80", "hd": "platinum", "plate": 84},
    "Diamond": {"zh": "钻石", "bright": "#62AFFF", "deep": "#1E66CC", "hd": "diamond", "plate": 79},
    "Master": {"zh": "大师", "bright": "#BC8BFF", "deep": "#7440D8", "hd": "master", "plate": 85},
    "Predator": {"zh": "猎杀", "bright": "#FF5D6C", "deep": "#C51F35", "hd": "apexpredator1", "plate": 85},
    "Unranked": {"zh": "未定级", "bright": "#A9B2BF", "deep": "#5B6472", "hd": "", "plate": 0},
}

TIER_ORDER = ("Rookie", "Bronze", "Silver", "Gold", "Platinum", "Diamond", "Master", "Predator")

# 进入每个大段所需 RP（EA 官方，2026-10 复核）
TIER_START = {
    "Rookie": 0, "Bronze": 1000, "Silver": 3000, "Gold": 5500,
    "Platinum": 8500, "Diamond": 12000, "Master": 16000,
}

# 各大段内 IV→I 每个小段的起点。和接口返回的小段不一致时只显示大段进度，不猜小段。
DIVISION_START = {
    "Rookie": (0, 250, 500, 750),
    "Bronze": (1000, 1500, 2000, 2500),
    "Silver": (3000, 3500, 4000, 4750),
    "Gold": (5500, 6250, 7000, 7750),
    "Platinum": (8500, 9250, 10000, 11000),
    "Diamond": (12000, 13000, 14000, 15000),
}

ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV"}


def normalize_tier(rank_name: str | None) -> str:
    """接口段位名 → 统一大段名（'Apex Predator' → 'Predator'）。"""
    text = (rank_name or "").strip().lower()
    if "predator" in text:
        return "Predator"
    for tier in TIER_ORDER:
        if text.startswith(tier.lower()):
            return tier
    return "Unranked"


def tier_style(tier: str) -> dict:
    return TIERS.get(tier, TIERS["Unranked"])


def hd_emblem(tier: str) -> str:
    slug = tier_style(tier)["hd"]
    return _RANK_ASSET.format(slug) if slug else ""


def fmt_int(n) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return "0"


def fmt_big(n) -> tuple[str, str]:
    """大数字缩写：≥10 万显示「361.5」+「万」，否则千分位。返回 (数字, 单位)。"""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "0", ""
    if abs(n) >= 100_000:
        return f"{n / 10_000:.1f}".rstrip("0").rstrip("."), "万"
    return f"{n:,}", ""


def rank_ladder(score: int, tier: str, div: int) -> dict | None:
    """当前大段内的进度条：小段刻度、填充比例、离下一级还差多少。

    大师 / 猎杀 / 未定级没有进度条，返回 None。
    """
    if tier not in DIVISION_START:
        return None
    next_tier = TIER_ORDER[TIER_ORDER.index(tier) + 1]
    start, end = TIER_START[tier], TIER_START[next_tier]
    bounds = list(DIVISION_START[tier]) + [end]
    score = max(start, min(int(score or 0), end))

    idx = 0
    for i in range(4):
        if bounds[i] <= score:
            idx = i
    computed_div = 4 - idx
    exact = computed_div == div

    span = end - start
    fill = (score - start) / span * 100
    zh = tier_style(tier)["zh"]
    if exact and computed_div > 1:
        target_name = f"{zh} {ROMAN[computed_div - 1]}"
        target = bounds[idx + 1]
    else:
        target_name = tier_style(next_tier)["zh"]
        target = end

    segments = []
    if exact:
        for i in range(4):
            segments.append({
                "label": ROMAN[4 - i],
                "left": (bounds[i] - start) / span * 100,
                "width": (bounds[i + 1] - bounds[i]) / span * 100,
                "current": i == idx,
                "done": i < idx,
            })
    return {
        "fill": round(fill, 2),
        "segments": segments,
        "start_fmt": fmt_int(start),
        "end_fmt": fmt_int(end),
        "end_name": tier_style(next_tier)["zh"],
        "target_name": target_name,
        "remaining_fmt": fmt_int(max(0, target - score)),
    }
