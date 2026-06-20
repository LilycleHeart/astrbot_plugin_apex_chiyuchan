"""Playwright WebKit HTML → PNG 渲染器 — Material Design 战绩卡片"""

from __future__ import annotations

import base64
import io

from PIL import Image

from .config import RANK_COLORS
from .playwright_manager import run_with_page

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
    """段位分布 — 仅显示玩家所在段位附近4个段位，含人数"""
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


def _build_stats_html(**d) -> str:
    """根据数据 dict 构建内联 CSS 的 Material Design 卡片 HTML"""

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

    # ── 根据段位动态取色 ──
    _theme = _theme_for_rank(rank_name)
    _C_SURFACE = _theme["surface"]
    _C_CARD = _theme["card"]
    _C_CARD2 = _theme["card2"]
    _C_CARD3 = _theme["card3"]
    _C_TEXT = _theme["text"]
    _C_MUTED = _theme["muted"]
    _C_OUTLINE = _theme["outline"]

    rp_delta = d.get("rp_delta")
    kills = d.get("kills", 0)
    damage = d.get("damage", 0)
    wins = d.get("wins", 0)
    wins_display = f"{wins:,}" if wins else "0"
    top_legends = d.get("top_legends", [])
    season_badges = d.get("season_badges", [])
    special_badges = d.get("special_badges", [])
    selected_legend = d.get("selected_legend")
    rank_dist_entries = d.get("rank_dist_entries", None)

    _p = {"PC": "PC", "PS4": "PS", "PS5": "PS", "X1": "Xbox", "XBX": "Xbox"}.get(platform.upper(), platform.upper())
    top_pct_label = "全平台" if rank_name.startswith(("Predator", "Master")) else _p

    display_name = f"{name} [{tag}]" if tag else name
    _p = {"PC": "PC", "PS4": "PS", "PS5": "PS", "X1": "Xbox", "XBX": "Xbox"}.get(platform.upper(), platform.upper())
    top_pct_label = "全平台" if rank_name.startswith(("Predator", "Master")) else _p
    online_map = {"online": "在线", "offline": "离线", "in_game": "游戏中"}
    state_text = online_map.get(online, online)
    state_dot = "#4CE5B1" if online in ("online", "in_game") else "#555"
    prestige_str = ""  # level is now total level, no need to show prestige prefix
    rank_c = _rank_color(rank_name)
    top_global = f"{rank_top_pct_global}%"
    rp_delta_html = ""
    if rp_delta is not None:
        sign = "+" if rp_delta >= 0 else ""
        delta_color = "#4CE5B1" if rp_delta >= 0 else "#DA292A"
        rp_delta_html = f'<span style="font-size:13px;color:{delta_color};margin-left:8px;">{sign}{rp_delta} RP</span>'

    # ── 徽章 HTML ──
    badge_rows = ""
    if season_badges:
        chips = []
        for b in season_badges:
            url = b.get("badge_url", "")
            s = b.get("season", "")
            tier = b.get("tier", "")
            color = b.get("color") or "#666"
            fw = "font-weight:700;" if tier == "master" else ""
            chips.append(
                f'<span style="display:inline-flex;align-items:center;gap:4px;padding:4px 10px;'
                f"border-radius:20px;font-size:12px;font-weight:600;{fw}"
                f"background:rgba({_hex_to_rgba(color, 0.15)});color:{color};"
                f'border:1px solid rgba({_hex_to_rgba(color, 0.3)});">'
                f'<img src="{url}" style="width:36px;height:36px;vertical-align:middle;" onerror="this.remove()">{s}</span>'
            )
        badge_rows += (
            f'<div style="display:flex;flex-wrap:wrap;gap:8px;padding:0 24px 12px;'
            f'justify-content:center;">{"".join(chips)}</div>'
        )

    spec_rows = ""
    if special_badges:
        chips = []
        for b in special_badges:
            b_url = b.get("badge_url", "")
            if not b_url:
                continue
            chips.append(
                f'<span style="display:inline-flex;align-items:center;justify-content:center;'
                f'width:40px;height:40px;border-radius:50%;'
                f'background:rgba(177,244,250,0.12);'
                f'border:1px solid rgba(177,244,250,0.25);">'
                f'<img src="{b_url}" style="width:28px;height:28px;display:block;" onerror="this.remove()"></span>'
            )
        spec_rows += (
            f'<div style="display:flex;flex-wrap:wrap;gap:8px;padding:0 24px 16px;'
            f'justify-content:center;">{"".join(chips)}</div>'
        )

    # ── 英雄排行 ──
    legends_html = ""
    if top_legends:
        rows = []
        for i, leg in enumerate(top_legends[:4]):
            icon_url = leg.get("icon_url", "") or leg.get("icon", "")
            top = (
                " background:linear-gradient(135deg,rgba(149,83,211,0.08),transparent);"
                if i == 0
                else ""
            )
            kc = "#9553d3" if i == 0 else _C_TEXT
            bd = "border:2px solid #9553d3;" if i == 0 else "border:2px solid #3e414d;"
            it = (
                f'<img src="{icon_url}" style="width:36px;height:36px;border-radius:50%;object-fit:cover;{bd}" onerror="this.remove()">'
                if icon_url
                else '<div style="width:36px;height:36px;border-radius:50%;background:#313542;"></div>'
            )
            rows.append(
                f'<div style="display:flex;align-items:center;gap:12px;padding:10px 12px;'
                f'border-radius:8px;margin-bottom:2px;{top}">'
                f'{it}<span style="flex:1;font-size:14px;font-weight:500;">{_legend_zh(leg["name"])}</span>'
                f'<span style="font-size:16px;font-weight:700;color:{kc};">{leg.get("kills", 0):,}</span>'
                f"</div>"
            )
        legends_html = f'<div style="padding:0 24px 16px;">{"".join(rows)}</div>'

    # ── 当前选用 ──
    selected_html = ""
    if selected_legend:
        sn = selected_legend.get("name", "")
        ss = selected_legend.get("stats", [])
        si = selected_legend.get("icon_url", "")
        st_html = ""
        for s in ss:
            st_html += (
                f'<span style="margin-right:24px;">'
                f'<span style="font-size:11px;color:{_C_MUTED};display:block;">{s.get("name", "")}</span>'
                f'<span style="font-size:14px;font-weight:500;">{s.get("value", "")}</span>'
                f"</span>"
            )
        ic = (
            f'<img src="{si}" style="width:36px;height:36px;border-radius:50%;object-fit:cover;border:2px solid #3e414d;" onerror="this.remove()">'
            if si
            else ""
        )
        selected_html = f"""
<div style="font-size:14px;font-weight:600;color:{_C_MUTED};text-transform:uppercase;letter-spacing:2px;padding:16px 24px 8px;">当前选用</div>
<div style="padding:0 24px 8px;display:flex;align-items:center;gap:12px;">
{ic}<span style="font-size:16px;font-weight:600;">{_legend_zh(sn)}</span>
<span style="display:flex;gap:8px;margin-left:auto;">{st_html}</span>
</div>"""

    # ── 段位分布参考条 ──
    rank_dist = _build_rank_dist(rank_name, rank_top_pct_global, rank_dist_entries, theme=_theme)

    badge_section = ""
    if badge_rows:
        badge_section += f'<div style="font-size:14px;font-weight:600;color:{_C_MUTED};text-transform:uppercase;letter-spacing:2px;padding:16px 24px 8px;">Ranked 赛季徽章</div>{badge_rows}'
    if spec_rows:
        badge_section += f'<div style="font-size:14px;font-weight:600;color:{_C_MUTED};text-transform:uppercase;letter-spacing:2px;padding:16px 24px 8px;">特殊徽章</div>{spec_rows}'

    # ══════ 完整 HTML（配色与原版卡片 ancallbelle_card.html 完全一致） ══════
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{
  font-family:'Microsoft YaHei','Noto Sans SC',sans-serif;
  background:transparent;color:{_C_TEXT};
  display:flex;justify-content:center;padding:24px
}}
.card{{
  width:680px;background:{_C_CARD};border-radius:24px;overflow:hidden;
  box-shadow:0 10px 20px rgba(0,0,0,.4)
}}
.header-bar{{
  background:linear-gradient(135deg,{_C_CARD},{_C_CARD2});padding:20px 24px;
  display:flex;align-items:center;gap:16px;
  border-bottom:1px solid {_C_OUTLINE}
}}
.avatar{{
  width:56px;height:56px;border-radius:50%;object-fit:cover;
  border:3px solid {rank_c};box-shadow:0 0 16px {rank_c}44
}}
.player-name{{font-size:22px;font-weight:800;letter-spacing:1px}}
.player-meta{{font-size:12px;color:{_C_MUTED};margin-top:2px}}
.platform-tag{{
  display:inline-flex;align-items:center;gap:6px;background:{_C_CARD};
  border:1px solid {_C_OUTLINE};border-radius:20px;
  padding:4px 12px;font-size:12px;margin-top:4px
}}

