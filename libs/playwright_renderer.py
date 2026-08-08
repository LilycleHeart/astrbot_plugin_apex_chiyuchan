"""Playwright WebKit HTML → PNG 渲染器 — Material Design 战绩卡片"""

from __future__ import annotations

import base64
import io

from PIL import Image

from .config import RANK_COLORS
from .playwright_manager import run_with_page
from . import disk_cache

# ── MD3 深色主题配色 (默认: 钻石冰蓝) ──
_C_SURFACE = "#0F1218"
_C_CARD = "#171A22"
_C_CARD2 = "#1D222C"
_C_CARD3 = "#272D39"
_C_TEXT = "#DDE4F3"
_C_MUTED = "#BFC7DA"
_C_OUTLINE = "#444C5C"
_C_GOLD = "#E7C150"
_C_DIAMOND = "#5D9FF0"
_C_MASTER = "#C58BFF"
_C_PRED = "#DA292A"

_USE_LOCAL_FONTS = False

def set_use_local_fonts(val: bool):
    global _USE_LOCAL_FONTS
    _USE_LOCAL_FONTS = val

def _escape_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _beijing_theme() -> str:
    """根据配置返回主题：dark/light/auto(北京时间 06:00-18:00 亮色)"""
    from .playwright_manager import _COLOR_SCHEME
    if _COLOR_SCHEME == "light":
        return "light"
    if _COLOR_SCHEME == "dark":
        return ""
    # auto: 北京时间 06:00-18:00 亮色
    from datetime import datetime, timezone, timedelta
    hour = datetime.now(timezone(timedelta(hours=8))).hour
    return "light" if 6 <= hour < 18 else ""


def _parse_rank_name(rank_img: str) -> str:
    """从段位图URL提取段位名，如 ranks/diamond4.png → Diamond 4"""
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


# ── MD3 每段位动态深色主题 ──
_RANK_THEMES = {
    "Bronze": {
        "surface": "#14100D", "card": "#1E1712", "card2": "#261D17",
        "card3": "#33261D", "text": "#EDDECE", "muted": "#D4C2AD",
        "outline": "#55473A", "primary": "#FFB693",
    },
    "Silver": {
        "surface": "#101113", "card": "#18191C", "card2": "#1F2125",
        "card3": "#292C30", "text": "#E0E2E9", "muted": "#C2C5D0",
        "outline": "#464A52", "primary": "#B0C6D8",
    },
    "Gold": {
        "surface": "#13100A", "card": "#1D1710", "card2": "#251E13",
        "card3": "#32281A", "text": "#ECE0CE", "muted": "#D4C4AD",
        "outline": "#55442E", "primary": "#EAC14D",
    },
    "Platinum": {
        "surface": "#0E1213", "card": "#161B1D", "card2": "#1C2326",
        "card3": "#262E32", "text": "#DBE5E8", "muted": "#BEC9CE",
        "outline": "#434D52", "primary": "#64C3D3",
    },
    "Diamond": {
        "surface": "#0F1218", "card": "#171A22", "card2": "#1D222C",
        "card3": "#272D39", "text": "#DDE4F3", "muted": "#BFC7DA",
        "outline": "#444C5C", "primary": "#6DA8FF",
    },
    "Master": {
        "surface": "#131016", "card": "#1C1821", "card2": "#221E2A",
        "card3": "#2E2837", "text": "#EAE0F5", "muted": "#D2C3E3",
        "outline": "#544B60", "primary": "#B184FF",
    },
    "Predator": {
        "surface": "#160E0F", "card": "#221415", "card2": "#2A191B",
        "card3": "#392024", "text": "#F2DDDF", "muted": "#DCBFC2",
        "outline": "#614445", "primary": "#FF6B6B",
    },
    "Rookie": {
        "surface": "#101112", "card": "#18191C", "card2": "#1F2124",
        "card3": "#292B2F", "text": "#DFE2E8", "muted": "#C1C5CC",
        "outline": "#44474F", "primary": "#8D929E",
    },
    "Unranked": {
        "surface": "#101112", "card": "#18191C", "card2": "#1F2124",
        "card3": "#292B2F", "text": "#DFE2E8", "muted": "#C1C5CC",
        "outline": "#44474F", "primary": "#8D929E",
    },
}


def _theme_for_rank(rank_name: str) -> dict:
    """根据段位名返回 MD3 深色主题配色"""
    major = rank_name.split(" ")[0] if rank_name else "Unranked"
    return _RANK_THEMES.get(major, _RANK_THEMES["Rookie"])


# ── 汉化映射 ──
_RANK_ZH = {
    "Rookie": "菜鸟",
    "Bronze": "青铜",
    "Silver": "白银",
    "Gold": "黄金",
    "Platinum": "白金",
    "Diamond": "钻石",
    "Master": "大师",
    "Predator": "猎杀",
    "Unranked": "未定级",
}

_LEGEND_ZH = {
    "Wraith": "恶灵",
    "Horizon": "地平线",
    "Valkyrie": "瓦尔基里",
    "Pathfinder": "探路者",
    "Bloodhound": "寻血猎犬",
    "Gibraltar": "直布罗陀",
    "Lifeline": "命脉",
    "Mirage": "幻象",
    "Caustic": "侵蚀",
    "Octane": "动力小子",
    "Bangalore": "班加罗尔",
    "Wattson": "沃特森",
    "Crypto": "密客",
    "Revenant": "亡灵",
    "Loba": "罗芭",
    "Rampart": "兰伯特",
    "Fuse": "暴雷",
    "Seer": "先知",
    "Ash": "艾许",
    "Mad Maggie": "疯玛吉",
    "Newcastle": "纽卡斯尔",
    "Vantage": "万蒂奇",
    "Catalyst": "卡特莉丝",
    "Ballistic": "弹道",
    "Conduit": "导管",
    "Alter": "变幻",
}


def _rank_zh(name: str) -> str:
    major = name.split(" ")[0] if name else ""
    return _RANK_ZH.get(major, major)


def _rank_div_zh(div: int, rank_name: str = "") -> str:
    major = rank_name.split(" ")[0] if rank_name else ""
    if major in ("Master", "Predator"):
        return ""
    return str(div) if div > 0 else ""


def _legend_zh(name: str) -> str:
    return _LEGEND_ZH.get(name, name)


def _rank_color(name: str) -> str:
    return RANK_COLORS.get(name, _C_MUTED)


_TIER_COLORS_MAP = {
    "bronze": _C_GOLD,  # 沿用原卡配色
    "silver": "#c0c0c0",
    "gold": _C_GOLD,
    "platinum": RANK_COLORS.get("Platinum", "#4ECDC4"),
    "diamond": _C_DIAMOND,
    "master": _C_MASTER,
    "predator": _C_PRED,
}


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    if not h or len(h) < 6:
        return f"102,102,102,{alpha}"
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"{r},{g},{b},{alpha}"


def _roman(n: int) -> str:
    if n <= 0:
        return "?"
    return ["", "I", "II", "III", "IV"][min(n, 4)]


def _build_rank_dist(
    player_rank: str, player_top_pct: float, rank_dist_entries: list = None, *, theme: dict = None
) -> str:
    """段位分布 — 仅显示玩家所在段位附近4个段位，含人数（返回 HTML）"""
    card3 = theme["card3"] if theme else _C_CARD3
    muted = theme["muted"] if theme else _C_MUTED
    if rank_dist_entries:
        tiers = [(e.name, e.pct, e.color, e.count) for e in rank_dist_entries]
    else:
        tiers = [
            ("Rookie", 2.40, "#484852", 0),
            ("Bronze", 12.98, "#cd7f32", 0),
            ("Silver", 27.59, "#c0c0c0", 0),
            ("Gold", 35.54, "#ffd700", 0),
            ("Platinum", 17.72, "#4ECDC4", 0),
            ("Diamond", 3.36, "#358de6", 0),
            ("Master", 0.09, "#9f35e6", 0),
            ("Predator", 0.32, "#e31b39", 0),
        ]

    player_tier = player_rank.split(" ")[0] if player_rank else ""
    player_idx = next(
        (i for i, t in enumerate(tiers) if t[0].lower() == player_tier.lower()), 0
    )

    # 取玩家附近4个段位
    start = max(0, player_idx - 1)
    end = min(len(tiers), start + 4)
    if end - start < 4:
        start = max(0, end - 4)
    visible = tiers[start:end]

    total_players = sum(t[3] for t in tiers if t[3])
    bars = ""
    for name, pct, color, count in visible:
        is_player = name.lower() == player_tier.lower()
        weight = "font-weight:700;" if is_player else ""
        arrow = (
            '<span style="font-size:12px;color:{color};{weight}">◀</span>'.format(
                color=color, weight=weight
            )
            if is_player
            else ""
        )
        bar_pct = min(pct, 50)
        count_str = f"{count:,}" if count else ""
        name_zh = _rank_zh(name)
        bars += (
            f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;padding:2px 24px;'
            f'{"background:rgba(149,83,211,0.06);border-radius:8px;" if is_player else ""}">'
            f'<span style="width:50px;text-align:right;font-size:12px;color:{color};{weight}">{name_zh}</span>'
            f"{arrow}"
            f'<div style="flex:1;height:6px;background:{card3};border-radius:3px;overflow:hidden;">'
            f'<div style="height:100%;width:{bar_pct}%;background:{color};border-radius:3px;{"box-shadow:0 0 8px " + color if is_player else ""}"></div>'
            f"</div>"
            f'<span style="width:44px;font-size:11px;text-align:right;color:{muted};{weight}">{pct:.2f}%</span>'
            f'<span style="width:64px;font-size:11px;text-align:right;color:{muted};">{count_str}</span>'
            f"</div>"
        )
    footer = f'<div style="padding:4px 24px 8px;font-size:11px;color:{muted};text-align:center;">'
    if total_players:
        footer += f"全服 {total_players:,} 名玩家中，Top {player_top_pct}%"
    else:
        footer += f"全服玩家中，Top {player_top_pct}%"
    footer += "</div>"
    return bars + footer


