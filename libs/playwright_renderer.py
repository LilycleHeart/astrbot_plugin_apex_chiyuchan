"""Playwright WebKit HTML → PNG 渲染器 — Material Design 战绩卡片"""
from __future__ import annotations

import asyncio
from typing import Optional

from .config import RANK_COLORS
from .playwright_manager import run_with_page

# ── 卡片专用配色（与原版 ancallbelle_card.html 一致）──
_C_SURFACE = "#1a1c23"
_C_CARD = "#22242d"
_C_CARD2 = "#2a2d38"
_C_CARD3 = "#313542"
_C_TEXT = "#e0e1e6"
_C_MUTED = "#9ca0ae"
_C_OUTLINE = "#3e414d"
_C_GOLD = "#ffd700"
_C_DIAMOND = "#358de6"
_C_MASTER = "#9f35e6"
_C_PRED = "#e31b39"


# ── 汉化映射 ──
_RANK_ZH = {
    "Rookie": "菜鸟", "Bronze": "青铜", "Silver": "白银",
    "Gold": "黄金", "Platinum": "白金", "Diamond": "钻石",
    "Master": "大师", "Predator": "猎杀", "Unranked": "未定级",
}

_LEGEND_ZH = {
    "Wraith": "恶灵", "Horizon": "地平线", "Valkyrie": "瓦尔基里",
    "Pathfinder": "探路者", "Bloodhound": "寻血猎犬", "Gibraltar": "直布罗陀",
    "Lifeline": "命脉", "Mirage": "幻象", "Caustic": "侵蚀",
    "Octane": "动力小子", "Bangalore": "班加罗尔", "Wattson": "沃特森",
    "Crypto": "密客", "Revenant": "亡灵", "Loba": "罗芭",
    "Rampart": "兰伯特", "Fuse": "暴雷", "Seer": "先知",
    "Ash": "艾许", "Mad Maggie": "疯玛吉", "Newcastle": "纽卡斯尔",
    "Vantage": "万蒂奇", "Catalyst": "卡特莉丝", "Ballistic": "弹道",
    "Conduit": "导管", "Alter": "变幻",
}


def _rank_zh(name: str) -> str:
    major = name.split(" ")[0] if name else ""
    return _RANK_ZH.get(major, major)


def _rank_div_zh(div: int) -> str:
    return {0: "4", 1: "3", 2: "2", 3: "1"}.get(div, str(div))


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
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"{r},{g},{b},{alpha}"


def _roman(n: int) -> str:
    if n <= 0:
        return "?"
    return ["", "I", "II", "III", "IV"][min(n, 4)]