.rank-section{{
  display:flex;align-items:center;padding:16px 24px;gap:16px;
  background:{_C_CARD2};border-bottom:1px solid {_C_OUTLINE}
}}
.rank-img{{width:80px;height:80px;filter:drop-shadow(0 4px 8px {rank_c}44)}}
.rank-tier{{font-size:28px;font-weight:800;color:{rank_c};line-height:1}}
.rank-div{{font-size:16px;color:{rank_c};opacity:.9}}
.rank-rp{{font-size:14px;color:{_C_MUTED};margin-top:4px}}
.rank-stats{{display:flex;gap:24px;text-align:center;margin-left:auto}}
.rank-stat-val{{font-size:18px;font-weight:700;color:{rank_c}}}
.rank-stat-label{{font-size:11px;color:{_C_MUTED};text-transform:uppercase}}

.level-row{{
  display:flex;align-items:center;gap:12px;padding:12px 24px;
  border-bottom:1px solid {_C_OUTLINE}
}}
.level-icon{{
  width:48px;height:48px;object-fit:contain;
  filter:drop-shadow(0 2px 6px rgba(0,0,0,.4))
}}
.level-bar{{flex:1;height:6px;background:{_C_CARD3};border-radius:3px;overflow:hidden}}
.level-fill{{height:100%;width:{level_pct}%;background:linear-gradient(90deg,{_C_PRED},#ff6b6b);border-radius:3px}}

.stat-grid{{
  display:grid;grid-template-columns:repeat(3,1fr);
  gap:1px;background:{_C_OUTLINE}
}}
.stat-chip{{
  background:{_C_CARD};padding:16px;text-align:center;
  display:flex;flex-direction:column;gap:4px
}}
.stat-val{{font-size:22px;font-weight:700;color:{_C_TEXT}}}
.stat-val.highlight{{color:{_C_GOLD}}}
.stat-lbl{{font-size:11px;color:{_C_MUTED};text-transform:uppercase;letter-spacing:.5px}}

.footer{{
  padding:12px 24px;border-top:1px solid {_C_OUTLINE};
  font-size:11px;color:{_C_MUTED};display:flex;justify-content:space-between
}}
</style></head><body>
<div class="card">

<div class="header-bar">
  <img class="avatar" src="{avatar_url}" onerror="this.style.display='none'">
  <div>
    <div class="player-name">{display_name}</div>
    <div class="player-meta">{"aka " + alias + " · " if alias else ""}UID: {uid}</div>
    <div class="platform-tag"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{state_dot};margin-right:4px;"></span>{platform} · {state_text}</div>
  </div>
</div>

<div class="rank-section">
  <img class="rank-img" src="{rank_img}" onerror="this.remove()">
  <div>
    <div class="rank-tier">{_rank_zh(rank_name)}{_rank_div_zh(rank_div, rank_name)}{' #' + str(rank_ladder_pos) if rank_ladder_pos and (rank_name.startswith('Predator') or rank_name.startswith('Master')) else ''}</div>
    <div class="rank-rp">{rank_score:,} RP{rp_delta_html}</div>
  </div>
  <div class="rank-stats">
    <div><div class="rank-stat-val">{top_global}</div><div class="rank-stat-label">Top ({top_pct_label})</div></div>
  </div>
</div>

<div class="level-row">
  <img class="level-icon" src="{level_icon}" onerror="this.style.display='none'">
  <div style="font-size:12px;color:{_C_MUTED};">{level_pct}% to next</div>
  <div class="level-bar"><div class="level-fill"></div></div>
</div>

<div class="stat-grid">
  <div class="stat-chip"><div class="stat-val highlight">{kills:,}</div><div class="stat-lbl">生涯击杀</div></div>
  <div class="stat-chip"><div class="stat-val">{damage:,}</div><div class="stat-lbl">BR 总伤害</div></div>
  <div class="stat-chip"><div class="stat-val">{wins_display}</div><div class="stat-lbl">BR 胜场</div></div>
</div>

{selected_html}

<div style="font-size:14px;font-weight:600;color:{_C_MUTED};text-transform:uppercase;letter-spacing:2px;padding:16px 24px 8px;">段位分布参考 (全平台)</div>
{rank_dist}

<div style="font-size:14px;font-weight:600;color:{_C_MUTED};text-transform:uppercase;letter-spacing:2px;padding:16px 24px 8px;">常用英雄</div>
{legends_html if legends_html else f'<div style="padding:0 24px 16px;color:{_C_MUTED};font-size:13px;">暂无英雄数据</div>'}

{badge_section}

<div class="footer">
  <span>Data: <span style="color:{_C_PRED};">Apex Legends Status</span></span>
  <span style="color:{_C_MUTED};">auth.赤羽真白 · Apex Chiyuchan</span>
  <span>UID: {uid}</span>
</div>

</div>
</body></html>"""


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




# ══════════════════════════════════════════
#  公开接口
# ══════════════════════════════════════════
#  图片缓存 — 远程URL转base64，零网络渲染
# ══════════════════════════════════════════

import asyncio
import re
from functools import lru_cache

_image_cache: dict[str, str] = {}


@lru_cache(maxsize=128)
def _download_sync(url: str) -> str | None:
    """同步下载图片转base64 (lru_cache保证线程安全)"""
    import httpx
    try:
        with httpx.Client(timeout=8.0, follow_redirects=True) as c:
            r = c.get(url)
            r.raise_for_status()
            b64 = base64.b64encode(r.content).decode()
            return f"data:image/png;base64,{b64}"
    except Exception:
        return None


async def _embed_images(html: str) -> str:
    """将远程图片URL替换为base64 data URI"""
    urls = set()
    urls.update(re.findall(r'src="(https?://[^"]+)"', html))
    urls.update(re.findall(r'url\((https?://[^)]+)\)', html))

    new_urls = [u for u in urls if u not in _image_cache]
    if new_urls:

        async def _fetch(url):
            loop = asyncio.get_running_loop()
            b64 = await loop.run_in_executor(None, _download_sync, url)
            if b64:
                _image_cache[url] = b64
            return b64

        await asyncio.gather(*[_fetch(u) for u in new_urls], return_exceptions=True)

    def _replace(m):
        url = m.group(1)
        return m.group(0).replace(url, _image_cache.get(url, url))

    html = re.sub(r'src="(https?://[^"]+)"', _replace, html)
    html = re.sub(r'url\((https?://[^)]+)\)', _replace, html)
    return html


async def _render_card_sync(html: str, width: int) -> bytes:
    html = await _embed_images(html)
    async with run_with_page(viewport={"width": width, "height": 100}, device_scale_factor=2) as page:
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


def _build_als_alert_html(als) -> str:
    parts = ""
    if als and als.alert_banner:
        parts += f"""<div class="als-alert"><i class="warning-icon">⚠</i><span>{_escape_html(als.alert_banner)}</span></div>"""
    if als and als.outage_announcement:
        parts += """<div class="als-alert als-outage"><i class="warning-icon">🔴</i><span>服务中断进行中</span></div>"""
    return parts


def _build_als_sections_html(als) -> str:
    if not als or not als.sections:
        return ""
    html = ""
    for sec in als.sections:
        s_lower = sec.status.lower()
        is_unstable = "unstable" in s_lower or "slow" in s_lower
        is_down = "down" in s_lower
        pill_class = "pill-down" if is_down else ("pill-unstable" if is_unstable else "pill-up")
        sec_name = _locale_section_name(sec.name)
        sec_pill = _locale_status(sec.status)
        html += f"""
        <div class="als-section">
            <div class="als-section-head">
                <span class="als-section-name">{_escape_html(sec_name)}</span>
                <span class="als-pill {pill_class}">{_escape_html(sec_pill)}</span>
            </div>"""
        for entry in sec.entries[:5]:
            e_upper = entry.status.upper()
            if "DOWN" in e_upper:
                state_class = "state-down"
                dot_color = "#FF4444"
            elif "UNSTABLE" in e_upper or "SLOW" in e_upper:
                state_class = "state-unstable"
                dot_color = "#FFA500"
            elif is_down or is_unstable:  # section abnormal → override UP entries to orange
                state_class = "state-unstable"
                dot_color = "#FFA500"
            else:
                state_class = "state-up"
                dot_color = "#4CE5B1"
            entry_status = _locale_status(entry.status)
            html += f"""
            <div class="als-row">
                <span class="dot" style="background:{dot_color}"></span>
                <span class="als-row-name">{_escape_html(entry.name)}</span>
                <span class="als-row-state {state_class}">{_escape_html(entry_status)}</span>
                <span class="als-row-rt">{_escape_html(entry.response_time)}</span>
            </div>"""
        html += "</div>"
    return html


def _build_server_status_html(server_status) -> str:
    als = getattr(server_status, "als", None)

    alert_html = _build_als_alert_html(als)
    als_sections_html = _build_als_sections_html(als)

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Microsoft YaHei','Noto Sans SC',sans-serif;background:transparent;color:{_C_TEXT};display:flex;justify-content:center;padding:24px}}
.card{{width:680px;background:{_C_CARD};border-radius:24px;overflow:hidden;box-shadow:0 10px 20px rgba(0,0,0,.4)}}
.header{{background:linear-gradient(135deg,{_C_CARD},{_C_CARD2});padding:20px 24px;border-bottom:1px solid {_C_OUTLINE}}}
.header h2{{font-size:22px;font-weight:800}}
.als-alert{{display:flex;align-items:flex-start;gap:8px;padding:12px 24px;background:rgba(255,165,0,.12);border-bottom:1px solid {_C_OUTLINE};font-size:12px;color:#FFB347;line-height:1.5}}
.als-outage{{background:rgba(255,69,0,.18);font-weight:700;color:#FF6347}}
.warning-icon{{flex-shrink:0;font-size:16px}}
.als-section{{border-bottom:1px solid {_C_OUTLINE};padding:12px 24px}}
.als-section:last-child{{border-bottom:none}}
.als-section-head{{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}}
.als-section-name{{font-size:14px;font-weight:700}}
.als-pill{{font-size:11px;font-weight:700;padding:3px 8px;border-radius:10px}}
.pill-down{{background:rgba(255,68,68,.18);color:#FF4444}}
.pill-unstable{{background:rgba(255,165,0,.2);color:#FFB347}}
.pill-up{{background:rgba(76,229,177,.15);color:#4CE5B1}}
.als-row{{display:flex;align-items:center;padding:6px 0;gap:8px}}
.als-row .dot{{width:8px;height:8px}}
.als-row-name{{flex:1;font-size:13px}}
.als-row-state{{font-size:12px;font-weight:700;width:70px;text-align:center}}
.state-unstable{{color:#FFB347}}
.state-down{{color:#FF4444}}
.state-up{{color:#4CE5B1}}
.als-row-rt{{font-size:11px;color:{_C_MUTED};width:64px;text-align:right}}
.footer{{padding:12px 24px;border-top:1px solid {_C_OUTLINE};font-size:11px;color:{_C_MUTED};text-align:center}}
</style></head><body>
<div class="card">
<div class="header"><h2>Apex 服务器状态</h2></div>
{alert_html}
{als_sections_html}
<div class="footer">数据来源: apexlegendsstatus.com</div>
</div>
</body></html>"""


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
}


def _build_map_rotation_html(rotation) -> str:
    def _section(mode_id: str, label: str, badge_color: str, current, next_) -> str:
        cur_map = current.map if current else ""
        nxt_map = next_.map if next_ else ""
        cur_zh = _MAP_ZH.get(cur_map, cur_map)
        nxt_zh = _MAP_ZH.get(nxt_map, nxt_map)
        cur_bg = _map_url(cur_map)
        nxt_bg = _map_url(nxt_map)
        timer = current.remaining_timer if current else ""

        cur_bg_css = f"background-image:url({cur_bg})" if cur_bg else ""
        nxt_bg_css = f"background-image:url({nxt_bg})" if nxt_bg else ""

        return f"""
        <div class="mode-card">
            <div class="split-bg-container">
                <div class="bg-img bg-left" style="{cur_bg_css}"></div>
                <div class="hud-arrow">
                    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                        <path fill="none" stroke="rgba(255,255,255,0.6)" stroke-width="1.5" d="M6,18L14.5,12L6,6M13,18L21.5,12L13,6"/>
                    </svg>
                </div>
                <div class="bg-img bg-right" style="{nxt_bg_css}"></div>
            </div>
            <div class="content-layer">
                <div class="top-row">
                    <span class="badge" style="background:{badge_color}">{label}</span>
                    <span class="timer-chip">{timer}</span>
                </div>
                <div class="bottom-row">
                    <div class="cur-info">
                        <span class="meta-label">当前地图</span>
                        <span class="cur-name">{cur_zh}</span>
                    </div>
                    <div class="divider"></div>
                    <div class="next-info">
                        <span class="meta-label">下一张</span>
                        <span class="next-name">{nxt_zh}</span>
                    </div>
                </div>
            </div>
        </div>"""

    br = _section("pubs", "匹配", "#DA292A", rotation.br_current, rotation.br_next)
    ranked = _section("ranked", "排位", "#E7C150", rotation.ranked_current, rotation.ranked_next)

    ltm = ""
    if rotation.ltm_current and rotation.ltm_current.event_name:
        ltm = _section(
            "ltm",
            rotation.ltm_current.event_name,
            "#5D9FF0",
            rotation.ltm_current,
            rotation.ltm_next,
        )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Microsoft YaHei','Noto Sans SC',sans-serif;background:transparent;display:flex;justify-content:center;padding:24px}}
.card{{width:680px;background:{_C_CARD};border-radius:24px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.4)}}
.title{{padding:18px 28px;font-size:20px;font-weight:800;color:{_C_TEXT};letter-spacing:0.5px;border-bottom:1px solid {_C_OUTLINE}}}

.mode-card{{position:relative;height:200px;overflow:hidden}}
.mode-card:not(:last-child){{border-bottom:1px solid rgba(255,255,255,0.06)}}

.split-bg-container{{position:absolute;inset:0;background:#121212;z-index:1}}
.bg-img{{position:absolute;top:0;width:70%;height:100%;background-size:cover;background-position:center}}
.bg-left{{left:0;-webkit-mask-image:linear-gradient(to right,black 50%,transparent 100%);mask-image:linear-gradient(to right,black 50%,transparent 100%)}}
.bg-right{{right:0;-webkit-mask-image:linear-gradient(to left,black 50%,transparent 100%);mask-image:linear-gradient(to left,black 50%,transparent 100%)}}
.hud-arrow{{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:36px;height:36px;z-index:5;filter:drop-shadow(0 0 6px rgba(255,255,255,0.4))}}
.hud-arrow svg{{width:100%;height:100%}}

.content-layer{{position:absolute;inset:0;z-index:10;display:flex;flex-direction:column;justify-content:space-between;padding:20px 28px;background:linear-gradient(180deg,rgba(0,0,0,0.35) 0%,rgba(0,0,0,0) 35%,rgba(0,0,0,0.75) 100%)}}
.top-row{{display:flex;justify-content:space-between;align-items:flex-start}}
.badge{{font-size:11px;font-weight:800;padding:5px 14px;border-radius:8px;text-transform:uppercase;letter-spacing:1px;color:#fff}}
.timer-chip{{font-family:monospace;font-size:16px;font-weight:700;background:rgba(255,255,255,0.18);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);border:1px solid rgba(255,255,255,0.15);padding:6px 14px;border-radius:12px;color:{_C_TEXT}}}
.bottom-row{{display:flex;align-items:flex-end;gap:24px}}
.cur-info,.next-info{{display:flex;flex-direction:column;gap:2px}}
.meta-label{{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:rgba(255,255,255,0.5)}}
.cur-name{{font-size:28px;font-weight:900;color:#fff;text-shadow:0 2px 12px rgba(0,0,0,.6);line-height:1.1}}
.next-name{{font-size:16px;font-weight:700;color:rgba(255,255,255,0.75)}}
.divider{{flex:1;height:1px;background:rgba(255,255,255,0.15);align-self:flex-end;margin-bottom:8px}}
.footer{{padding:10px 28px;font-size:11px;color:{_C_MUTED};text-align:center}}
</style></head><body>
<div class="card">
<div class="title">地图轮换</div>
{br}
{ranked}
{ltm}
<div class="footer">Data: apexlegendsstatus.com · 背景: EA</div>
</div>
</body></html>"""


async def draw_map_rotation_card(rotation) -> bytes:
    html = _build_map_rotation_html(rotation)
    return await _render_card_sync(html, 720)


# ══════════════════════════════════════════
#  大师/猎杀数据卡片 (Moe Counter rule34)
# ══════════════════════════════════════════


def _build_predator_html(predator) -> str:
    platforms_order = ["PC", "PS4", "X1", "SWITCH"]
    plat_colors = {
        "PC": "#4DABF7",
        "PS4": "#4ECDC4",
        "X1": "#4CE5B1",
        "SWITCH": "#DA292A",
    }

    cells = ""
    for plat in platforms_order:
        pd = predator.platforms.get(plat)
        if not pd:
            continue
        color = plat_colors.get(plat, _C_TEXT)
        cap_img = _render_moe_number_base64(pd.predator_cap)
        masters_img = _render_moe_number_base64(pd.masters_and_preds)

        cap_html = (
            f'<img src="data:image/png;base64,{cap_img}" style="height:80px">'
            if cap_img
            else f'<span style="font-size:28px;font-weight:700;color:{_C_TEXT}">{pd.predator_cap:,}</span>'
        )
        masters_html = (
            f'<img src="data:image/png;base64,{masters_img}" style="height:80px">'
            if masters_img
            else f'<span style="font-size:28px;font-weight:700;color:{_C_MUTED}">{pd.masters_and_preds:,}</span>'
        )

        cells += f"""
            <div class="plat-cell">
                <div class="plat-name" style="color:{color}">{plat}</div>
                <div class="plat-metric">
                    <div class="metric-label">猎杀线</div>
                    {cap_html}
                </div>
                <div class="plat-divider"></div>
                <div class="plat-metric">
                    <div class="metric-label">大师人数</div>
                    {masters_html}
                </div>
            </div>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Microsoft YaHei','Noto Sans SC',sans-serif;background:transparent;color:{_C_TEXT};display:flex;justify-content:center;padding:24px}}
.card{{width:680px;background:{_C_CARD};border-radius:24px;overflow:hidden;box-shadow:0 10px 20px rgba(0,0,0,.4)}}
.header{{background:linear-gradient(135deg,{_C_CARD},{_C_CARD2});padding:20px 24px;border-bottom:1px solid {_C_OUTLINE}}}
.header h2{{font-size:22px;font-weight:800}}
.plat-grid{{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:{_C_OUTLINE}}}
.plat-cell{{background:{_C_CARD};padding:20px;text-align:center}}
.plat-name{{font-size:16px;font-weight:800;margin-bottom:12px}}
.plat-metric{{margin:10px 0}}
.metric-label{{font-size:12px;color:{_C_MUTED};margin-bottom:4px}}
.plat-divider{{height:1px;background:{_C_OUTLINE};margin:12px 0}}
.footer{{padding:12px 24px;border-top:1px solid {_C_OUTLINE};font-size:11px;color:{_C_MUTED};text-align:center}}
</style></head><body>
<div class="card">
<div class="header"><h2>大师 / 猎杀 数据</h2></div>
<div class="plat-grid">{cells}</div>
<div class="footer">Data: apexlegendsstatus.com</div>
</div>
</body></html>"""


async def draw_predator_card(predator) -> bytes:
    html = _build_predator_html(predator)
    return await _render_card_sync(html, 720)


def _build_lfg_mode_card() -> str:
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
.card{{width:420px;background:#2b2930;border-radius:28px;padding:24px}}
.title{{font-size:1.5rem;font-weight:700;margin-bottom:8px}}
.subtitle{{font-size:0.85rem;color:#938f99;margin-bottom:24px}}
.options{{display:flex;flex-direction:column;gap:12px}}
.opt{{padding:20px;border-radius:16px;background:#1c1b1f;border:1px solid #49454f;cursor:pointer;transition:all 0.2s ease}}
.opt:hover{{background:#36343b;border-color:#4f378b}}
.opt-title{{font-size:1rem;font-weight:700;margin-bottom:4px}}
.opt-sub{{font-size:0.8rem;color:#938f99}}
.footer{{margin-top:24px;text-align:center;font-size:0.75rem;color:#938f99}}
</style></head><body>
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

    rows = ""
    for e in entries:
        mode = e.get("mode", "ranked")
        rank_name = e.get("rank_name", "Unranked")
        rank_score = e.get("rank_score", 0)
        rank_img = e.get("rank_img", "")
        level = e.get("level", 0)
        kills = e.get("kills", 0)
        apex_name = e.get("apex_name", "Unknown")
        platform = e.get("platform", "PC")
        ladder_pos = e.get("rank_ladder_pos", 0) or 0
        state = e.get("state", "offline")

        rank_type = rank_name.lower().split(" ")[0] if rank_name else "unranked"
        text_color = rank_colors.get(rank_name, "#938f99")
        rank_display = _rank_zh(rank_name)
        if ladder_pos and rank_name in ("Predator", "Master"):
            rank_display += f" #{ladder_pos}"

        chip_class = "chip-highlight" if mode == "ranked" else ""
        chip_icon = '<span class="material-symbols-rounded" style="font-size:16px">workspace_premium</span>' if mode == "ranked" else ""
        mode_label = "排位赛" if mode == "ranked" else "娱乐匹配"

        state_map = {"online": "在线", "in_game": "游戏中", "offline": "离线"}
        state_text = state_map.get(state, "在线")
        dot_color = "#4CE5B1" if state in ("online", "in_game") else "#555"

        dot_icon = f'<span class="material-symbols-rounded" style="font-variation-settings:\'FILL\' 1;font-size:8px;color:{dot_color}">circle</span>'

        display_name = e.get("qq_name") or apex_name
        qq_avatar = e.get("qq_avatar", "")

        rows += f"""
        <div class="player-row">
            <div class="col-player">
                <img class="avatar" src="{qq_avatar}" alt="">
                <div class="player-info">
                    <div class="player-name" title="{display_name}">{display_name}</div>
                    <div class="status-tag">{dot_icon} {state_text} · {platform}</div>
                </div>
            </div>
            <div class="col-rank">
                <img class="rank-icon" src="{rank_img}" alt="{rank_name}">
                <div class="rank-text">
                    <span class="rank-score text-{rank_type}">{rank_score:,}</span>
                    <span class="rank-label">{rank_display}</span>
                </div>
            </div>
            <div class="col-wants">
                <div class="md3-chip {chip_class}">{chip_icon} {mode_label}</div>
            </div>
            <div class="col-data">{level}</div>
            <div class="col-data">{kills:,}</div>
        </div>"""

    if not rows:
        rows = '<div style="text-align:center;padding:40px;color:#938f99;">目前没有玩家在线发起组队</div>'

    font_family = "'Noto Sans SC','Roboto',sans-serif" if not _USE_LOCAL_FONTS else "sans-serif"
    fonts_link = "" if _USE_LOCAL_FONTS else '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&family=Roboto:wght@400;700&family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,0,0" rel="stylesheet">'
    ms_link = "" if _USE_LOCAL_FONTS else ""
    if _USE_LOCAL_FONTS:
        ms_link = '<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,0,0" rel="stylesheet">'

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
{fonts_link}
{ms_link}
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:transparent;color:#e6e1e5;font-family:{font_family};display:flex;justify-content:center;padding:32px 24px}}
.lfg-list{{width:100%;max-width:1280px;display:flex;flex-direction:column;gap:12px;background:#1e1e2e;padding:8px 0}}
.list-header{{display:grid;grid-template-columns:1.5fr 1fr 0.8fr 0.5fr 0.5fr;padding:0 32px 16px 32px;font-size:0.85rem;font-weight:500;color:#938f99;align-items:center;gap:16px}}
.list-header>div{{text-align:center}}
.list-header>div:first-child{{text-align:left}}
.list-header>div:nth-child(2){{text-align:left}}
.list-header>div:nth-child(3){{text-align:left}}
.player-row{{display:grid;grid-template-columns:1.5fr 1fr 0.8fr 0.5fr 0.5fr;align-items:center;background:#282838;padding:20px 32px;border-radius:20px;transition:all 0.2s ease;border:1px solid transparent;gap:16px}}
.player-row:hover{{background:#303042;transform:translateY(-2px);border-color:#49454f}}
.col-player{{display:flex;align-items:center;gap:18px}}
.avatar{{width:52px;height:52px;border-radius:14px;object-fit:cover;flex-shrink:0}}
.player-info{{display:flex;flex-direction:column;gap:4px}}
.player-name{{font-weight:700;font-size:1rem}}
.status-tag{{font-size:0.7rem;color:#938f99;display:flex;align-items:center;gap:4px}}
.col-rank{{display:flex;align-items:center;gap:14px}}
.rank-icon{{width:44px;height:44px;flex-shrink:0}}
.rank-text{{display:flex;flex-direction:column;gap:2px;white-space:nowrap}}
.rank-score{{font-weight:700;font-size:1.15rem}}
.rank-label{{font-size:0.78rem;color:#938f99}}
.col-wants{{display:flex;gap:8px;flex-wrap:wrap}}
.md3-chip{{background:#333537;color:#e3e2e6;padding:6px 14px;border-radius:10px;font-size:0.75rem;font-weight:500;display:flex;align-items:center;gap:6px;white-space:nowrap}}
.chip-highlight{{background:#633b48;color:#ffd8e4}}
.col-data{{font-weight:700;font-size:1.1rem;text-align:center;white-space:nowrap}}
.text-predator{{color:#ffb4ab}} .text-master{{color:#d0bcff}} .text-diamond{{color:#bac3ff}}
.text-platinum{{color:#99f1ff}} .text-gold{{color:#ffd966}} .text-silver{{color:#c0c0c0}}
.text-bronze{{color:#cd7f32}} .text-unranked{{color:#938f99}}
.footer{{padding:16px 32px 0 32px;font-size:11px;color:#555;display:flex;justify-content:space-between;border-top:1px solid #383850;margin-top:8px}}
</style></head><body>
<div class="lfg-list">
    <div class="list-header">
        <div>玩家</div><div>段位 / 分数</div><div>寻找队友</div><div>等级</div><div>击杀数</div>
    </div>
    {rows}
    <div class="footer">
        <span>Data: apexlegendsstatus.com</span>
        <span>auth.赤羽真白 · Apex Chiyuchan</span>
    </div>
</div>
</body></html>"""


async def draw_lfg_card(entries: list[dict]) -> bytes:
    html = _build_lfg_html(entries)
    return await _render_card_sync(html, 1328)


async def draw_lfg_mode_card() -> bytes:
    html = _build_lfg_mode_card()
    return await _render_card_sync(html, 420)


async def draw_text_card_pw(title: str, message: str, is_error: bool = False) -> bytes:
    import html as _html
    color = "#DA292A" if is_error else "#4CE5B1"
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
.header{{padding:24px 24px 0;font-size:20px;font-weight:800;color:{color}}}
.body{{padding:16px 24px 24px;font-size:15px;color:#938f99;line-height:1.6}}
.msg-line{{margin-top:4px}}
.footer{{padding:0 24px 20px;font-size:12px;color:#49454f;text-align:center}}
</style></head><body>
<div class="card">
  <div class="header">{_html.escape(title)}</div>
  <div class="body">{msg_lines}</div>
  <div class="footer">auth.赤羽真白 &middot; Apex Chiyuchan</div>
</div>
</body></html>"""
    return await _render_card_sync(html_str, 460)