def _build_rank_dist_list(
    player_rank: str, player_top_pct: float, rank_dist_entries: list = None, *, theme: dict = None
) -> list[dict]:
    """段位分布 — 返回 list[dict] 供 Jinja 模板渲染（全8段位显示，高亮当前段位）"""
    # 默认全8段位
    default_ranks = [
        ("Rookie", 2.40, "#484852", 0),
        ("Bronze", 12.98, "#cd7f32", 0),
        ("Silver", 27.59, "#c0c0c0", 0),
        ("Gold", 35.54, "#ffd700", 0),
        ("Platinum", 17.72, "#4ECDC4", 0),
        ("Diamond", 3.36, "#358de6", 0),
        ("Master", 0.09, "#9f35e6", 0),
        ("Predator", 0.32, "#e31b39", 0),
    ]

    if rank_dist_entries:
        # 用 API 数据覆盖默认值，但保证全8段位都在
        api_map = {e.name: (e.name, e.pct, e.color, e.count) for e in rank_dist_entries}
        tiers = []
        for default in default_ranks:
            tiers.append(api_map.get(default[0], default))
    else:
        tiers = default_ranks

    player_tier = player_rank.split(" ")[0] if player_rank else ""

    result = []
    for name, pct, color, count in tiers:
        is_player = name.lower() == player_tier.lower()
        # 精简显示: 0→0, 20→20, 521→521, 1660→1.7k, 16600→17k
        if count == 0:
            count_fmt = "0"
        elif count < 1000:
            count_fmt = str(count)
        elif count < 10000:
            count_fmt = f"{count/1000:.1f}k"
        else:
            count_fmt = f"{count/1000:.0f}k"
        result.append({
            "name": _rank_zh(name),
            "pct": min(pct, 50),
            "pct_display": f"{pct:.2f}",
            "color": color,
            "count_fmt": count_fmt,
            "is_player": is_player,
        })
    return result


# ── Apex 排位分段门槛（进入该档位所需最低 RP）──
# 2024 年排位改版后的官方分档（2026-08 官方 API/ALS 实测验证）：
# Rookie 0 · Bronze 1000 · Silver 3000 · Gold 5500 · Platinum 8500 · Diamond 12000 · Master/Predator 16000
# （Master 与 Predator 同为 16000 起步，猎杀 = 大师中全服前 750 名）
_TIER_STEPS = (
    (0, "rookie4"),
    (1000, "bronze4"),
    (3000, "silver4"),
    (5500, "gold4"),
    (8500, "platinum4"),
    (12000, "diamond4"),
    (16000, "master"),
)
_TIER_ICON_BASE = "https://api.mozambiquehe.re/assets/ranks/{}.png"


def _tier_index_for_score(score: int) -> int:
    """返回 score 所处的档位序号（_TIER_STEPS 下标），未定级返回 -1"""
    idx = -1
    for i, (thr, _) in enumerate(_TIER_STEPS):
        if score >= thr:
            idx = i
        else:
            break
    return idx


def _build_rp_chart_html(entries: list) -> str:
    """RP 历史折线图（SVG，区域渐变 + 首尾标注）。数据不足 2 条返回空串。

    entries: [{score, at}] 按时间正序，at 为 "YYYY-MM-DD HH:MM:SS"
    """
    entries = entries or []
    pts = [
        (e.get("score"), e.get("at", ""))
        for e in entries
        if isinstance(e, dict) and e.get("score") is not None
    ]
    if len(pts) < 2:
        return ""
    import math
    scores = [p[0] for p in pts]
    dates = [p[1] for p in pts]
    n = len(pts)

    # SVG 内部 pad_l 预留 36px 作为 y 轴刻度区（刻度文字左缘与全局 28px 边距统一）
    W, H = 664, 150
    pad_l, pad_r, pad_t, pad_b = 36, 6, 26, 24
    plot_w = W - pad_l - pad_r
    plot_h = H - pad_t - pad_b
    base_y = pad_t + plot_h
    # Y 轴边界整数化：下界向下取整、上界向上取整到刻度步长整数倍，
    # 折线不贴边、刻度覆盖完整范围
    def _nice_step(lo, hi, count=4):
        raw = ((hi - lo) or 1) / count
        mag = 10 ** math.floor(math.log10(raw))
        norm = raw / mag
        return (next(n for n in (1, 2, 2.5, 5, 10) if norm <= n)) * mag

    step = _nice_step(min(scores), max(scores))
    lo = math.floor(min(scores) / step) * step
    hi = math.ceil(max(scores) / step) * step
    if hi - lo < step:  # 防止全同值
        hi = lo + step
    span = hi - lo

    xs = [pad_l + i * plot_w / (n - 1) for i in range(n)]
    ys = [pad_t + (hi - s) / span * plot_h for s in scores]

    # Y 轴刻度：横向网格线 + 刻度文字（SVG 内联，随图表缩放天然对齐）
    grid_lines = ""
    tv = lo
    while tv <= hi + 1e-9:
        frac = (tv - lo) / span
        gy = pad_t + (1 - frac) * plot_h
        grid_lines += (
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{W - pad_r}" y2="{gy:.1f}" '
            f'stroke="var(--outline-v)" stroke-width="1"/>'
            f'<text x="{pad_l - 6}" y="{gy + 3:.1f}" text-anchor="end" font-size="9" '
            f'fill="var(--on-sv)" font-variant-numeric="tabular-nums">{tv:,.0f}</text>'
        )
        tv += step

    line_d = " M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in zip(xs, ys))
    area_d = f"{line_d} L{xs[-1]:.1f} {base_y:.1f} L{xs[0]:.1f} {base_y:.1f} Z"

    # 段位分档线：显示在 [lo, hi] 内的门槛，虚线 + 档位名；大师线以上用深一档颜色
    tier_colors = {
        "bronze4": "#CD7F32", "silver4": "#C0C0C0", "gold4": "#FFD700",
        "platinum4": "#4ECDC4", "diamond4": "#358DE6", "master": "#9F35E6",
    }
    tier_lines = ""
    for thr, name in _TIER_STEPS:
        if not (lo < thr <= hi):
            continue
        ty = pad_t + (1 - (thr - lo) / span) * plot_h
        col = tier_colors.get(name, "var(--on-sv)")
        major = _rank_zh(name[:-1].capitalize() if name != "master" else "Master")
        tier_lines += (
            f'<line x1="{pad_l}" y1="{ty:.1f}" x2="{W - pad_r}" y2="{ty:.1f}" '
            f'stroke="{col}" stroke-opacity="0.55" stroke-width="1" stroke-dasharray="4 3"/>'
            f'<text x="{W - pad_r - 4}" y="{ty - 3:.1f}" text-anchor="end" font-size="9" '
            f'fill="{col}" font-weight="600" opacity="0.85">{major}</text>'
        )
    # 升档时刻：首次达到比历史最高档位更高的档位时，在该点上方显示段位图标
    # （跳过 Rookie 起步档；只显示"升到新高"的时刻，降档/回档不显示）
    peak_idx = -1
    icons = ""
    for i, s in enumerate(scores):
        idx = _tier_index_for_score(s)
        if idx > 0 and idx > peak_idx:
            name = _TIER_STEPS[idx][1]
            ic = 26
            ix = xs[i] - ic / 2
            iy = ys[i] - ic - 6
            if ix < pad_l:
                ix = pad_l
            if iy < 2:
                iy = ys[i] + 6
            icons += (
                f'<img src="{_TIER_ICON_BASE.format(name)}" width="{ic}" height="{ic}" '
                f'style="position:absolute;left:{ix:.1f}px;top:{iy:.1f}px;border-radius:6px;'
                f'background:var(--sc-low);padding:1px;'
                f'box-shadow:0 1px 4px rgba(0,0,0,0.25);" '
                f'loading="eager" decoding="async"/>'
            )
        if idx > peak_idx:
            peak_idx = idx

    # 首点数值标签：贴顶时改放点下方，避免溢出
    lbl0_y = ys[0] - 8 if ys[0] - 8 >= 14 else ys[0] + 16
    lbl1_y = ys[-1] - 10 if ys[-1] - 10 >= 14 else ys[-1] + 16

    # X 轴：每个数据点下方标日期（MM-DD）；点数多时隔点显示防重叠
    # 首点用 start 锚点（文字向右展开）、末点用 end 锚点（文字向左展开），防止贴边裁切
    x_labels = ""
    for i, d in enumerate(dates):
        if n > 8 and i % 2 == 1 and i != n - 1:
            continue  # 密集时只标偶数位点
        xl = f"{d[5:10]}" if len(d) >= 10 else ""
        anchor = "start" if i == 0 else ("end" if i == n - 1 else "middle")
        x_labels += (
            f'<text x="{xs[i]:.1f}" y="{H - 4}" text-anchor="{anchor}" font-size="9" '
            f'fill="var(--on-sv)" opacity="0.75" font-variant-numeric="tabular-nums">{xl}</text>'
        )

    svg = (
        f'<svg class="rp-chart" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">'
        "<defs>"
        '<linearGradient id="rp-fill" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0%" stop-color="var(--p)" stop-opacity="0.28"/>'
        '<stop offset="100%" stop-color="var(--p)" stop-opacity="0"/>'
        "</linearGradient>"
        "</defs>"
        f"{grid_lines}"
        f"{tier_lines}"
        f'<path d="{area_d}" fill="url(#rp-fill)"/>'
        f'<path d="{line_d}" fill="none" stroke="var(--p)" stroke-width="2" '
        'stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{xs[0]:.1f}" cy="{ys[0]:.1f}" r="3" fill="var(--p)"/>'
        f'<circle cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="4.5" fill="var(--p)" '
        'stroke="var(--sc-low)" stroke-width="2"/>'
        f'<text x="{xs[0]:.1f}" y="{lbl0_y:.1f}" text-anchor="start" font-size="11" '
        f'fill="var(--on-sv)" font-variant-numeric="tabular-nums">{scores[0]:,}</text>'
        f'<text x="{xs[-1]:.1f}" y="{lbl1_y:.1f}" text-anchor="end" font-size="12" '
        f'font-weight="700" fill="var(--p-text)" font-variant-numeric="tabular-nums">{scores[-1]:,}</text>'
        f"{x_labels}"
        "</svg>"
    )

    # 升档图标为 HTML 层（绝对定位叠加在 SVG 上，随 _embed_images 一并内嵌）
    icon_layer = (
        f'<div style="position:relative;">{svg}{icons}</div>'
        if icons
        else svg
    )

    plot_wrap = icon_layer

    # 24 小时内涨幅徽章：最后两个数据点间隔 ≤ 24h 时显示其差值
    # （超过一天没查询则不显示，避免误导）
    trend_html = ""
    if n >= 2:
        from datetime import datetime as _dt

        def _parse(s: str):
            try:
                return _dt.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                return None

        t0, t1 = _parse(dates[-2]), _parse(dates[-1])
        if t0 and t1 and (t1 - t0).total_seconds() <= 24 * 3600 and scores[-1] != scores[-2]:
            diff = scores[-1] - scores[-2]
            sign = "+" if diff > 0 else ""
            cls = "rp-up" if diff > 0 else "rp-down"
            arrow = "▲" if diff > 0 else "▼"
            trend_html = (
                f'<span class="{cls}" style="font-size:11px;font-weight:700;">'
                f"{arrow} {sign}{diff:,} · 24h</span>"
            )

    return (
        '<div class="rp-chart-strip">'
        '<div class="rp-chart-head">'
        '<span class="col-title">RP 历史</span>'
        f"{trend_html}"
        "</div>"
        f"{plot_wrap}"
        "</div>"
    )


