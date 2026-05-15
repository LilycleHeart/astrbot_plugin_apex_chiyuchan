"""Material Design 颜色常量、布局尺寸、字体加载"""

from __future__ import annotations

from pathlib import Path

# ── Material Design 配色 ──
SURFACE = "#0F1923"
CARD = "#1A2635"
PRIMARY = "#DA292A"
ON_SURFACE = "#FFFFFF"
MUTED = "#89A0B0"
DIVIDER = "#2A3A4A"
ACCENT_GREEN = "#4CE5B1"
ACCENT_BLUE = "#4DABF7"
SHADOW = "#060D14"

RANK_COLORS = {
    "Bronze": "#CD7F32",
    "Silver": "#C0C0C0",
    "Gold": "#FFD700",
    "Platinum": "#4ECDC4",
    "Diamond": "#74B9FF",
    "Master": "#A855F7",
    "Predator": "#DA292A",
    "Unranked": MUTED,
}
RANK_COLOR_FALLBACK = MUTED

PLATFORM_COLORS = {
    "PC": "#4DABF7",
    "PS4": "#4ECDC4",
    "X1": "#4CE5B1",
    "SWITCH": "#DA292A",
}

# ── 卡片布局尺寸 ──
PADDING = 24
RADIUS = 16
CARD_GAP = 16

STATS_CARD_W = 600
STATS_CARD_H = 520

MAP_CARD_W = 600
MAP_CARD_H = 480

MASTER_CARD_W = 640
MASTER_CARD_H = 560

TEAM_CARD_W = 500
TEAM_CARD_H = 280

BIND_CARD_W = 480
BIND_CARD_H = 200

PROFILE_CARD_W = 680
PROFILE_CARD_H = 860

# ── 字体 ──
FONT_PATHS = [
    str(Path(__file__).parent.parent / "assets" / "fonts" / "NotoSansSC-Regular.ttf"),
    str(Path(__file__).parent.parent / "assets" / "fonts" / "NotoSansSC-Bold.ttf"),
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
]

FONT_SIZES = {
    "title": 26,
    "subtitle": 18,
    "body": 15,
    "caption": 12,
    "metric": 28,
    "metric_label": 13,
    "small": 11,
}

def load_font(size: int, bold: bool = False) -> "ImageFont.FreeTypeFont":
    from PIL import ImageFont

    candidates = list(FONT_PATHS)
    if bold:
        bold_path = str(Path(__file__).parent.parent / "assets" / "fonts" / "NotoSansSC-Bold.ttf")
        candidates = [bold_path, "C:/Windows/Fonts/msyhbd.ttc"] + candidates

    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError, AttributeError):
            continue
    return ImageFont.load_default()


def get_rank_color(rank_name: str) -> str:
    raw = rank_name.split(" ")[0]
    return RANK_COLORS.get(raw, RANK_COLOR_FALLBACK)
