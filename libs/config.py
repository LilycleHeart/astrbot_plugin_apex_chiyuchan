"""Material Design 颜色常量 — 无 Pillow 依赖"""

from __future__ import annotations

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


def preload_fonts() -> None:
    """已废弃 — Playwright 渲染不再需要字体预加载"""
    pass


def get_rank_color(rank_name: str) -> str:
    raw = rank_name.split(" ")[0]
    return RANK_COLORS.get(raw, RANK_COLOR_FALLBACK)