def _build_stats_html(**d) -> str:
    """根据数据 dict 构建 MD3 Jinja2 战绩卡片 HTML"""
    name = d.get("name", "Unknown")
    tag = d.get("tag", "")
    alias = d.get("alias", "")
    uid = d.get("uid", "")
    avatar_url = d.get("avatar_url", "")
    platform = d.get("platform", "PC")
    online = d.get("online", d.get("online_status", "offline"))
    level = d.get("level", 0)
    level_pct = d.get("level_pct", d.get("to_next_level_pct", 0))
    prestige = d.get("prestige", 0)
    level_icon = d.get("level_icon", "")
    level_raw = d.get("level_raw", level)
    rank_name = d.get("rank_name", "Unranked")
    rank_div = d.get("rank_div", 0)
    rank_score = d.get("rank_score", 0)
    rank_img = d.get("rank_img", d.get("rank_icon_url", ""))
    rank_top_pct = d.get("rank_top_pct", 0)
    rank_top_pct_global = d.get("rank_top_pct_global", rank_top_pct)
    rank_ladder_pos = d.get("rank_ladder_pos", 0)
    rp_delta = d.get("rp_delta")
    rp_history = d.get("rp_history") or []
    kills = d.get("kills", 0)
    damage = d.get("damage", 0)
    wins = d.get("wins", 0)
    top_legends = d.get("top_legends", [])
    season_badges = d.get("season_badges", [])
    special_badges = d.get("special_badges", [])
    selected_legend = d.get("selected_legend")
    rank_dist_entries = d.get("rank_dist_entries", None)

    # ── 段位主题色 ──
    theme = _theme_for_rank(rank_name)
    # MD3 亮色主题：primary 用 Tone 40 等效（比暗色 Tone 80 更深）
    light_theme = {
        "primary": theme["primary"],
        "surface": "#F8FAFF",
        "card": "#FFFFFF",
        "card2": "#F0F3F8",
        "card3": "#E1E5EC",
        "text": "#11161F",
        "muted": "#44474F",
        "outline": "#BCC3D0",
    }

    _p = {"PC": "PC", "PS4": "PS", "PS5": "PS", "X1": "Xbox", "XBX": "Xbox"}.get(platform.upper(), platform.upper())
    top_pct_label = "全平台" if rank_name.startswith(("Predator", "Master")) else _p

    display_name = f"{name} [{tag}]" if tag else name
    online_map = {"online": "在线", "offline": "离线", "in_game": "游戏中"}
    state_text = online_map.get(online, online)
    state_dot = "#4CE5B1" if online in ("online", "in_game") else "#555"

    rank_c = _rank_color(rank_name)
    top_global = f"{rank_top_pct_global}%"

    rp_delta_html = ""
    if rp_delta is not None:
        sign = "+" if rp_delta >= 0 else ""
        delta_cls = "rp-up" if rp_delta >= 0 else "rp-down"
        rp_delta_html = f'<span class="{delta_cls}" style="font-size:13px;margin-left:8px;">{sign}{rp_delta} RP</span>'

    rank_display = _rank_zh(rank_name) + _rank_div_zh(rank_div, rank_name)
    if rank_ladder_pos and rank_name.startswith(("Predator", "Master")):
        rank_display += f" #{rank_ladder_pos}"

    # ── 徽章 ──
    season_badges_ctx = []
    for b in season_badges:
        color = b.get("color") or "#666"
        season_badges_ctx.append({
            "badge_url": b.get("badge_url", ""),
            "season": b.get("season", ""),
            "color": color,
            "bg": f"rgba({_hex_to_rgba(color, 0.15)})",
            "border": f"rgba({_hex_to_rgba(color, 0.3)})",
        })

    special_badges_ctx = [{"badge_url": b.get("badge_url", "")} for b in special_badges if b.get("badge_url")]

    # ── 英雄排行 ──
    legends_ctx = []
    for leg in top_legends[:4]:
        legends_ctx.append({
            "icon_url": leg.get("icon_url", "") or leg.get("icon", ""),
            "name_zh": _legend_zh(leg["name"]),
            "kills_fmt": f"{leg.get('kills', 0):,}",
        })

    # ── 当前选用 ──
    selected_ctx = None
    if selected_legend:
        ss = selected_legend.get("stats", [])
        selected_ctx = {
            "icon_url": selected_legend.get("icon_url", ""),
            "name_zh": _legend_zh(selected_legend.get("name", "")),
            "stats": [{"name": s.get("name", ""), "value": s.get("value", "")} for s in ss],
        }

    # ── 段位分布 ──
    rank_dist_ctx = _build_rank_dist_list(rank_name, rank_top_pct_global, rank_dist_entries, theme=theme)

    # ── RP 历史折线图 ──
    rp_chart_html = _build_rp_chart_html(rp_history)

    context = {
        "theme": theme,
        "light_theme": light_theme,
        "theme_class": _beijing_theme(),
        "avatar_url": avatar_url,
        "display_name": display_name,
        "alias": alias,
        "uid": uid,
        "platform": platform,
        "state_text": state_text,
        "state_dot": state_dot,
        "rank_img": rank_img,
        "rank_display": rank_display,
        "rank_score_fmt": f"{rank_score:,}",
        "rp_delta_html": rp_delta_html,
        "top_global": top_global,
        "top_pct_label": top_pct_label,
        "level_icon": level_icon,
        "level": level,
        "level_pct": level_pct,
        "kills_fmt": f"{kills:,}",
        "damage_fmt": f"{damage:,}",
        "wins_fmt": f"{wins:,}" if wins else "0",
        "selected_legend": selected_ctx,
        "rank_dist": rank_dist_ctx,
        "rp_chart_html": rp_chart_html,
        "top_legends": legends_ctx,
        "season_badges": season_badges_ctx,
        "special_badges": special_badges_ctx,
    }
    return _get_jinja_template("stats.html.jinja").render(**context)