def _build_rank_dist(player_rank: str, player_top_pct: float, rank_dist_entries: list = None) -> str:
    """段位分布 — 仅显示玩家所在段位附近4个段位，含人数"""
    if rank_dist_entries:
        tiers = [(e.name, e.pct, e.color, e.count) for e in rank_dist_entries]
    else:
        tiers = [
            ("Rookie", 2.40, "#484852", 0), ("Bronze", 12.98, "#cd7f32", 0),
            ("Silver", 27.59, "#c0c0c0", 0), ("Gold", 35.54, "#ffd700", 0),
            ("Platinum", 17.72, "#4ECDC4", 0), ("Diamond", 3.36, "#358de6", 0),
            ("Master", 0.09, "#9f35e6", 0), ("Predator", 0.32, "#e31b39", 0),
        ]

    player_tier = player_rank.split(" ")[0] if player_rank else ""
    player_idx = next((i for i, t in enumerate(tiers) if t[0].lower() == player_tier.lower()), 0)

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
        arrow = '<span style="font-size:12px;color:{color};{weight}">◀</span>'.format(color=color, weight=weight) if is_player else ""
        bar_pct = min(pct, 50)
        count_str = f"{count:,}" if count else ""
        name_zh = _rank_zh(name)
        bars += (
            f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;padding:2px 24px;'
            f'{"background:rgba(149,83,211,0.06);border-radius:8px;" if is_player else ""}">'
            f'<span style="width:50px;text-align:right;font-size:12px;color:{color};{weight}">{name_zh}</span>'
            f'{arrow}'
            f'<div style="flex:1;height:6px;background:{_C_CARD3};border-radius:3px;overflow:hidden;">'
            f'<div style="height:100%;width:{bar_pct}%;background:{color};border-radius:3px;{"box-shadow:0 0 8px "+color if is_player else ""}"></div>'
            f'</div>'
            f'<span style="width:44px;font-size:11px;text-align:right;color:{_C_MUTED};{weight}">{pct:.2f}%</span>'
            f'<span style="width:64px;font-size:11px;text-align:right;color:{_C_MUTED};">{count_str}</span>'
            f'</div>'
        )
    footer = f'<div style="padding:4px 24px 8px;font-size:11px;color:{_C_MUTED};text-align:center;">'
    if total_players:
        footer += f'全服 {total_players:,} 名玩家中，Top {player_top_pct}%'
    else:
        footer += f'全服玩家中，Top {player_top_pct}%'
    footer += '</div>'
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
    rank_name = d.get("rank_name", "Unranked")
    rank_div = d.get("rank_div", 0)
    rank_score = d.get("rank_score", 0)
    rank_img = d.get("rank_img", d.get("rank_icon_url", ""))
    rank_top_pct = d.get("rank_top_pct", 0)
    rank_top_pct_global = d.get("rank_top_pct_global", rank_top_pct)
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

    display_name = f"{name} [{tag}]" if tag else name
    online_map = {"online": "在线", "offline": "离线", "in_game": "游戏中"}
    state_text = online_map.get(online, online)
    state_dot = "#4CE5B1" if online in ("online", "in_game") else "#555"
    prestige_str = f"P{prestige}" if prestige else ""
    rank_c = _rank_color(rank_name)
    top_als = f"{rank_top_pct}%"
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
            color = b.get("color", "#666")
            fw = "font-weight:700;" if tier == "master" else ""
            chips.append(
                f'<span style="display:inline-flex;align-items:center;gap:4px;padding:4px 10px;'
                f'border-radius:20px;font-size:12px;font-weight:600;{fw}'
                f'background:rgba({_hex_to_rgba(color,0.15)});color:{color};'
                f'border:1px solid rgba({_hex_to_rgba(color,0.3)});">'
                f'<img src="{url}" style="width:28px;height:28px;vertical-align:middle;">{s}</span>'
            )
        badge_rows += (
            f'<div style="display:flex;flex-wrap:wrap;gap:8px;padding:0 24px 12px;'
            f'justify-content:center;">{"".join(chips)}</div>'
        )

    spec_rows = ""
    if special_badges:
        chips = []
        for b in special_badges:
            nm = b.get("name", "")
            color = b.get("color", "#666")
            chips.append(
                f'<span style="display:inline-flex;align-items:center;gap:4px;padding:6px 14px;'
                f'border-radius:20px;font-size:12px;font-weight:600;'
                f'background:rgba({_hex_to_rgba(color,0.12)});color:{color};'
                f'border:1px solid rgba({_hex_to_rgba(color,0.25)});">'
                f'{nm}</span>'
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
            top = " background:linear-gradient(135deg,rgba(149,83,211,0.08),transparent);" if i == 0 else ""
            kc = "#9553d3" if i == 0 else _C_TEXT
            bd = "border:2px solid #9553d3;" if i == 0 else "border:2px solid #3e414d;"
            it = f'<img src="{icon_url}" style="width:36px;height:36px;border-radius:50%;object-fit:cover;{bd}">' if icon_url else '<div style="width:36px;height:36px;border-radius:50%;background:#313542;"></div>'
            rows.append(
                f'<div style="display:flex;align-items:center;gap:12px;padding:10px 12px;'
                f'border-radius:8px;margin-bottom:2px;{top}">'
                f'{it}<span style="flex:1;font-size:14px;font-weight:500;">{_legend_zh(leg["name"])}</span>'
                f'<span style="font-size:16px;font-weight:700;color:{kc};">{leg.get("kills",0):,}</span>'
                f'</div>'
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
                f'<span style="font-size:11px;color:{_C_MUTED};display:block;">{s.get("name","")}</span>'
                f'<span style="font-size:14px;font-weight:500;">{s.get("value","")}</span>'
                f'</span>'
            )
        ic = f'<img src="{si}" style="width:36px;height:36px;border-radius:50%;object-fit:cover;border:2px solid #3e414d;">' if si else ""
        selected_html = f"""
<div style="font-size:14px;font-weight:600;color:{_C_MUTED};text-transform:uppercase;letter-spacing:2px;padding:16px 24px 8px;">当前选用</div>
<div style="padding:0 24px 8px;display:flex;align-items:center;gap:12px;">
{ic}<span style="font-size:16px;font-weight:600;">{_legend_zh(sn)}</span>
<span style="display:flex;gap:8px;margin-left:auto;">{st_html}</span>
</div>"""

    # ── 段位分布参考条 ──
    rank_dist = _build_rank_dist(rank_name, rank_top_pct, rank_dist_entries)

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
  background:{_C_SURFACE};color:{_C_TEXT};
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
.level-num{{
  font-size:32px;font-weight:800;
  background:linear-gradient(135deg,{_C_PRED},#ff6b6b);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
  background-clip:text
}}
.level-bar{{flex:1;height:6px;background:{_C_CARD3};border-radius:3px;overflow:hidden;margin-left:12px}}
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
    <div class="player-meta">{'aka ' + alias + ' · ' if alias else ''}UID: {uid}</div>
    <div class="platform-tag"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{state_dot};margin-right:4px;"></span>{platform} · {state_text}</div>
  </div>
</div>

<div class="rank-section">
  <img class="rank-img" src="{rank_img}">
  <div>
    <div class="rank-tier">{_rank_zh(rank_name)}{_rank_div_zh(rank_div)}</div>
    <div class="rank-rp">{rank_score:,} RP{rp_delta_html}</div>
  </div>
  <div class="rank-stats">
    <div><div class="rank-stat-val">{top_als}</div><div class="rank-stat-label">Top (ALS)</div></div>
    <div><div class="rank-stat-val">{top_global}</div><div class="rank-stat-label">Top (Global)</div></div>
  </div>
</div>

<div class="level-row">
  <div class="level-num">{level}</div>
  <div style="font-size:12px;color:{_C_MUTED};">{prestige_str + ' · ' if prestige_str else ''}{level_pct}% to next</div>
  <div class="level-bar"><div class="level-fill"></div></div>
</div>

<div class="stat-grid">
  <div class="stat-chip"><div class="stat-val highlight">{kills:,}</div><div class="stat-lbl">生涯击杀</div></div>
  <div class="stat-chip"><div class="stat-val">{damage:,}</div><div class="stat-lbl">BR 总伤害</div></div>
  <div class="stat-chip"><div class="stat-val">{wins_display}</div><div class="stat-lbl">BR 胜场</div></div>
</div>

{selected_html}

<div style="font-size:14px;font-weight:600;color:{_C_MUTED};text-transform:uppercase;letter-spacing:2px;padding:16px 24px 8px;">段位分布参考</div>
{rank_dist}

<div style="font-size:14px;font-weight:600;color:{_C_MUTED};text-transform:uppercase;letter-spacing:2px;padding:16px 24px 8px;">常用英雄</div>
{legends_html if legends_html else f'<div style="padding:0 24px 16px;color:{_C_MUTED};font-size:13px;">暂无英雄数据</div>'}

{badge_section}

<div class="footer">
  <span>Data: <span style="color:{_C_PRED};">Apex Legends Status</span></span>
  <span>UID: {uid}</span>
</div>

</div>
</body></html>"""


# ══════════════════════════════════════════
#  Moe Counter 数字 → Base64 (rule34)
# ══════════════════════════════════════════

def _render_moe_number_base64(number: int) -> str:
    import base64, io
    from PIL import Image
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

async def _render_card_sync(html: str, width: int) -> bytes:
    async with run_with_page(viewport={"width": width, "height": 100}, device_scale_factor=2) as page:
        await page.set_content(html, wait_until="networkidle", timeout=15000)
        card_height = await page.evaluate(
            "() => document.querySelector('.card')?.offsetHeight || 600"
        )
        await page.set_viewport_size({"width": width, "height": card_height + 48})
        return await page.screenshot(full_page=False, type="png")


async def draw_profile_card(data: dict) -> bytes:
    """根据 dict 渲染战绩卡片 PNG（playwright WebKit）"""
    html = _build_stats_html(**data)
    return await _render_card_sync(html, 720)


# ══════════════════════════════════════════
#  服务器状态卡片
# ══════════════════════════════════════════

def _build_server_status_html(servers: list) -> str:
    rows = ""
    for s in servers:
        dot_color = "#4CE5B1" if s.is_up else "#E31B39" if s.status.upper() == "DOWN" else "#FFD700"
        status_color = dot_color
        rt = f"{s.response_time}ms" if s.response_time else "--"
        rows += f"""
            <div class="server-row">
                <span class="dot" style="background:{dot_color}"></span>
                <span class="server-name">{s.display_name}</span>
                <span class="server-status" style="color:{status_color}">{s.status_text}</span>
                <span class="server-rt">{rt}</span>
            </div>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Microsoft YaHei','Noto Sans SC',sans-serif;background:{_C_SURFACE};color:{_C_TEXT};display:flex;justify-content:center;padding:24px}}
.card{{width:680px;background:{_C_CARD};border-radius:24px;overflow:hidden;box-shadow:0 10px 20px rgba(0,0,0,.4)}}
.header{{background:linear-gradient(135deg,{_C_CARD},{_C_CARD2});padding:20px 24px;border-bottom:1px solid {_C_OUTLINE}}}
.header h2{{font-size:22px;font-weight:800}}
.server-row{{display:flex;align-items:center;padding:14px 24px;border-bottom:1px solid {_C_OUTLINE};gap:12px}}
.server-row:last-child{{border-bottom:none}}
.dot{{width:10px;height:10px;border-radius:50%;flex-shrink:0}}
.server-name{{flex:1;font-size:14px;font-weight:500}}
.server-status{{font-size:13px;font-weight:700;width:60px;text-align:center}}
.server-rt{{font-size:13px;color:{_C_MUTED};width:64px;text-align:right}}
.footer{{padding:12px 24px;border-top:1px solid {_C_OUTLINE};font-size:11px;color:{_C_MUTED};text-align:center}}
</style></head><body>
<div class="card">
<div class="header"><h2>Apex 服务器状态</h2></div>
{rows}
<div class="footer">Data: apexlegendsstatus.com</div>
</div>
</body></html>"""


async def draw_server_status_card(server_status) -> bytes:
    html = _build_server_status_html(server_status.servers)
    return await _render_card_sync(html, 720)


# ══════════════════════════════════════════
#  地图轮换卡片
# ══════════════════════════════════════════

_MAP_BG = {
    "Kings Canyon": "https://drop-assets.ea.com/images/2106fDsHrzPvx15EpUCHSe/fff15d2bdc1d278fe8b762ec81db10f6/apex-media-maps-kings-canyon-xl-l-m1.jpg",
    "World's Edge": "https://drop-assets.ea.com/images/4suIbEk14qVTpGEOh0Zt9Q/72c2062cd32f22447beff2b5ed4ed58f/apex-media-maps-worlds-edge-xl-l-m.jpg",
    "Olympus": "https://drop-assets.ea.com/images/1nbiZcYKD5exXWgecxZWNf/8af1c5a04b16e7c4e169dd421ada34ad/Apex_Maps-Olympus-1x1.jpg",
    "Storm Point": "https://drop-assets.ea.com/images/1ZnzgvuwhHfVgbNGphL7OR/0e76b2875665ffc375f2d95e28dafd44/apex-media-maps-storm-point-xl-l-m.jpg",
    "Broken Moon": "https://drop-assets.ea.com/images/3L05Q850J60jdpnzaMqi6n/b6ab5093e5bff08a84327e929b4ca2e0/apex-media-maps-broken-moon-xl-l-m.jpg",
    "E-District": "https://drop-assets.ea.com/images/6NXmn5uRFXPffRFWd64YjD/808cd2ad017acdf363b16274357d11df/apex-media-maps-e-district-xl.jpg",
}

_MAP_ZH = {
    "Kings Canyon": "王者峽谷", "World's Edge": "世界邊緣", "Olympus": "奧林匹斯",
    "Storm Point": "暴風點", "Broken Moon": "殘月", "E-District": "電流區",
}


def _map_bg_style(map_name: str) -> str:
    url = _MAP_BG.get(map_name, "")
    if url:
        return f"background:linear-gradient(rgba(26,28,35,0.75),rgba(26,28,35,0.85)),url({url}) center/cover no-repeat;"
    return ""


def _build_map_rotation_html(rotation) -> str:
    def _map_row(label: str, current, next_, mode_label: str) -> str:
        cur_map = current.map if current else "--"
        cur_timer = current.remaining_timer if current and current.remaining_timer else ""
        next_map = next_.map if next_ and next_.map else "--"
        timer_html = f'<span class="timer">{cur_timer}</span>' if cur_timer else ""
        cur_zh = _MAP_ZH.get(cur_map, cur_map)
        next_zh = _MAP_ZH.get(next_map, next_map)
        bg = _map_bg_style(cur_map)
        return f"""
            <div class="map-section" style="{bg}">
                <div class="map-header">{mode_label} {label}</div>
                <div class="map-row">
                    <span class="map-label">当前</span>
                    <span class="map-name">{cur_zh}</span>
                    {timer_html}
                </div>
                <div class="map-row next">
                    <span class="map-label">下一张</span>
                    <span class="map-name">{next_zh}</span>
                </div>
            </div>"""

    br_html = _map_row("", rotation.br_current, rotation.br_next, "🎮 匹配")
    ranked_html = _map_row("", rotation.ranked_current, rotation.ranked_next, "🏆 排位")

    ltm_html = ""
    if rotation.ltm_current and rotation.ltm_current.event_name:
        ltm_html = f"""
            <div class="map-section">
                <div class="map-header">⚡ 限时模式  {rotation.ltm_current.event_name} · {rotation.ltm_current.map}</div>
            </div>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Microsoft YaHei','Noto Sans SC',sans-serif;background:{_C_SURFACE};color:{_C_TEXT};display:flex;justify-content:center;padding:24px}}
.card{{width:680px;background:{_C_CARD};border-radius:24px;overflow:hidden;box-shadow:0 10px 20px rgba(0,0,0,.4)}}
.header{{background:linear-gradient(135deg,{_C_CARD},{_C_CARD2});padding:20px 24px;border-bottom:1px solid {_C_OUTLINE}}}
.header h2{{font-size:22px;font-weight:800}}
.map-section{{padding:20px 24px;border-bottom:1px solid {_C_OUTLINE};min-height:120px}}
.map-section:last-child{{border-bottom:none}}
.map-header{{font-size:16px;font-weight:700;margin-bottom:10px;color:{_C_GOLD}}}
.map-row{{display:flex;align-items:center;gap:12px;padding:4px 0}}
.map-label{{font-size:13px;color:{_C_MUTED};width:48px}}
.map-name{{font-size:18px;font-weight:700;text-shadow:0 2px 8px rgba(0,0,0,.6)}}
.map-row.next .map-name{{font-size:14px;font-weight:400;color:{_C_MUTED};text-shadow:none}}
.timer{{margin-left:auto;font-size:12px;color:{_C_DIAMOND}}}
.footer{{padding:12px 24px;border-top:1px solid {_C_OUTLINE};font-size:11px;color:{_C_MUTED};text-align:center}}
</style></head><body>
<div class="card">
<div class="header"><h2>地图轮换</h2></div>
{br_html}
{ranked_html}
{ltm_html}
<div class="footer">Data: apexlegendsstatus.com · 背景图: EA</div>
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
    plat_colors = {"PC": "#4DABF7", "PS4": "#4ECDC4", "X1": "#4CE5B1", "SWITCH": "#DA292A"}

    cells = ""
    for plat in platforms_order:
        pd = predator.platforms.get(plat)
        if not pd:
            continue
        color = plat_colors.get(plat, _C_TEXT)
        cap_img = _render_moe_number_base64(pd.predator_cap)
        masters_img = _render_moe_number_base64(pd.masters_and_preds)

        cap_html = f'<img src="data:image/png;base64,{cap_img}" style="height:80px">' if cap_img else f'<span style="font-size:28px;font-weight:700;color:{_C_TEXT}">{pd.predator_cap:,}</span>'
        masters_html = f'<img src="data:image/png;base64,{masters_img}" style="height:80px">' if masters_img else f'<span style="font-size:28px;font-weight:700;color:{_C_MUTED}">{pd.masters_and_preds:,}</span>'

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
body{{font-family:'Microsoft YaHei','Noto Sans SC',sans-serif;background:{_C_SURFACE};color:{_C_TEXT};display:flex;justify-content:center;padding:24px}}
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