# ══════════════════════════════════════════
#  Moe Counter 数字 → Base64 (rule34)
# ══════════════════════════════════════════


def _render_moe_number_base64(number: int) -> str:
    import base64
    from .image_renderer import _moe_digit_frames, _load_moe_digits

    _load_moe_digits()
    digits = str(number)
    if not _moe_digit_frames:
        return ""

    scale = 100 / 100.0
    dw = int(45 * scale)
    total_w = dw * len(digits)
    total_h = 100

    canvas = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
    x = 0
    for ch in digits:
        frames = _moe_digit_frames.get(ch, [])
        if not frames:
            continue
        frame = frames[0]
        resized = frame.resize((dw, total_h), Image.LANCZOS)
        canvas.paste(resized, (x, 0), resized)
        x += dw

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _render_moe_digits_list(number: int) -> list[str]:
    """Render each digit as individual base64 data URIs (Moe Counter style).
    Auto-crops transparent padding and centers each digit consistently."""
    from .image_renderer import _moe_digit_frames, _load_moe_digits

    _load_moe_digits()
    digits = str(number)
    if not _moe_digit_frames:
        return []

    scale = 100 / 100.0
    dw = int(45 * scale)
    total_h = 100
    result = []
    for ch in digits:
        frames = _moe_digit_frames.get(ch, [])
        if not frames:
            continue
        frame = frames[0]
        resized = frame.resize((dw, total_h), Image.LANCZOS)
        # 自动裁剪透明边缘，然后垂直居中到统一画布
        bbox = resized.getbbox()
        if bbox and bbox[3] - bbox[1] > 0 and bbox[2] - bbox[0] > 0:
            cropped = resized.crop(bbox)
            cw, ch = cropped.size
            # 垂直居中
            cy = (total_h - ch) // 2
            canvas = Image.new("RGBA", (dw, total_h), (0, 0, 0, 0))
            canvas.paste(cropped, ((dw - cw) // 2, cy), cropped)
        else:
            canvas = Image.new("RGBA", (dw, total_h), (0, 0, 0, 0))
        buf = io.BytesIO()
        canvas.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        result.append(f"data:image/png;base64,{b64}")
    return result


# ══════════════════════════════════════════
#  公开接口
# ══════════════════════════════════════════
#  图片缓存 — 远程URL转base64，零网络渲染
# ══════════════════════════════════════════

import asyncio
import re
from functools import lru_cache as _unused_lru_cache  # kept for reference only

_MIME_MAP = {
    b'\x89PNG': 'image/png',
    b'\xff\xd8\xff': 'image/jpeg',
    b'GIF8': 'image/gif',
    b'RIFF': 'image/webp',
    b'<svg': 'image/svg+xml',
    b'<?xml': 'image/svg+xml',
}

async def _download_and_cache(url: str) -> str | None:
    """异步下载图片转base64，优先从磁盘缓存加载"""
    import httpx
    
    # 尝试从磁盘缓存获取
    try:
        cached_data = await disk_cache.get(url)
        if cached_data:
            stripped = cached_data.lstrip()
            mime = 'image/png'
            for prefix, m in _MIME_MAP.items():
                if stripped[:4].startswith(prefix) or stripped[:5].startswith(prefix):
                    mime = m
                    break
            b64 = base64.b64encode(cached_data).decode()
            return f"data:{mime};base64,{b64}"
    except Exception:
        pass
    
    # 缓存未命中，从网络下载
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Referer": "https://apexlegendsstatus.com/",
            "Accept": "image/svg+xml,image/png,image/*,*/*;q=0.8",
        }
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=headers) as c:
            r = await c.get(url)
            r.raise_for_status()
            raw = r.content
            if not raw:
                return None
            
            # 写入磁盘缓存（永久保存）
            try:
                await disk_cache.set(url, raw)
            except Exception:
                pass
            
            stripped = raw.lstrip()
            mime = 'image/png'
            for prefix, m in _MIME_MAP.items():
                if stripped[:4].startswith(prefix) or stripped[:5].startswith(prefix):
                    mime = m
                    break
            b64 = base64.b64encode(raw).decode()
            return f"data:{mime};base64,{b64}"
    except Exception as e:
        from astrbot.api import logger
        logger.warning(f"[Renderer] 下载失败 {url[:80]}: {e}")
        return None


async def _embed_images(html: str) -> str:
    """将远程图片URL替换为base64 data URI（使用磁盘缓存）"""
    urls = set()
    urls.update(re.findall(r'src="(https?://[^"]+)"', html))
    urls.update(re.findall(r'url\((https?://[^)]+)\)', html))

    if not urls:
        return html

    # 并发下载所有图片（磁盘缓存会自动处理缓存命中）
    async def _fetch(url):
        b64 = await _download_and_cache(url)
        return url, b64

    results = await asyncio.gather(*[_fetch(u) for u in urls], return_exceptions=True)
    
    # 构建替换映射
    replacements = {}
    for result in results:
        if isinstance(result, Exception):
            continue
        url, b64 = result
        if b64:
            replacements[url] = b64

    # 执行替换
    def _replace(m):
        url = m.group(1)
        return m.group(0).replace(url, replacements.get(url, url))

    html = re.sub(r'src="(https?://[^"]+)"', _replace, html)
    html = re.sub(r'url\((https?://[^)]+)\)', _replace, html)
    return html


async def _render_card_sync(html: str, width: int) -> bytes:
    html = await _embed_images(html)
    async with run_with_page(viewport={"width": width, "height": 100}, device_scale_factor=3) as page:
        await page.set_content(html, wait_until="load", timeout=20000)
        await page.wait_for_selector(".card, .lfg-list", timeout=10000)
        try:
            await page.wait_for_function("() => document.fonts.ready", timeout=8000)
        except Exception:
            pass
        card = await page.query_selector(".card, .lfg-list")
        if card:
            return await card.screenshot(type="png", omit_background=True)
        return await page.screenshot(full_page=False, type="png")


async def draw_profile_card(data: dict) -> bytes:
    """根据 dict 渲染战绩卡片 PNG（playwright WebKit）"""
    html = _build_stats_html(**data)
    return await _render_card_sync(html, 720)


# ══════════════════════════════════════════
#  服务器状态卡片
# ══════════════════════════════════════════


# ALS 服务区块名汉化映射
_ALS_SECTION_NAMES = {
    "Crossplay auth (any platform)": "跨平台认证",
    "Lobby/Matchmaking servers": "大厅/匹配服务器",
    "PC/Desktop logins": "PC 登录",
    "Player accounts": "玩家账户",
    "ALS website": "ALS 网站",
    "PSN/Xbox Live status": "PSN/Xbox Live 状态",
}

# ALS 状态汉化
_ALS_STATUS_TEXT = {
    "UNSTABLE": "不稳定",
    "UP": "正常",
    "RUNNING": "正常",
    "SLOW": "缓慢",
    "DOWN": "宕机",
    "UNSTABLE / SLOW": "不稳定 / 缓慢",
    "MOSTLY OPERATIONAL": "正常",
    "OPERATIONAL": "正常",
}


def _locale_status(status: str) -> str:
    return _ALS_STATUS_TEXT.get(status.strip().upper(), status) if status else status


def _locale_section_name(name: str) -> str:
    return _ALS_SECTION_NAMES.get(name.strip(), name)


# ── Region name → flag icon code mapping ──
_REGION_FLAGS = {
    # ALS broad region names
    "eu west": "ie", "eu east": "de", "us west": "us", "us central": "us",
    "us east": "us", "south america": "br", "asia": "jp",
    # City names
    "tokyo": "jp", "london": "gb", "dallas": "us", "frankfurt": "de",
    "singapore": "sg", "sydney": "au", "são paulo": "br", "salt lake city": "us",
    "oregon": "us", "bahrain": "bh", "hong kong": "hk", "miami": "us",
    "vancouver": "ca", "taipei": "tw", "seoul": "kr", "chile": "cl",
    "peru": "pe", "mumbai": "in", "south africa": "za", "japan": "jp",
    "iowa": "us", "ohio": "us", "netherlands": "nl", "paris": "fr",
    "madrid": "es", "milan": "it", "stockholm": "se", "warsaw": "pl",
    "vienna": "at", "prague": "cz", "dubai": "ae", "istanbul": "tr",
    "moskow": "ru", "moscow": "ru", "india": "in", "jakarta": "id",
    "bangkok": "th", "osaka": "jp", "kansas city": "us", "atlanta": "us",
    "seattle": "us", "los angeles": "us", "new york": "us", "chicago": "us",
    "san jose": "us", "ashburn": "us",
}


def _region_flag(entry_name: str) -> str:
    """Guess flag code from region / datacenter name (ALS entry name)."""
    name_lower = entry_name.strip().lower()
    if name_lower in _REGION_FLAGS:
        return _REGION_FLAGS[name_lower]
    first_word = name_lower.split()[0] if name_lower else ""
    if first_word in _REGION_FLAGS:
        return _REGION_FLAGS[first_word]
    return ""


def _flag_emoji(code: str) -> str:
    """Convert 2-letter country code to emoji flag (e.g. 'JP' → '🇯🇵')."""
    if not code or len(code) != 2:
        return ""
    return chr(0x1F1E6 + ord(code[0].upper()) - ord("A")) + chr(0x1F1E6 + ord(code[1].upper()) - ord("A"))


def _latency_color(response_time: str) -> str:
    """Classify latency from response_time string like '72 ms', '100% up'."""
    import re
    # "100% up" means uptime percentage, not latency — always good
    if "%" in response_time and "up" in response_time.lower():
        return "good"
    m = re.search(r"(\d+)\s*ms", response_time)
    if m:
        ms = int(m.group(1))
        if ms < 100:
            return "good"
        elif ms < 300:
            return "medium"
        else:
            return "high"
    return "good" if "up" in response_time.lower() else "medium"


def _status_class_dot(status: str) -> str:
    """Map ALS status string to template CSS class (running/degraded/down)."""
    s = status.upper()
    if "DOWN" in s:
        return "down"
    if "UNSTABLE" in s or "SLOW" in s:
        return "degraded"
    return "running"


def _build_server_status_html(server_status) -> str:
    als = getattr(server_status, "als", None)
    services = []

    if als and als.sections:
        # Compute overall status across all sections
        any_down = any("down" in sec.status.lower() for sec in als.sections)
        any_unstable = any(
            "unstable" in sec.status.lower() or "slow" in sec.status.lower()
            for sec in als.sections
        )
        if any_down:
            overall_class = "down"
            overall_text = "部分服务宕机"
        elif any_unstable:
            overall_class = "degraded"
            overall_text = "部分服务异常"
        else:
            overall_class = "running"
            overall_text = "全部服务正常运行"

        for sec in als.sections:
            regions = []
            for entry in sec.entries:
                flag_cls = getattr(entry, "flag_class", "") or _region_flag(entry.name)
                regions.append({
                    "flag_class": flag_cls,
                    "name": _escape_html(entry.name),
                    "state_class": _status_class_dot(entry.status),
                    "state": _escape_html(_locale_status(entry.status)),
                    "latency_color": _latency_color(entry.response_time),
                    "detail": _escape_html(entry.response_time),
                })

            services.append({
                "name": _escape_html(_locale_section_name(sec.name)),
                "status_class": _status_class_dot(sec.status),
                "regions": regions,
            })
    else:
        overall_class = "running"
        overall_text = "全部服务正常运行"

    context = {
        "theme": _beijing_theme(),
        "overall_class": overall_class,
        "overall_text": overall_text,
        "services": services,
    }
    return _get_jinja_template("server_status.html.jinja").render(**context)


async def draw_server_status_card(server_status) -> bytes:
    html = _build_server_status_html(server_status)
    return await _render_card_sync(html, 720)


# ══════════════════════════════════════════
#  地图轮换卡片
# ══════════════════════════════════════════

_MAP_BASE = "https://apexlegendsstatus.com/assets/maps"

# LTM/特殊地图名→ALS文件名映射
_MAP_VARIANTS = {
    "Skulltown": "Arena_Skulltown",
    "Skull Town": "Arena_Skulltown",
    "Autumn Estates": "Arena_Autumn_Estates",
    "Monument": "Worlds_Edge",
    "Siphon": "Kings_Canyon",
    "Caustic Treatment": "No_Map_Data",
    "Estates": "Arena_Autumn_Estates",
    "Phase Runner": "Arena_Phase_Runner",
    "Overflow": "Arena_Overflow",
    "Habitat": "Arena_Habitat",
    "Encore": "Arena_Encore",
    "Party Crasher": "Arena_Party_Crasher",
    "Drop-Off": "Arena_Drop_Off",
    "Zeus Station": "No_Map_Data",
    "Wattson's Pylon": "No_Map_Data",
    "Barometer": "No_Map_Data",
}


def _map_url(map_name: str) -> str:
    """根据地图名生成ALS地图图片URL"""
    if not map_name:
        return ""
    # 优先查变体映射
    slug = _MAP_VARIANTS.get(map_name)
    if not slug:
        slug = map_name.replace("'", "").replace(" ", "_")
    return f"{_MAP_BASE}/{slug}.png"


_MAP_ZH = {
    # 大逃杀地图 (官方简中)
    "Kings Canyon": "诸王峡谷",
    "World's Edge": "世界尽头",
    "Olympus": "奥林匹斯",
    "Storm Point": "风暴点",
    "Broken Moon": "残月",
    "E-District": "电流区",
    # LTM / 竞技场
    "Fragment": "碎片",
    "Hammond Labs": "哈蒙德实验室",
    "Hammond Laboratories": "哈蒙德实验室",
    "Skulltown": "骷髅镇",
    "Skull Town": "骷髅镇",
    "Autumn Estates": "秋日庄园",
    "Monument": "纪念碑",
    "Siphon": "虹吸管",
    "Caustic Treatment": "腐蚀疗法",
    "Estates": "秋日庄园",
    "Phase Runner": "相位通道",
    "Overflow": "溢出",
    "Habitat": "栖息地",
    "Encore": "安可",
    "Party Crasher": "派对破坏者",
    "Drop-Off": "空降区",
    # 混合模式地图
    "Barometer": "气压计",
    "Zeus Station": "宙斯站",
    "Thunderdome": "雷霆穹顶",
}

# 混合模式类型翻译
_MODE_ZH = {
    "Control": "区域控制",
    "TDM": "团队死斗",
    "Gun Run": "枪械升级赛",
    "Lockdown": "移动据点争夺",
}


def _parse_timer(timer_str: str) -> int:
    """Parse 'HH:MM:SS' or 'MM:SS' timer string to total seconds."""
    import re
    m = re.match(r"(?:(\d+):)?(\d+):(\d+)$", timer_str.strip())
    if not m:
        return 0
    h = int(m.group(1)) if m.group(1) else 0
    mm = int(m.group(2))
    s = int(m.group(3))
    return h * 3600 + mm * 60 + s


_BR_DURATION = 5400  # 90 min — standard BR/ranked rotation


def _build_map_rotation_html(rotation) -> str:
    import time as _time
    import datetime as _dt
    from zoneinfo import ZoneInfo

    _CST = ZoneInfo("Asia/Shanghai")

    modes = []

    def _make_map_data(mode_data, fallback_map: str = ""):
        """Build a map dict with image, name, start_fmt, end_fmt, end.
        Uses real start/end timestamps from API when available,
        falls back to computing from remaining timer + hardcoded duration."""
        if not mode_data or not mode_data.map:
            return None
        # Prefer real API timestamps (available from v2 API)
        start_ts = getattr(mode_data, 'start', 0)
        end_ts = getattr(mode_data, 'end', 0)
        if not start_ts or not end_ts:
            # Fallback: compute from remaining timer
            remaining_sec = _parse_timer(mode_data.remaining_timer)
            end_ts = int(_time.time()) + remaining_sec
            duration = _BR_DURATION
            start_ts = end_ts - duration
        else:
            start_ts = int(start_ts)
            end_ts = int(end_ts)
        # 翻译地图名（支持 "Map - Mode" 格式）
        raw_name = mode_data.map
        if " - " in raw_name:
            map_part, mode_part = raw_name.split(" - ", 1)
            translated_map = _MAP_ZH.get(map_part.strip(), map_part.strip())
            translated_mode = _MODE_ZH.get(mode_part.strip(), mode_part.strip())
            display_name = f"{translated_map} - {translated_mode}"
        else:
            display_name = _MAP_ZH.get(raw_name, raw_name)
        return {
            "image": _map_url(raw_name.split(" - ")[0].strip() if " - " in raw_name else raw_name),
            "name": display_name,
            "start_fmt": _dt.datetime.fromtimestamp(start_ts, tz=_CST).strftime("%H:%M"),
            "end_fmt": _dt.datetime.fromtimestamp(end_ts, tz=_CST).strftime("%H:%M"),
            "end": end_ts,
        }

    # 匹配 (Pubs)
    current_map = _make_map_data(rotation.br_current)
    next_map = _make_map_data(rotation.br_next)
    if current_map:
        modes.append({
            "key": "pubs",
            "name": "匹配",
            "current": current_map,
            "next": [next_map] if next_map else [],
        })

    # 排位 (Ranked)
    current_map = _make_map_data(rotation.ranked_current)
    next_map = _make_map_data(rotation.ranked_next)
    if current_map:
        modes.append({
            "key": "ranked",
            "name": "排位",
            "current": current_map,
            "next": [next_map] if next_map else [],
        })

    # 混合模式 (Mixtape — 原 LTM)
    if rotation.ltm_current and rotation.ltm_current.map:
        ltm_key = rotation.ltm_current.event_name.lower().replace(" ", "-") if rotation.ltm_current.event_name else "ltm"
        cur_map = _make_map_data(rotation.ltm_current)
        nxt_map = _make_map_data(rotation.ltm_next)
        if cur_map:
            modes.append({
                "key": f"ltm-{ltm_key}",
                "name": "混合模式",
                "event_name": rotation.ltm_current.event_name or "",
                "current": cur_map,
                "next": [nxt_map] if nxt_map else [],
            })

    # 外卡（Wildcard）
    if hasattr(rotation, 'wildcard_current') and rotation.wildcard_current and rotation.wildcard_current.map:
        cur_map = _make_map_data(rotation.wildcard_current)
        nxt_map = _make_map_data(rotation.wildcard_next)
        if cur_map:
            modes.append({
                "key": "wildcard",
                "name": "外卡",
                "current": cur_map,
                "next": [nxt_map] if nxt_map else [],
            })

    context = {
        "theme": _beijing_theme(),
        "modes": modes,
    }
    return _get_jinja_template("map_rotation.html.jinja").render(**context)


async def draw_map_rotation_card(rotation) -> bytes:
    html = _build_map_rotation_html(rotation)
    return await _render_card_sync(html, 720)


# ══════════════════════════════════════════
#  大师/猎杀数据卡片 (Moe Counter rule34)
# ══════════════════════════════════════════


def _build_predator_html(predator) -> str:
    platforms_order = ["PC", "PS4", "X1", "SWITCH"]

    platforms = []
    for plat in platforms_order:
        pd = predator.platforms.get(plat)
        if not pd:
            continue
        rp_imgs = _render_moe_digits_list(pd.predator_cap)

        # 24h 变动值（从 ALS 页面抓取）
        rp_change = getattr(pd, 'rp_change_24h', None)
        if rp_change is not None and rp_change > 0:
            change_class = "up"
            change_text = f"\u25b2 +{rp_change:,} RP"
        elif rp_change is not None and rp_change < 0:
            change_class = "down"
            change_text = f"\u25bc {rp_change:,} RP"
        elif rp_change is not None and rp_change == 0:
            change_class = "flat"
            change_text = "\u2014 RP"
        else:
            change_class = "flat"
            change_text = "\u2014 RP"

        count_fmt = f"{pd.masters_and_preds:,}"

        platforms.append({
            "name": plat,
            "rp_imgs": rp_imgs,
            "change_class": change_class,
            "change_text": change_text,
            "count_fmt": count_fmt,
        })

    context = {
        "theme": _beijing_theme(),
        "platforms": platforms,
    }
    return _get_jinja_template("predator.html.jinja").render(**context)


async def draw_predator_card(predator) -> bytes:
    html = _build_predator_html(predator)
    return await _render_card_sync(html, 720)


def _build_lfg_mode_card() -> str:
    from datetime import datetime, timezone, timedelta
    hour = datetime.now(timezone(timedelta(hours=8))).hour
    is_light = 6 <= hour < 18
    ff = "sans-serif" if _USE_LOCAL_FONTS else "'Noto Sans SC','Roboto',sans-serif"
    fl = "" if _USE_LOCAL_FONTS else '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&family=Roboto:wght@400;700&family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,0,0" rel="stylesheet">'
    ml = ""
    if _USE_LOCAL_FONTS:
        ml = '<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,0,0" rel="stylesheet">'
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
{fl}
{ml}
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:transparent;color:#e6e1e5;font-family:{ff};display:flex;justify-content:center;padding:40px 20px}}
body.light{{color:#1a1a2e}}
.card{{width:420px;background:#2b2930;border-radius:28px;padding:24px}}
body.light .card{{background:#f0f2f5}}
.title{{font-size:1.5rem;font-weight:700;margin-bottom:8px}}
body.light .title{{color:#1a1a2e}}
.subtitle{{font-size:0.85rem;color:#938f99;margin-bottom:24px}}
body.light .subtitle{{color:#666}}
.options{{display:flex;flex-direction:column;gap:12px}}
.opt{{padding:20px;border-radius:16px;background:#1c1b1f;border:1px solid #49454f;cursor:pointer;transition:all 0.2s ease}}
body.light .opt{{background:#e8eaed;border-color:#c4c7cc}}
.opt:hover{{background:#36343b;border-color:#4f378b}}
body.light .opt:hover{{background:#dde0e3;border-color:#6750a4}}
.opt-title{{font-size:1rem;font-weight:700;margin-bottom:4px}}
body.light .opt-title{{color:#1a1a2e}}
.opt-sub{{font-size:0.8rem;color:#938f99}}
body.light .opt-sub{{color:#666}}
.footer{{margin-top:24px;text-align:center;font-size:0.75rem;color:#938f99}}
body.light .footer{{color:#999}}
</style></head><body class="{"light" if is_light else ""}">
<div class="card">
    <div class="title">找队友</div>
    <div class="subtitle">选择你要玩的模式</div>
    <div class="options">
        <div class="opt">
            <div class="opt-title">排位赛</div>
            <div class="opt-sub">/lfg 排位</div>
        </div>
        <div class="opt">
            <div class="opt-title">娱乐匹配</div>
            <div class="opt-sub">/lfg 娱乐</div>
        </div>
    </div>
    <div class="footer">auth.赤羽真白 · Apex Chiyuchan</div>
</div>
</body></html>"""


def _build_lfg_html(entries: list[dict]) -> str:
    rank_colors = {
        "Predator": "#ffb4ab", "Master": "#d0bcff", "Diamond": "#bac3ff",
        "Platinum": "#99f1ff", "Gold": "#ffd966", "Silver": "#c0c0c0",
        "Bronze": "#cd7f32", "Unranked": "#938f99",
    }

    state_map = {"online": "在线", "in_game": "游戏中", "offline": "离线"}
    dot_color_map = {"online": "#4CE5B1", "in_game": "#4CE5B1", "offline": "#555"}

    players = []
    for e in entries:
        mode = e.get("mode", "ranked")
        rank_name = e.get("rank_name", "Unranked")
        rank_score = e.get("rank_score", 0)
        rank_img = e.get("rank_img", "")
        level = e.get("level", 0)
        kills = e.get("kills", 0)
        platform = e.get("platform", "PC")
        ladder_pos = e.get("rank_ladder_pos", 0) or 0
        state = e.get("state", "offline")

        rank_type = rank_name.lower().split(" ")[0] if rank_name else "unranked"
        rank_display = _rank_zh(rank_name)
        if ladder_pos and rank_name in ("Predator", "Master"):
            rank_display += f" #{ladder_pos}"

        chip_class = "chip-highlight" if mode == "ranked" else ""
        chip_icon = '<span class="material-symbols-rounded" style="font-size:16px">workspace_premium</span>' if mode == "ranked" else ""
        mode_label = "排位赛" if mode == "ranked" else "娱乐匹配"

        state_text = state_map.get(state, "在线")
        dot_color = dot_color_map.get(state, "#555")
        dot_icon = f'<span class="material-symbols-rounded" style="font-variation-settings:\'FILL\' 1;font-size:8px;color:{dot_color}">circle</span>'

        display_name = e.get("qq_name") or e.get("apex_name", "Unknown")

        players.append({
            "avatar": e.get("qq_avatar", ""),
            "display_name": display_name,
            "dot_icon": dot_icon,
            "state_text": state_text,
            "platform": platform,
            "rank_img": rank_img,
            "rank_name": rank_name,
            "rank_type": rank_type,
            "rank_score_fmt": f"{rank_score:,}",
            "rank_display": rank_display,
            "chip_class": chip_class,
            "chip_icon": chip_icon,
            "mode_label": mode_label,
            "level": level,
            "kills_fmt": f"{kills:,}",
        })

    context = {
        "theme": _beijing_theme(),
        "players": players,
    }
    return _get_jinja_template("lfg.html.jinja").render(**context)


async def draw_lfg_card(entries: list[dict]) -> bytes:
    html = _build_lfg_html(entries)
    return await _render_card_sync(html, 1328)


async def draw_lfg_mode_card() -> bytes:
    html = _build_lfg_mode_card()
    return await _render_card_sync(html, 420)


# ══════════════════════════════════════════
#  赛季信息卡片
# ══════════════════════════════════════════


def _build_season_html(season_info, meta_top5: list) -> str:
    """构建赛季信息卡片 HTML（北京时间 06:00-18:00 明亮，其余深色）"""
    from datetime import datetime, timezone, timedelta
    bj_hour = datetime.now(timezone(timedelta(hours=8))).hour
    theme = "light" if 6 <= bj_hour < 18 else ""
    context = {
        "theme": theme,
        "season_number": season_info.season_number,
        "season_name": season_info.season_name,
        "split_label": season_info.split_label,
        "split": season_info.split,
        "days_left": season_info.days_left,
        "hours_left": season_info.hours_left,
        "minutes_left": season_info.minutes_left,
        "season_end": season_info.season_end,
        "meta_top5": [
            {
                "name": m.name,
                "en": m.en,
                "icon": m.icon,
                "win_rate": m.win_rate,
                "pick_rate": m.pick_rate,
            }
            for m in meta_top5
        ],
    }
    return _get_jinja_template("season.html.jinja").render(**context)


async def draw_season_card(season_info, meta_top5: list) -> bytes:
    html = _build_season_html(season_info, meta_top5)
    return await _render_card_sync(html, 440)


async def draw_text_card_pw(title: str, message: str, is_error: bool = False) -> bytes:
    import html as _html
    color = "#DA292A" if is_error else "#4CE5B1"
    light_color = "#B3261E" if is_error else "#2E7D32"
    msg_lines = "".join(f'<div class="msg-line">{_html.escape(line)}</div>' for line in message.split("\n"))
    html_str = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{
  font-family:'Microsoft YaHei','Noto Sans SC',sans-serif;
  background:transparent;display:flex;justify-content:center;padding:24px
}}
.card{{
  width:420px;background:#1A2635;border-radius:16px;overflow:hidden;
  box-shadow:0 4px 24px rgba(0,0,0,.4)
}}
body.light .card{{background:#f0f2f5;box-shadow:0 4px 24px rgba(0,0,0,.08)}}
.header{{padding:24px 24px 0;font-size:20px;font-weight:800;color:{color}}}
body.light .header{{color:{light_color}}}
.body{{padding:16px 24px 24px;font-size:15px;color:#938f99;line-height:1.6}}
body.light .body{{color:#444}}
.msg-line{{margin-top:4px}}
.footer{{padding:0 24px 20px;font-size:12px;color:#49454f;text-align:center}}
body.light .footer{{color:#999}}
</style></head><body class="{"light" if _beijing_theme() else ""}">
<div class="card">
  <div class="header">{_html.escape(title)}</div>
  <div class="body">{msg_lines}</div>
  <div class="footer">auth.赤羽真白 &middot; Apex Chiyuchan</div>
</div>
</body></html>"""
    return await _render_card_sync(html_str, 460)


# ══════════════════════════════════════════
#  绑定 / 解绑 / 队伍 / 战绩卡片 HTML
# ══════════════════════════════════════════


def _build_bind_html(uid: str, name: str, platform: str) -> str:
    _theme = _beijing_theme()
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Microsoft YaHei','Noto Sans SC',sans-serif;background:transparent;display:flex;justify-content:center;padding:24px}}
.card{{width:480px;background:#1A2635;border-radius:16px;padding:28px;box-shadow:0 4px 24px rgba(0,0,0,.4);text-align:center}}
body.light .card{{background:#f0f2f5;box-shadow:0 4px 24px rgba(0,0,0,.08)}}
.title{{font-size:26px;font-weight:700;color:#4CE5B1;margin-bottom:16px}}
body.light .title{{color:#2E7D32}}
.row{{font-size:15px;color:#FFF;margin-bottom:8px}}
body.light .row{{color:#1a1a2e}}
.hint{{font-size:13px;color:#89A0B0;margin-top:20px}}
body.light .hint{{color:#666}}
.footer{{font-size:11px;color:#89A0B0;margin-top:16px}}
body.light .footer{{color:#999}}
</style></head><body class="{_theme}">
<div class="card">
<div class="title">绑定成功</div>
<div class="row">玩家　{_escape_html(name)}</div>
<div class="row">平台　{_escape_html(platform)}</div>
<div class="row">UID　　{_escape_html(uid)}</div>
<div class="hint">现在可以使用 /stats 查询战绩</div>
<div class="footer">auth.赤羽真白 · Apex Chiyuchan</div>
</div></body></html>"""


def _build_unbind_html() -> str:
    _theme = _beijing_theme()
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Microsoft YaHei','Noto Sans SC',sans-serif;background:transparent;display:flex;justify-content:center;padding:24px}}
.card{{width:480px;background:#1A2635;border-radius:16px;padding:28px;box-shadow:0 4px 24px rgba(0,0,0,.4);text-align:center}}
body.light .card{{background:#f0f2f5;box-shadow:0 4px 24px rgba(0,0,0,.08)}}
.title{{font-size:26px;font-weight:700;color:#4CE5B1;margin-bottom:12px}}
body.light .title{{color:#2E7D32}}
.msg{{font-size:15px;color:#89A0B0}}
body.light .msg{{color:#666}}
.footer{{font-size:11px;color:#89A0B0;margin-top:20px}}
body.light .footer{{color:#999}}
</style></head><body class="{_theme}">
<div class="card">
<div class="title">已解绑</div>
<div class="msg">Apex 账号已与本 QQ 解除绑定</div>
<div class="footer">auth.赤羽真白 · Apex Chiyuchan</div>
</div></body></html>"""


def _build_team_html(team: dict) -> str:
    name = _escape_html(team.get("name", ""))
    owner = _escape_html(str(team.get("owner_qq", "")))
    member_count = team.get("member_count", 0)
    members = team.get("members", [])
    ttl_hours = team.get("ttl_hours", 12)

    members_html = ""
    for m in members:
        crown = " (队长)" if str(m) == str(team.get("owner_qq", "")) else ""
        members_html += f'<div class="member">　{_escape_html(str(m))}{crown}</div>'
    for _ in range(3 - member_count):
        members_html += '<div class="member empty">　(空位)</div>'

    _theme = _beijing_theme()
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Microsoft YaHei','Noto Sans SC',sans-serif;background:transparent;display:flex;justify-content:center;padding:24px}}
.card{{width:500px;background:#1A2635;border-radius:16px;padding:24px;box-shadow:0 4px 24px rgba(0,0,0,.4)}}
body.light .card{{background:#f0f2f5;box-shadow:0 4px 24px rgba(0,0,0,.08)}}
.team-name{{font-size:26px;font-weight:700;color:#FFF;margin-bottom:4px}}
body.light .team-name{{color:#1a1a2e}}
.owner{{font-size:12px;color:#89A0B0;margin-bottom:16px}}
body.light .owner{{color:#666}}
.section-title{{font-size:18px;font-weight:700;color:#FFF;margin-bottom:8px}}
body.light .section-title{{color:#1a1a2e}}
.member{{font-size:15px;color:#FFF;margin-bottom:4px}}
body.light .member{{color:#1a1a2e}}
.member.empty{{color:#89A0B0}}
body.light .member.empty{{color:#999}}
.ttl{{font-size:12px;color:#89A0B0;margin-top:16px}}
body.light .ttl{{color:#666}}
.footer{{font-size:11px;color:#89A0B0;margin-top:16px;text-align:center}}
body.light .footer{{color:#999}}
</style></head><body class="{_theme}">
<div class="card">
<div class="team-name">{name}</div>
<div class="owner">队长: {owner}</div>
<div class="section-title">成员 ({member_count}/3)</div>
{members_html}
<div class="ttl">{ttl_hours} 小时后自动解散</div>
<div class="footer">auth.赤羽真白 · Apex Chiyuchan</div>
</div></body></html>"""


def _build_team_list_html(teams: list[dict]) -> str:
    count = len(teams)
    if count == 0:
        items_html = '<div class="empty">暂无活跃队伍</div>'
    else:
        items = ""
        for t in teams:
            n = _escape_html(t.get("name", ""))
            mc = t.get("member_count", 0)
            o = _escape_html(str(t.get("owner_qq", "")))
            items += f'<div class="team-row">{n}　{mc}/3　队长:{o}</div>'
        items_html = items

    _theme = _beijing_theme()
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Microsoft YaHei','Noto Sans SC',sans-serif;background:transparent;display:flex;justify-content:center;padding:24px}}
.card{{width:500px;background:#1A2635;border-radius:16px;padding:24px;box-shadow:0 4px 24px rgba(0,0,0,.4)}}
body.light .card{{background:#f0f2f5;box-shadow:0 4px 24px rgba(0,0,0,.08)}}
.title{{font-size:26px;font-weight:700;color:#FFF;margin-bottom:16px}}
body.light .title{{color:#1a1a2e}}
.team-row{{font-size:15px;color:#FFF;margin-bottom:12px;padding:8px 0;border-bottom:1px solid #2A3A4A}}
body.light .team-row{{color:#1a1a2e;border-bottom-color:#e0e0e0}}
.empty{{font-size:15px;color:#89A0B0}}
body.light .empty{{color:#999}}
.footer{{font-size:11px;color:#89A0B0;margin-top:16px;text-align:center}}
body.light .footer{{color:#999}}
</style></head><body class="{_theme}">
<div class="card">
<div class="title">活跃队伍 ({count})</div>
{items_html}
<div class="footer">auth.赤羽真白 · Apex Chiyuchan</div>
</div></body></html>"""


def _build_stats_card_html(stats) -> str:
    """Build stats card HTML from PlayerStats object."""
    name = _escape_html(stats.name or "Unknown")
    avatar_url = stats.avatar or ""
    level = stats.level
    level_pct = stats.to_next_level_pct
    rank_name = stats.rank_name or "Unranked"
    rank_score = stats.rank_score
    rank_top_pct = stats.rank_top_pct
    state = stats.state
    kills = stats.kills
    damage = stats.damage
    kd = stats.kd
    top_legends = stats.top_legends or []
    selected_legend = stats.selected_legend or ""

    rank_color = RANK_COLORS.get(rank_name.split(" ")[0], "#89A0B0")
    status_color = "#4CE5B1" if state == "online" else "#89A0B0"
    status_text = "在线" if state == "online" else "离线"
    kd_str = f"{kd:.2f}" if kd is not None else "--"

    legends_html = ""
    if top_legends:
        rows = ""
        for leg in top_legends[:3]:
            rows += (
                f'<div style="display:flex;justify-content:space-between;padding:4px 0;">'
                f'<span style="font-size:13px;color:#89A0B0;">{_escape_html(leg["name"])}</span>'
                f'<span style="font-size:15px;font-weight:700;color:#FFF;">{leg["kills"]:,}</span>'
                f"</div>"
            )
        legends_html = (
            f'<div style="font-size:14px;font-weight:600;color:#89A0B0;'
            f'text-transform:uppercase;letter-spacing:2px;padding:12px 0 6px;">常用英雄 TOP3</div>'
            f"{rows}"
        )

    selected_html = ""
    if selected_legend:
        selected_html = (
            f'<div style="font-size:12px;color:#89A0B0;margin-top:8px;">'
            f"当前选用: {_escape_html(selected_legend)}</div>"
        )

    avatar_html = (
        f'<img style="width:52px;height:52px;border-radius:50%;object-fit:cover;" '
        f"src=\"{avatar_url}\" onerror=\"this.style.display='none'\">"
        if avatar_url
        else ""
    )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Microsoft YaHei','Noto Sans SC',sans-serif;background:transparent;display:flex;justify-content:center;padding:24px}}
.card{{width:600px;background:#1A2635;border-radius:16px;padding:24px;box-shadow:0 4px 24px rgba(0,0,0,.4)}}
</style></head><body>
<div class="card">
<div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">
{avatar_html}
<div>
<div style="font-size:26px;font-weight:700;color:#FFF;">{name}</div>
<div style="font-size:12px;color:#89A0B0;margin-top:2px;">
<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{status_color};margin-right:4px;vertical-align:middle;"></span>
Lv.{level}　{level_pct}%　{status_text}</div>
</div>
</div>
<div style="display:flex;align-items:center;gap:12px;padding:8px 0;margin-bottom:4px;">
<div style="width:4px;height:64px;background:{rank_color};border-radius:2px;"></div>
<div>
<div style="font-size:18px;font-weight:700;color:{rank_color};">{_escape_html(rank_name)}</div>
<div style="font-size:15px;color:#FFF;margin-top:2px;">RP {rank_score:,}</div>
<div style="font-size:12px;color:#89A0B0;margin-top:2px;">全服 Top {rank_top_pct}%</div>
</div>
</div>
<div style="border-top:1px solid #2A3A4A;margin:8px 0 16px;"></div>
<div style="font-size:14px;font-weight:600;color:#89A0B0;text-transform:uppercase;letter-spacing:2px;padding-bottom:8px;">生涯数据总览</div>
<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;text-align:center;margin-bottom:16px;">
<div><div style="font-size:28px;font-weight:700;color:#FFF;">{kills:,}</div><div style="font-size:13px;color:#89A0B0;">击杀</div></div>
<div><div style="font-size:28px;font-weight:700;color:#FFF;">{damage:,}</div><div style="font-size:13px;color:#89A0B0;">伤害</div></div>
<div><div style="font-size:28px;font-weight:700;color:#FFF;">{kd_str}</div><div style="font-size:13px;color:#89A0B0;">K/D</div></div>
</div>
{legends_html}
{selected_html}
<div style="font-size:11px;color:#89A0B0;margin-top:16px;text-align:center;">auth.赤羽真白 · Apex Chiyuchan</div>
</div></body></html>"""


async def draw_bind_card_pw(uid: str, name: str, platform: str) -> bytes:
    html = _build_bind_html(uid, name, platform)
    return await _render_card_sync(html, 520)


async def draw_unbind_card_pw() -> bytes:
    html = _build_unbind_html()
    return await _render_card_sync(html, 520)


async def draw_team_card_pw(team: dict) -> bytes:
    html = _build_team_html(team)
    return await _render_card_sync(html, 540)


async def draw_team_list_card_pw(teams: list[dict]) -> bytes:
    html = _build_team_list_html(teams)
    return await _render_card_sync(html, 540)


async def draw_stats_card_pw(stats) -> bytes:
    html = _build_stats_card_html(stats)
    return await _render_card_sync(html, 640)


# ══════════════════════════════════════════
#  Jinja2 模板加载器（共享）
# ══════════════════════════════════════════

_TEMPLATE_CACHE: dict[str, "Template"] = {}


def _get_jinja_template(name: str) -> "Template":
    """懒加载任意 Jinja 模板（缓存）"""
    if name not in _TEMPLATE_CACHE:
        from pathlib import Path
        from jinja2 import Environment, FileSystemLoader
        tmpl_dir = Path(__file__).parent
        env = Environment(loader=FileSystemLoader(str(tmpl_dir)), autoescape=False)
        _TEMPLATE_CACHE[name] = env.get_template(name)
    return _TEMPLATE_CACHE[name]


# ══════════════════════════════════════════
#  Steamcharts 日活卡片（Jinja 模板 + Chart.js）
# ══════════════════════════════════════════


def _render_steamcharts_html(data) -> str:
    """用 Jinja 模板渲染 Steamcharts MD3 卡片 HTML"""
    import datetime as _dt
    import json as _json

    _tz = _dt.timezone(_dt.timedelta(hours=8))
    now = _dt.datetime.now(_tz)
    updated = now.strftime("%Y-%m-%d %H:%M")

    # 原始 7 天数据点 [[ts_ms, players], ...]
    raw_points = getattr(data, "raw_7d_points", None) or []
    # 如果没有原始数据，退回用分桶数据构造
    if not raw_points:
        for b in (data.seven_day_buckets or []):
            raw_points.append([b.ts_ms, int(b.avg_players)])

    ctx = {
        "theme": _beijing_theme(),
        "title": "Apex Legends",
        "current_formatted": f"{data.current_online:,}",
        "updated_local": updated,
        "peak_24h_formatted": f"{data.peak_24h:,}",
        "peak_all_formatted": f"{data.peak_all_time:,}",
        "point_count": len(raw_points),
        "app_id": "1172470",
        "data": _json.dumps(raw_points),
    }
    return _get_jinja_template("steamcharts_template.jinja").render(**ctx)


async def draw_steamcharts_card(data) -> bytes:
    """渲染 Steamcharts Jinja 模板卡片 PNG — 等待 Chart.js 加载并渲染 canvas"""
    html = _render_steamcharts_html(data)
    from .playwright_manager import run_with_page

    async with run_with_page(
        viewport={"width": 720, "height": 900}, device_scale_factor=3
    ) as page:
        # 允许外部 CDN 资源加载（Chart.js + Google Fonts）
        await page.set_content(html, wait_until="load", timeout=30000)
        # 等待 Chart.js 库加载完成
        try:
            await page.wait_for_function(
                "() => typeof window.Chart !== 'undefined'",
                timeout=15000,
            )
        except Exception:
            pass
        # 等待 chart 实例创建 + canvas 渲染（等待 Chart.js 内部动画首帧）
        try:
            await page.wait_for_function(
                "() => { const c = document.getElementById('trendChart'); "
                "return c && c.width > 0 && c.height > 0; }",
                timeout=10000,
            )
        except Exception:
            pass
        # 额外等待让 Chart.js 完成渲染动画
        await page.wait_for_timeout(800)
        # 等待字体就绪
        try:
            await page.wait_for_function("() => document.fonts.ready", timeout=5000)
        except Exception:
            pass
        card = await page.query_selector(".card")
        if card:
            return await card.screenshot(type="png", omit_background=True)
        return await page.screenshot(full_page=False, type="png")

