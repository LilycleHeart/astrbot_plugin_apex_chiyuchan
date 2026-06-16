"""小赤羽 — Apex Legends QQ Bot 插件入口"""

from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.core.message.message_event_result import MessageChain
from astrbot.api.message_components import Image, Plain
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .libs.apex_client import ApexClient
from .libs.database import Database
from .libs import image_renderer as renderer
from .libs.als_scraper import fetch_badges, fetch_lfg_stats, search_players


async def _send_status_card(context, sid: str, text: str, wrapper):
    """渲染并推送服务器状态卡片，发送失败自动降级为纯文字"""
    try:
        img = await renderer.draw_server_status_card(wrapper)
    except Exception:
        img = None
    if img:
        try:
            await context.send_message(sid, MessageChain([Plain(text), Image.fromBytes(img)]))
        except Exception:
            await context.send_message(sid, MessageChain([Plain(text)]))
    else:
        await context.send_message(sid, MessageChain([Plain(text)]))


@register(
    "apex_chiyuchan",
    "小赤羽",
    "Apex 战绩查询 / 地图轮换 / 大师数据 / 组队系统",
    "1.1.0",
)
class XiaoChiyu(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        api_key = config.get("apex_api_key", "")
        self.apex = ApexClient(api_key)
        self.db = Database()

        self._temp_dir = Path(get_astrbot_data_path()) / "temp" / "apex_chiyuchan"
        self._temp_dir.mkdir(parents=True, exist_ok=True)

        self._last_search: dict[str, list[dict]] = {}
        self._profile_cache: dict[str, dict] = {}
        self._lfg_entries: dict[str, dict] = {}
        self._monitor_task: asyncio.Task | None = None

        from .libs.config import preload_fonts
        preload_fonts()

        if config.get("use_local_fonts", False):
            try:
                from .libs.playwright_renderer import set_use_local_fonts
                set_use_local_fonts(True)
            except Exception:
                pass

        self._fire_and_forget(self._on_init(), "DB初始化")

    def _fire_and_forget(self, coro, name: str = ""):
        """后台任务，自动捕获异常并日志"""

        async def _wrapper():
            try:
                await coro
            except Exception as e:
                tag = f" ({name})" if name else ""
                logger.error(f"[小赤羽] 后台任务{tag}异常: {e}")

        asyncio.create_task(_wrapper())

    async def _on_init(self):
        await self.db.init()
        from .libs.image_renderer import _download_moe_digits_async
        from .libs.ttl_cache import start_cleaner
        from .libs.playwright_manager import get_browser

        asyncio.create_task(get_browser())
        asyncio.create_task(_download_moe_digits_async())
        start_cleaner()
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def terminate(self):
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
        await self.apex.close()
        await self.db.close()
        from .libs.playwright_manager import close_browser
        from .libs.http_client import close_clients

        await close_browser()
        await close_clients()

    async def _save_temp(self, img_bytes: bytes, suffix: str = ".png") -> str:
        path = self._temp_dir / f"{uuid.uuid4()}{suffix}"
        path.write_bytes(img_bytes)
        return str(path)

    @staticmethod
    def _calc_global_pct(rank_name: str, rank_div: int, rank_dist) -> float | None:
        if not rank_dist or not rank_dist.entries:
            return None
        total = sum(e.count for e in rank_dist.entries if e.count)
        if total == 0:
            return None
        major = rank_name.split(" ")[0] if rank_name else ""
        above = 0
        found = False
        for e in rank_dist.entries:
            if e.name == major:
                found = True
                continue
            if found:
                above += e.count
        tier_count = next((e.count for e in rank_dist.entries if e.name == major), 0)
        div = min(rank_div, 3)
        above += tier_count * (3 - div) / 4
        return round(above / total * 100, 2)

    def _extract_at_target(self, args: str) -> tuple[str | None, str]:
        """从参数字符串中提取 @QQ，返回 (target_qq, cleaned_args)。"""
        m = re.search(r'\[CQ:at,qq=(\d+)\]', args)
        if m:
            target = m.group(1)
            cleaned = args.replace(m.group(0), "").strip()
            return target, cleaned
        m = re.search(r'@(\d+)', args)
        if m:
            target = m.group(1)
            cleaned = args.replace(m.group(0), "").strip()
            return target, cleaned
        return None, args

    async def _resolve_admin_target(
        self, event: AstrMessageEvent, args: str
    ) -> tuple[str | None, str, str | None]:
        """解析命令中的 @目标。管理员可为他人操作。
        Returns (target_qq, cleaned_args, error_msg).
        若 non-admin 使用 @目标，返回 (None, cleaned_args, 错误消息)。
        """
        target_qq, cleaned = self._extract_at_target(args)
        if target_qq and not event.is_admin():
            return None, cleaned, "只有管理员才能为他人操作"
        return target_qq or event.get_sender_id(), cleaned, None

    async def _get_badges_cached(self, uid: str, platform: str) -> dict:
        """获取徽章数据。媒体资源（赛季/特殊徽章）首次爬取后永久存 DB，不再重爬。
        排名/击杀等变化数据来自 API + 计算，不走 DB 缓存。"""
        cached = await self.db.get_badge_cache(uid, platform)
        if cached:
            return cached["data"]
        badges = await fetch_badges(uid, platform)
        if badges.get("seasons") or badges.get("special"):
            await self.db.set_badge_cache(uid, platform, badges)
        return badges

    async def _send_card(
        self, event: AstrMessageEvent, img_bytes: bytes, suffix: str = ".png", **kwargs
    ):
        """直接发送图片消息"""
        path = await self._save_temp(img_bytes, suffix)
        yield event.image_result(path)

    # ═══════════════════════════════════════════════
    #  绑定 / 解绑
    # ═══════════════════════════════════════════════

    @filter.command("bind", alias={"绑定"})
    async def cmd_bind(self, event: AstrMessageEvent):
        """绑定 Apex 账号 — /bind <玩家名> [平台] (@目标 仅管理员)"""
        msg = event.get_message_str().strip()
        rest = msg.split(maxsplit=1)[1] if " " in msg else ""
        qq_id, rest, err = await self._resolve_admin_target(event, rest)
        if err:
            yield event.plain_result(err)
            return
        parts = rest.split()
        platform = "PC"
        if parts and parts[-1].upper() in ("PC", "PS4", "X1"):
            platform = parts.pop().upper()
        name = " ".join(parts)
        if not name:
            yield event.plain_result("请提供玩家名，例如 /bind Liliumcordis")
            return

        if name.strip().isdigit():
            idx = int(name.strip())
            cached = self._last_search.get(qq_id, [])
            if 1 <= idx <= len(cached):
                r = cached[idx - 1]
                plat = r.get("platform", platform)
                await self.db.upsert_user(qq_id, r["uid"], r["name"], plat)
                img = await renderer.draw_bind_card(r["uid"], r["name"], plat)
                async for r2 in self._send_card(event, img):
                    yield r2
                return

        results = await search_players(name, platform)
        if results:
            if len(results) == 1:
                r = results[0]
                await self.db.upsert_user(qq_id, r["uid"], r["name"], platform)
                img = await renderer.draw_bind_card(r["uid"], r["name"], platform)
                async for r2 in self._send_card(event, img):
                    yield r2
                return
            self._last_search[qq_id] = results
            hint = f"共 {len(results)} 个结果，请使用 /bind 数字 选择"
            img = await renderer.draw_player_list_card(results, hint)
            async for r in self._send_card(event, img):
                yield r
            return

        # ALS搜不到，回退API
        api_results = await self.apex.name_to_uid_all(name, platform)
        if not api_results:
            img = await renderer.draw_text_card(
                "绑定失败", f"找不到玩家 '{name}'", is_error=True
            )
            async for r in self._send_card(event, img):
                yield r
            return
        if len(api_results) > 1:
            lines = [f"找到 {len(api_results)} 个匹配玩家，请用 /bind_uid <UID> 绑定:"]
            for r in api_results:
                lines.append(f"  {r.name} — UID: {r.uid}")
            img = await renderer.draw_text_card(
                "多个匹配", "\n".join(lines), is_error=False
            )
            async for r in self._send_card(event, img):
                yield r
            return
        api_result = api_results[0]

        expected = name.strip().lower().replace(" ", "")
        actual = api_result.name.lower().replace(" ", "")
        if expected not in actual and actual not in expected:
            img = await renderer.draw_text_card(
                "名字可能不匹配",
                f"搜索 '{name}' 返回了 '{api_result.name}' (UID: {api_result.uid})\n"
                f"绑定将继续。如果不对，请用 /bind_uid {api_result.uid} 重新绑定",
                is_error=False,
            )
            async for r in self._send_card(event, img):
                yield r

        await self.db.upsert_user(qq_id, api_result.uid, api_result.name, platform)
        img = await renderer.draw_bind_card(api_result.uid, api_result.name, platform)
        async for r in self._send_card(event, img):
            yield r

    @filter.command("bind_uid", alias={"绑定UID"})
    async def cmd_bind_uid(self, event: AstrMessageEvent, uid: str, platform: str = "PC"):
        """直接通过 UID 绑定 — /bind_uid <UID> [平台] [@目标 仅管理员]"""
        if platform.upper() not in ("PC", "PS4", "X1"):
            yield event.plain_result("平台仅支持 PC / PS4 / X1")
            return
        platform = platform.upper()
        msg = event.get_message_str().strip()
        _, rest, err = await self._resolve_admin_target(event, msg)
        if err:
            yield event.plain_result(err)
            return
        qq_id, _, _ = await self._resolve_admin_target(event, msg)
        stats = await self.apex.get_stats(uid, platform)
        if not stats:
            yield event.plain_result(f"找不到 UID '{uid}'")
            return
        await self.db.upsert_user(qq_id, uid, stats.name, platform)
        img = await renderer.draw_bind_card(uid, stats.name, platform)
        async for r in self._send_card(event, img):
            yield r

    @filter.command("unbind", alias={"解绑"})
    async def cmd_unbind(self, event: AstrMessageEvent):
        """解绑 Apex 账号 — /unbind [@目标 仅管理员]"""
        msg = event.get_message_str().strip()
        rest = msg.split(maxsplit=1)[1] if " " in msg else ""
        qq_id, _, err = await self._resolve_admin_target(event, rest)
        if err:
            yield event.plain_result(err)
            return
        user = await self.db.get_user(qq_id)
        if not user:
            yield event.plain_result("你还没有绑定 Apex 账号")
            return
        await self.db.delete_user(qq_id)
        img = await renderer.draw_unbind_card()
        async for r in self._send_card(event, img):
            yield r

    # ═══════════════════════════════════════════════
    #  战绩查询
    # ═══════════════════════════════════════════════

    @filter.command("stats", alias={"战绩", "查询", "profile", "卡片"})
    async def cmd_stats(self, event: AstrMessageEvent):
        """查询 Apex 战绩 — /stats [玩家名或UID]"""
        qq_id = event.get_sender_id()
        msg = event.get_message_str().strip()
        name = msg.split(maxsplit=1)[1] if " " in msg else ""

        if name:
            # 处理 @提及：查对方绑定
            at_match = re.search(r'\[CQ:at,qq=(\d+)\]', name) or re.search(r'@(\d+)', name)
            if at_match:
                target_qq = at_match.group(1)
                target_user = await self.db.get_user(target_qq)
                if not target_user:
                    img = await renderer.draw_text_card("查询失败", "对方未绑定 Apex 账号", is_error=True)
                    async for r in self._send_card(event, img):
                        yield r
                    return
                uid = target_user["uid"]
                platform = target_user.get("platform", "PC")
            elif name.strip().isdigit():
                idx = int(name.strip())
                cached = self._last_search.get(qq_id, [])
                if 1 <= idx <= len(cached):
                    r = cached[idx - 1]
                    uid = r["uid"]
                    platform = r.get("platform", "PC")
                else:
                    uid = name.strip()
                    platform = "PC"
            else:
                # 优先 ALS 搜索（比 API 准确）
                search_results = await search_players(name.strip())
                if search_results:
                    if len(search_results) == 1:
                        uid = search_results[0]["uid"]
                        platform = search_results[0].get("platform", "PC")
                    else:
                        self._last_search[qq_id] = search_results
                        hint = f"共 {len(search_results)} 个结果，请使用 /stats 数字 选择"
                        img = await renderer.draw_player_list_card(search_results, hint)
                        async for r in self._send_card(event, img):
                            yield r
                        return
                else:
                    # ALS搜不到，回退API
                    api_results = await self.apex.name_to_uid_all(name.strip())
                    if not api_results:
                        img = await renderer.draw_text_card(
                            "查询失败", f"找不到玩家 '{name}'", is_error=True
                        )
                        async for r in self._send_card(event, img):
                            yield r
                        return
                    uid = api_results[0].uid
                    platform = "PC"
                platform = "PC"
        else:
            user = await self.db.get_user(qq_id)
            if not user:
                img = await renderer.draw_text_card(
                    "未绑定", "请先使用 /bind <玩家名> 绑定账号", is_error=True
                )
                async for r in self._send_card(event, img):
                    yield r
                return
            uid = user["uid"]
            platform = user["platform"]

        # ── API 获取基础数据 + 网站抓取徽章 + 段位分布（并行）──
        stats_task = self.apex.get_stats(uid, platform)
        badges_task = self._get_badges_cached(uid, platform)
        rankdist_task = self.apex.get_rank_distribution()
        stats, badges, rank_dist = await asyncio.gather(
            stats_task, badges_task, rankdist_task
        )

        if not stats:
            img = await renderer.draw_text_card(
                "查询失败", "无法获取战绩数据", is_error=True
            )
            async for r in self._send_card(event, img):
                yield r
            return

        # ── RP 变化（距上次查询）──
        rp_delta = await self.db.get_rp_delta(stats.uid, platform, stats.rank_score)
        self._fire_and_forget(self.db.save_rp(stats.uid, platform, stats.rank_score), "保存RP")

        # ── 构建渲染数据 ──
        qq_avatar = f"https://q1.qlogo.cn/g?b=qq&nk={qq_id}&s=640"
        _lv = badges.get("level") or stats.level
        _pr = badges.get("prestige") or stats.prestige
        global_pct = badges.get("rankTopPct") or self._calc_global_pct(stats.rank_name, stats.rank_div, rank_dist) or stats.rank_top_pct
        rank_ladder_pos = stats.rank_ladder_pos or badges.get("rankPcPos") or badges.get("rankPos", 0)
        profile_data = {
            "name": stats.name,
            "tag": stats.tag,
            "uid": stats.uid,
            "avatar_url": qq_avatar,
            "platform": platform,
            "online": stats.state,
            "level": _pr * 500 + _lv if _pr else _lv,
            "level_pct": stats.to_next_level_pct,
            "prestige": _pr,
            "rank_name": stats.rank_name,
            "rank_div": stats.rank_div,
            "rank_score": stats.rank_score,
            "rank_img": stats.rank_img,
            "rank_top_pct": stats.rank_top_pct,
            "rank_top_pct_global": global_pct,
            "rank_ladder_pos": rank_ladder_pos,
            "rp_delta": rp_delta,
            "kills": badges.get("kills", 0) or stats.kills,
            "damage": stats.damage,
            "wins": stats.wins,
            "kd": stats.kd,
            "top_legends": [
                {
                    "name": leg["name"],
                    "kills": leg["kills"],
                    "icon_url": leg.get("icon", ""),
                }
                for leg in stats.top_legends[:3]
            ],
            "selected_legend": stats.selected_legend_data,
            "season_badges": badges.get("seasons", []),
            "special_badges": badges.get("special", []),
            "rank_dist_entries": rank_dist.entries if rank_dist else None,
        }

        self._profile_cache[qq_id] = {
            "uid": stats.uid,
            "name": stats.name,
            "platform": platform,
            "rank_name": stats.rank_name,
            "rank_div": stats.rank_div,
            "rank_score": stats.rank_score,
            "rank_img": stats.rank_img,
            "rank_ladder_pos": rank_ladder_pos,
            "level": _pr * 500 + _lv if _pr else _lv,
            "prestige": _pr,
            "kills": badges.get("kills", 0) or stats.kills,
            "avatar_url": qq_avatar,
        }

        logger.info(
            f"[DEBUG] rank_name={profile_data.get('rank_name')} "
            f"rank_div={profile_data.get('rank_div')} "
            f"rank_img={profile_data.get('rank_img')[:60] if profile_data.get('rank_img') else 'EMPTY'}"
        )
        img = await renderer.draw_profile_card(profile_data)
        async for r in self._send_card(event, img):
            yield r

    # ═══════════════════════════════════════════════
    #  LFG 找队友
    # ═══════════════════════════════════════════════

    async def _refresh_lfg_entry(self, u: dict, group_id: str, rank_dist, bot) -> dict | None:
        """获取或刷新 LFG 列表条目。DB 中 kills/level 等静态数据在 30min 内直接使用，否则重爬 ALS（在线状态始终实时）。"""
        from datetime import datetime, timedelta

        now = datetime.now()
        stats_updated = u.get("stats_updated_at")
        fresh = False
        if stats_updated:
            try:
                updated = datetime.strptime(stats_updated, "%Y-%m-%d %H:%M:%S")
                if (now - updated) < timedelta(minutes=30):
                    fresh = True
            except ValueError:
                pass

        # QQ 名字
        qq_name = u.get("qq_name", "") or ""
        if not qq_name:
            try:
                info = await bot.call_action("get_stranger_info", user_id=int(u["qq_id"]), no_cache=False)
                qq_name = info.get("nickname", "") or info.get("nick", "")
                if qq_name:
                    await self.db.update_lfg_qq_name(u["qq_id"], group_id, qq_name)
            except Exception:
                pass

        if fresh:
            stats = await self.apex.get_stats(u["uid"], u["platform"])
            state = stats.state if stats else u.get("state", "offline")
            rank_img = u.get("rank_img", "") or (stats.rank_img if stats else "")
            lvl_raw = u.get("level", 0) or 0
            pr_raw = u.get("prestige", 0) or 0
            total_lvl = pr_raw * 500 + lvl_raw if pr_raw else lvl_raw
            gpct = self._calc_global_pct(
                u.get("rank_name", ""), 0, rank_dist
            ) or (stats.rank_top_pct if stats else 0)
            return {
                "qq_id": u["qq_id"], "qq_name": qq_name or "",
                "qq_avatar": f"https://q1.qlogo.cn/g?b=qq&nk={u['qq_id']}&s=640",
                "mode": u["mode"], "apex_name": u["name"],
                "platform": u["platform"],
                "rank_name": u.get("rank_name", ""),
                "rank_score": u.get("rank_score", 0),
                "rank_img": rank_img,
                "rank_top_pct_global": gpct,
                "rank_ladder_pos": u.get("rank_pos", 0),
                "level": total_lvl, "kills": u.get("kills", 0),
                "state": state,
            }

        # stale — 重新爬取
        stats = await self.apex.get_stats(u["uid"], u["platform"])
        if not stats:
            return None
        bind_user = await self.db.get_user(u["qq_id"])
        als_lookup = bind_user["uid"] if bind_user else u["uid"]
        badges = await fetch_lfg_stats(als_lookup, u["platform"])
        gpct = badges.get("rankTopPct") or self._calc_global_pct(stats.rank_name, stats.rank_div, rank_dist) or stats.rank_top_pct
        lvl_raw = badges.get("level") or stats.level
        pr_raw = badges.get("prestige") or stats.prestige
        total_lvl = pr_raw * 500 + lvl_raw if pr_raw else lvl_raw
        rp_pos = stats.rank_ladder_pos or badges.get("rankPcPos") or badges.get("rankPos", 0)
        await self.db.upsert_lfg_user(
            u["qq_id"], group_id, u["uid"], stats.name, u["platform"], u["mode"],
            qq_name=qq_name or "",
            kills=badges.get("kills", 0) or stats.kills,
            level=lvl_raw, prestige=pr_raw,
            rank_pos=rp_pos,
            rank_name=stats.rank_name, rank_score=stats.rank_score,
            rank_img=stats.rank_img, state=stats.state,
        )
        return {
            "qq_id": u["qq_id"], "qq_name": qq_name or "",
            "qq_avatar": f"https://q1.qlogo.cn/g?b=qq&nk={u['qq_id']}&s=640",
            "mode": u["mode"], "apex_name": stats.name,
            "platform": u["platform"],
            "rank_name": stats.rank_name, "rank_score": stats.rank_score,
            "rank_img": stats.rank_img,
            "rank_top_pct_global": gpct,
            "rank_ladder_pos": rp_pos,
            "level": total_lvl, "kills": badges.get("kills", 0) or stats.kills,
            "state": stats.state,
        }

    @filter.command("lfg", alias={"组队", "lfg"})
    async def cmd_lfg(self, event: AstrMessageEvent):
        """找队友 — /lfg [排位|娱乐|列表|退出] [@目标 仅管理员]"""
        qq_id = event.get_sender_id()
        group_id = event.unified_msg_origin
        msg = event.get_message_str().strip()
        parts = msg.split(maxsplit=1)
        arg = parts[1].strip().lower() if len(parts) > 1 else ""

        # 提取 @目标（仅 leave / register 模式支持）
        target_qq, arg_cleaned, err = await self._resolve_admin_target(event, arg)
        if err:
            yield event.plain_result(err)
            return
        if target_qq != qq_id:
            qq_id = target_qq
            arg = arg_cleaned

        if arg in ("list", "列表"):
            lfg_users = await self.db.list_lfg_users(group_id)
            if not lfg_users:
                img = await renderer.draw_text_card("LFG", "当前没有人在找队友", is_error=True)
                async for r in self._send_card(event, img):
                    yield r
                return

            entries = []
            rank_dist = await self.apex.get_rank_distribution()
            for u in lfg_users:
                entry = await self._refresh_lfg_entry(u, group_id, rank_dist, event.bot)
                if entry:
                    entries.append(entry)

            if not entries:
                img = await renderer.draw_text_card("LFG", "没有有效的战绩数据", is_error=True)
                async for r in self._send_card(event, img):
                    yield r
                return

            img = await renderer.draw_lfg_card(entries)
            async for r in self._send_card(event, img):
                yield r
            return

        if arg in ("leave", "退出", "取消"):
            existing = await self.db.get_lfg_user(qq_id, group_id)
            if existing:
                await self.db.remove_lfg_user(qq_id, group_id)
                yield event.plain_result("已退出找队友列表")
            else:
                yield event.plain_result("你不在找队友列表中")
            return

        mode = None
        if arg in ("rank", "ranked", "排位", "rp"):
            mode = "ranked"
        elif arg in ("casual", "娱乐", "匹配", "pub", "pubs"):
            mode = "casual"
        elif arg in ("register", "注册", "登记"):
            mode = None
        elif arg and arg not in ("list", "列表", "leave", "退出", "取消"):
            img = await renderer.draw_text_card(
                "LFG", "用法: /lfg [排位|娱乐|列表|退出]", is_error=True
            )
            async for r in self._send_card(event, img):
                yield r
            return

        if not mode:
            img = await renderer.draw_lfg_mode_card()
            async for r in self._send_card(event, img):
                yield r
            return

        cached = self._profile_cache.get(qq_id)
        if cached:
            # 验证 cache 里的 uid 是自己绑定的，防止 /stats @别人 后误注册
            user = await self.db.get_user(qq_id)
            if user and str(user["uid"]) != str(cached["uid"]):
                cached = None
        if not cached:
            user = await self.db.get_user(qq_id)
            if user:
                stats = await self.apex.get_stats(user["uid"], user["platform"])
                if stats:
                    qq_avatar = f"https://q1.qlogo.cn/g?b=qq&nk={qq_id}&s=640"
                    cached = {
                        "uid": user["uid"],
                        "name": stats.name,
                        "platform": user["platform"],
                        "rank_name": stats.rank_name,
                        "rank_score": stats.rank_score,
                        "rank_img": stats.rank_img,
                        "level": stats.level,
                        "kills": stats.kills,
                        "avatar_url": qq_avatar,
                    }
                    self._profile_cache[qq_id] = cached

        if not cached:
            img = await renderer.draw_text_card(
                "LFG", "请先使用 /bind 绑定账号或 /stats 查询战绩后再找队友", is_error=True
            )
            async for r in self._send_card(event, img):
                yield r
            return

        # 注册时一并爬取 ALS 数据存入 DB
        bind_user = await self.db.get_user(qq_id)
        als_lookup = bind_user["uid"] if bind_user else cached["uid"]
        badges, stats_lfg = await asyncio.gather(
            fetch_lfg_stats(als_lookup, cached["platform"]),
            self.apex.get_stats(cached["uid"], cached["platform"]),
        )
        lvl_raw = badges.get("level") or (stats_lfg.level if stats_lfg else cached.get("level", 0))
        pr_raw = badges.get("prestige") or (stats_lfg.prestige if stats_lfg else cached.get("prestige", 0))
        kills = badges.get("kills", 0) or (stats_lfg.kills if stats_lfg else cached.get("kills", 0))
        rp = stats_lfg.rank_score if stats_lfg else cached.get("rank_score", 0)
        rn = stats_lfg.rank_name if stats_lfg else cached.get("rank_name", "")
        ri = stats_lfg.rank_img if stats_lfg else cached.get("rank_img", "")
        st = stats_lfg.state if stats_lfg else "offline"
        rp_pos = badges.get("rankPos", 0) or (stats_lfg.rank_ladder_pos if stats_lfg else 0)

        qq_name = event.get_sender_name() or ""
        if qq_id != event.get_sender_id():
            try:
                info = await event.bot.call_action("get_stranger_info", user_id=int(qq_id), no_cache=False)
                qq_name = info.get("nickname", "") or info.get("nick", "")
            except Exception:
                qq_name = ""
        await self.db.upsert_lfg_user(
            qq_id, group_id, cached["uid"], cached["name"], cached["platform"], mode,
            qq_name=qq_name,
            kills=kills, level=lvl_raw, prestige=pr_raw,
            rank_pos=rp_pos, rank_name=rn, rank_score=rp, rank_img=ri, state=st,
        )

        yield event.plain_result(f"已注册找队友 ({'排位' if mode == 'ranked' else '娱乐'})，使用 /lfg 列表 查看")

    # ═══════════════════════════════════════════════
    #  地图轮换
    # ═══════════════════════════════════════════════

    @filter.command("map", alias={"地图"})
    async def cmd_map(self, event: AstrMessageEvent):
        """查询当前 Apex 地图轮换"""
        rotation = await self.apex.get_map_rotation()
        if not rotation:
            img = await renderer.draw_text_card(
                "查询失败", "无法获取地图轮换数据", is_error=True
            )
            async for r in self._send_card(event, img):
                yield r
            return
        img = await renderer.draw_map_card(rotation)
        async for r in self._send_card(event, img):
            yield r

    # ═══════════════════════════════════════════════
    #  大师数据
    # ═══════════════════════════════════════════════

    @filter.command("master", alias={"大师"})
    async def cmd_master(self, event: AstrMessageEvent):
        """查询大师 / 猎杀数据"""
        predator = await self.apex.get_predator()
        if not predator:
            img = await renderer.draw_text_card(
                "查询失败", "无法获取大师 / 猎杀数据", is_error=True
            )
            async for r in self._send_card(event, img):
                yield r
            return
        img = await renderer.draw_master_card(predator)
        async for r in self._send_card(event, img):
            yield r

    # ═══════════════════════════════════════════════
    #  服务器状态
    # ═══════════════════════════════════════════════

    @filter.command("server", alias={"服务器"})
    async def cmd_server(self, event: AstrMessageEvent):
        """查询 Apex 服务器状态"""
        server_status = await self.apex.get_server_status()
        if not server_status or not getattr(server_status, "als", None):
            img = await renderer.draw_text_card(
                "查询失败", "无法获取服务器状态", is_error=True
            )
            async for r in self._send_card(event, img):
                yield r
            return
        img = await renderer.draw_server_status_card(server_status)
        async for r in self._send_card(event, img):
            yield r

    @filter.command("monitor", alias={"监控", "服务器监控"})
    async def cmd_monitor(self, event: AstrMessageEvent, action: str = ""):
        session = event.unified_msg_origin
        action = (action or "").strip().lower()

        if action == "on":
            await self.db.set_monitor(session, True)
            interval = max(60, int(self.config.get("monitor_interval", 900)))
            logger.info(f"[Monitor] 开启 session={session}")
            yield event.plain_result(f"✅ 服务器状态监控已开启，每 {interval} 秒检查一次，异常时自动推送")
        elif action == "off":
            await self.db.set_monitor(session, False)
            logger.info(f"[Monitor] 关闭 session={session}")
            yield event.plain_result("✅ 服务器状态监控已关闭")
        elif action in ("status", ""):
            row = await self.db.get_monitor(session)
            if row and row["enabled"]:
                state = {"": "待首次检查", "normal": "正常", "unstable": "异常"}.get(row["last_state"], row["last_state"])
                logger.info(f"[Monitor] status session={session} enabled=1 last_state={row['last_state']!r}")
                yield event.plain_result(f"📡 监控状态: 开启\n当前状态: {state}")
            else:
                logger.info(f"[Monitor] status session={session} enabled=0")
                yield event.plain_result("📡 监控状态: 关闭\n使用 /monitor on 开启")
        else:
            yield event.plain_result("用法: /monitor on|off|status")

    @staticmethod
    def _detect_als_state(als) -> str:
        if als and als.outage_announcement:
            return "unstable"
        if als and als.sections:
            for sec in als.sections:
                s_lower = sec.status.lower()
                if "down" in s_lower or "unstable" in s_lower:
                    return "unstable"
                for entry in sec.entries:
                    e_upper = entry.status.upper()
                    if "DOWN" in e_upper or "UNSTABLE" in e_upper:
                        return "unstable"
        return "normal"

    async def _monitor_tick(self):
        import types

        als = None
        try:
            from .libs.als_scraper import scrape_als_server_status
            als = await scrape_als_server_status()
        except Exception:
            logger.warning("[Monitor] ALS scrape failed", exc_info=True)

        if als is None:
            logger.warning("[Monitor] ALS scrape failed, 跳过本轮 tick")
            return

        current_state = self._detect_als_state(als)
        logger.info(f"[Monitor] tick → state={current_state!r}  alert_banner={'…' if als and als.alert_banner else '—'}  outage={als.outage_announcement if als else '—'}  sections={len(als.sections) if als and als.sections else 0}")

        sessions = await self.db.list_monitor_sessions()
        if not sessions:
            logger.debug("[Monitor] tick → 无监控会话, 跳过")
            return

        wrapper = types.SimpleNamespace(als=als)

        for row in sessions:
            sid = row["session_id"]
            old_state = row.get("last_state", "")
            logger.info(f"[Monitor] tick → session={sid}  old={old_state!r}  new={current_state!r}")

            # 每个 session 独立 try/except，防止一个发送失败拖垮整个 tick
            try:
                if old_state == "unstable" and current_state == "normal":
                    text = f"🟢 服务器状态已恢复\n{als.alert_banner[:120] if als and als.alert_banner else '所有服务恢复正常'}"
                    await self.db.update_monitor_state(sid, current_state)
                    await _send_status_card(self.context, sid, text, wrapper)
                    logger.info(f"[Monitor] → 恢复推送 {sid}")

                elif current_state == "unstable" and old_state != "unstable":
                    text = f"🔴 服务器状态异常\n{als.alert_banner[:120] if als and als.alert_banner else '检测到服务不稳定'}"
                    await self.db.update_monitor_state(sid, current_state)
                    await _send_status_card(self.context, sid, text, wrapper)
                    logger.info(f"[Monitor] → 异常推送 {sid}")

                elif old_state == "" and current_state:
                    if current_state == "unstable":
                        text = f"🔴 服务器状态异常\n{als.alert_banner[:120] if als and als.alert_banner else '检测到服务不稳定'}"
                        await self.db.update_monitor_state(sid, current_state)
                        await _send_status_card(self.context, sid, text, wrapper)
                        logger.info(f"[Monitor] → 初始异常推送 {sid}")
                    else:
                        await self.db.update_monitor_state(sid, current_state)
                else:
                    if old_state != current_state:
                        await self.db.update_monitor_state(sid, current_state)
            except Exception:
                logger.warning(f"[Monitor] session={sid} 处理异常", exc_info=True)

    async def _monitor_loop(self):
        interval = max(60, int(self.config.get("monitor_interval", 900)))
        logger.info(f"[Monitor] loop 启动, 每 {interval}s 检查一次")
        while True:
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("[Monitor] loop 被终止")
                return
            try:
                logger.info("[Monitor] loop → tick")
                await self._monitor_tick()
            except Exception as e:
                logger.error(f"[Monitor] tick 异常: {e}")

    @filter.command("perf", alias={"性能"})
    async def cmd_perf(self, event: AstrMessageEvent):
        """查看 Playwright 浏览器性能"""
        from .libs.playwright_manager import get_pw_stats
        stats = get_pw_stats()
        if not stats:
            yield event.plain_result("暂无性能数据")
            return
        lines = ["[Playwright 性能]"]
        for k, v in stats.items():
            lines.append(
                f"{k}: avg={v['avg']:.2f}s max={v['max']:.2f}s min={v['min']:.2f}s ({v['count']}次)"
            )
        yield event.plain_result("\n".join(lines))

    # ═══════════════════════════════════════════════
    #  队伍系统
    # ═══════════════════════════════════════════════

    # ═══════════════════════════════════════════════
    #  后台自动清理过期队伍
    # ═══════════════════════════════════════════════

    @filter.on_astrbot_loaded()
    async def start_cleaner(self):
        self._fire_and_forget(self._auto_clean_temp_files(), "清理临时文件")

    async def _auto_clean_temp_files(self):
        """每5分钟清理超过30分钟的临时PNG文件"""
        import time
        from pathlib import Path
        while True:
            await asyncio.sleep(300)
            try:
                now = time.time()
                for f in Path(self._temp_dir).glob("*.png"):
                    if now - f.stat().st_mtime > 1800:
                        f.unlink(missing_ok=True)
            except Exception as e:
                logger.error(f"[小赤羽] 清理临时文件失败: {e}")

    # ═══════════════════════════════════════════════
    #  LLM 工具 — 返文本数据给LLM，图片缓存用于send_message_to_user
    # ═══════════════════════════════════════════════

    @filter.llm_tool(name="apex_stats")
    async def llm_stats(self, event: AstrMessageEvent, player_name: str = ""):
        """获取 Apex Legends 游戏内战绩数据并生成卡片。仅当用户明确要求查询 Apex 段位、击杀、胜场、KD 等游戏数据时调用。不要因为用户说"介绍我"或"评价我"就触发。

        Args:
            player_name(string): 玩家名或UID，留空查绑定账号
        """
        import base64
        from mcp.types import CallToolResult, TextContent, ImageContent

        qq_id = event.get_sender_id()
        if player_name:
            # 处理 @提及：查对方绑定
            at_match = re.search(r'\[CQ:at,qq=(\d+)\]', player_name) or re.search(r'@(\d+)', player_name)
            if at_match:
                target_qq = at_match.group(1)
                target_user = await self.db.get_user(target_qq)
                if not target_user:
                    return CallToolResult(
                        content=[TextContent(type="text", text=f"对方 (QQ {target_qq}) 未绑定 Apex 账号")]
                    )
                uid = target_user["uid"]
                platform = target_user.get("platform", "PC")
            elif player_name.strip().isdigit():
                idx = int(player_name.strip())
                cached = self._last_search.get(qq_id, [])
                if 1 <= idx <= len(cached):
                    r = cached[idx - 1]
                    uid = r["uid"]
                    platform = r.get("platform", "PC")
                else:
                    uid, platform = player_name.strip(), "PC"
            else:
                search_results = await search_players(player_name.strip())
                if search_results:
                    if len(search_results) == 1:
                        uid = search_results[0]["uid"]
                        platform = search_results[0].get("platform", "PC")
                    else:
                        self._last_search[qq_id] = search_results
                        hint = f"共 {len(search_results)} 个结果，请使用 /stats 数字 选择"
                        img_bytes = await renderer.draw_player_list_card(search_results, hint)
                        img_b64 = base64.b64encode(img_bytes).decode()
                        return CallToolResult(
                            content=[
                                TextContent(
                                    type="text",
                                    text=f"找到 {len(search_results)} 个匹配玩家。请发送卡片图片，用户回复数字后，直接将该数字作为 player_name 参数再次调用 apex_stats 即可。",
                                ),
                                ImageContent(type="image", data=img_b64, mimeType="image/png"),
                            ]
                        )
                else:
                    api_results = await self.apex.name_to_uid_all(player_name.strip())
                    if not api_results:
                        return CallToolResult(
                            content=[
                                TextContent(type="text", text=f"找不到玩家 '{player_name}'")
                            ]
                        )
                    if len(api_results) > 1:
                        lines = [f"找到 {len(api_results)} 个匹配玩家:"]
                        for r in api_results:
                            lines.append(f"{r.name} — UID {r.uid}")
                        lines.append("请让用户选择一个 UID，然后用 UID 直接查询。")
                        return CallToolResult(
                            content=[TextContent(type="text", text="\n".join(lines))]
                        )
                    uid, platform = api_results[0].uid, "PC"
        else:
            user = await self.db.get_user(qq_id)
            if not user:
                return CallToolResult(
                    content=[
                        TextContent(
                            type="text",
                            text="用户还没有绑定 Apex 账号，提示用户使用 /bind 命令绑定",
                        )
                    ]
                )
            uid, platform = user["uid"], user["platform"]

        stats_task = self.apex.get_stats(uid, platform)
        badges_task = self._get_badges_cached(uid, platform)
        rankdist_task = self.apex.get_rank_distribution()
        stats, badges, rank_dist = await asyncio.gather(
            stats_task, badges_task, rankdist_task
        )
        if not stats:
            return CallToolResult(
                content=[TextContent(type="text", text="无法获取战绩数据")]
            )

        rp_delta = await self.db.get_rp_delta(stats.uid, platform, stats.rank_score)
        self._fire_and_forget(self.db.save_rp(stats.uid, platform, stats.rank_score), "保存RP")

        qq_avatar = f"https://q1.qlogo.cn/g?b=qq&nk={qq_id}&s=640"
        _lv2 = badges.get("level") or stats.level
        _pr2 = badges.get("prestige") or stats.prestige
        global_pct = badges.get("rankTopPct") or self._calc_global_pct(stats.rank_name, stats.rank_div, rank_dist) or stats.rank_top_pct
        rank_ladder_pos = stats.rank_ladder_pos or badges.get("rankPcPos") or badges.get("rankPos", 0)
        profile_data = {
            "name": stats.name,
            "tag": stats.tag,
            "uid": stats.uid,
            "avatar_url": qq_avatar,
            "platform": platform,
            "online": stats.state,
            "level": _pr2 * 500 + _lv2 if _pr2 else _lv2,
            "level_pct": stats.to_next_level_pct,
            "prestige": _pr2,
            "rank_name": stats.rank_name,
            "rank_div": stats.rank_div,
            "rank_score": stats.rank_score,
            "rank_img": stats.rank_img,
            "rank_top_pct": stats.rank_top_pct,
            "rank_top_pct_global": global_pct,
            "rank_ladder_pos": rank_ladder_pos,
            "rp_delta": rp_delta,
            "kills": badges.get("kills", 0) or stats.kills,
            "damage": stats.damage,
            "wins": stats.wins,
            "kd": stats.kd,
            "top_legends": [
                {
                    "name": leg["name"],
                    "kills": leg["kills"],
                    "icon_url": leg.get("icon", ""),
                }
                for leg in stats.top_legends[:3]
            ],
            "selected_legend": stats.selected_legend_data,
            "season_badges": badges.get("seasons", []),
            "special_badges": badges.get("special", []),
            "rank_dist_entries": rank_dist.entries if rank_dist else None,
        }
        img_bytes = await renderer.draw_profile_card(profile_data)
        img_b64 = base64.b64encode(img_bytes).decode()

        rank_zh = {
            "Rookie": "菜鸟",
            "Bronze": "青铜",
            "Silver": "白银",
            "Gold": "黄金",
            "Platinum": "白金",
            "Diamond": "钻石",
            "Master": "大师",
            "Predator": "猎杀",
        }
        rn = rank_zh.get(
            profile_data["rank_name"].split(" ")[0], profile_data["rank_name"]
        )
        rd = profile_data["rank_div"] if profile_data["rank_div"] > 0 else ""
        state = "在线" if profile_data["online"] in ("online", "in_game") else "离线"
        delta_str = f" (较上次查询 {rp_delta:+d} RP)" if rp_delta is not None else ""

        text = (
            f"玩家 {profile_data['name']} (UID {profile_data['uid']})\n"
            f"等级 Lv.{profile_data['level']} | 状态 {state}\n"
            f"段位 {rn}{rd} | RP {profile_data['rank_score']:,}{delta_str} | 全服 Top {profile_data['rank_top_pct']}%\n"
            f"生涯击杀 {profile_data['kills']:,} | 总伤害 {profile_data['damage']:,} | BR 胜场 {profile_data['wins']:,}\n"
        )
        if profile_data["top_legends"]:
            text += (
                "常用英雄: "
                + ", ".join(
                    f"{leg['name']} ({leg['kills']}杀)"
                    for leg in profile_data["top_legends"][:3]
                )
                + "\n"
            )
        if rank_dist and rank_dist.entries:
            text += (
                "段位分布: "
                + ", ".join(f"{e.name} {e.pct}%" for e in rank_dist.entries)
                + "\n"
            )
        text += "\n请根据以上数据评论一下用户的战绩，然后用 send_message_to_user 发送战绩卡片图片。"

        return CallToolResult(
            content=[
                TextContent(type="text", text=text),
                ImageContent(type="image", data=img_b64, mimeType="image/png"),
            ]
        )

    @filter.llm_tool(name="apex_bind")
    async def llm_bind(
        self, event: AstrMessageEvent, player_name: str, platform: str = "PC", target_qq: str = ""
    ):
        """绑定 Apex 账号到当前 QQ（管理员可绑定到其他人的 QQ）。
        Args:
            player_name(string): 要绑定的玩家名或数字序号
            platform(string): 平台，PC/PS4/X1，默认PC
            target_qq(string): 要绑定到的QQ号，不填则绑定给自己（仅管理员可用）
        """
        import base64
        from mcp.types import CallToolResult, TextContent, ImageContent

        if platform.upper() not in ("PC", "PS4", "X1"):
            return CallToolResult(
                content=[
                    TextContent(
                        type="text", text="平台仅支持 PC / PS / XBOX ，请提示用户"
                    )
                ]
            )
        platform = platform.upper()
        qq_id = event.get_sender_id()

        # admin 可为他人绑定
        if target_qq:
            if not event.is_admin():
                return CallToolResult(
                    content=[TextContent(type="text", text="只有管理员才能为他人绑定账号")]
                )
            qq_id = target_qq

        if player_name.strip().isdigit():
            idx = int(player_name.strip())
            cached = self._last_search.get(qq_id, [])
            if 1 <= idx <= len(cached):
                r = cached[idx - 1]
                plat = r.get("platform", platform)
                await self.db.upsert_user(qq_id, r["uid"], r["name"], plat)
                return CallToolResult(
                    content=[
                        TextContent(
                            type="text",
                            text=f"已成功绑定 {r['name']} (UID {r['uid']}, {plat})。请告知用户绑定成功。",
                        )
                    ]
                )
            return CallToolResult(
                content=[
                    TextContent(type="text", text=f"序号 {idx} 无效，请先搜索玩家名后再用数字选择。")
                ]
            )

        results = await search_players(player_name.strip(), platform)
        if results:
            if len(results) == 1:
                r = results[0]
                plat = r.get("platform", platform)
                await self.db.upsert_user(qq_id, r["uid"], r["name"], plat)
                return CallToolResult(
                    content=[
                        TextContent(
                            type="text",
                            text=f"已成功绑定 {r['name']} (UID {r['uid']}, {plat})。请告知用户绑定成功。",
                        )
                    ]
                )
            self._last_search[qq_id] = results
            img_bytes = await renderer.draw_player_list_card(results, f"共 {len(results)} 个结果，回复数字选择")
            img_b64 = base64.b64encode(img_bytes).decode()
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=f"找到 {len(results)} 个匹配玩家。请发送卡片图片，用户回复数字后重新调用 apex_bind 传入该数字即可。",
                    ),
                    ImageContent(type="image", data=img_b64, mimeType="image/png"),
                ]
            )

        api_results = await self.apex.name_to_uid_all(player_name, platform)
        if not api_results:
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=f"找不到玩家 '{player_name}'，请提示用户检查名字",
                    )
                ]
            )
        if len(api_results) > 1:
            lines = [f"找到 {len(api_results)} 个匹配玩家:"]
            for r in api_results:
                lines.append(f"{r.name} — UID {r.uid}")
            lines.append("请让用户选择一个 UID，用 /bind_uid <UID> 绑定。")
            return CallToolResult(
                content=[TextContent(type="text", text="\n".join(lines))]
            )
        result = api_results[0]
        await self.db.upsert_user(qq_id, result.uid, result.name, platform)
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=f"已成功绑定 {result.name} (UID {result.uid}, {platform})。请告知用户绑定成功。",
                )
            ]
        )

    @filter.llm_tool(name="apex_unbind")
    async def llm_unbind(self, event: AstrMessageEvent, target_qq: str = ""):
        """解绑 QQ 的 Apex 账号（管理员可解绑其他人的 QQ）。
        Args:
            target_qq(string): 要解绑的QQ号，不填则解绑自己（仅管理员可用）
        """
        from mcp.types import CallToolResult, TextContent

        qq_id = event.get_sender_id()
        if target_qq:
            if not event.is_admin():
                return CallToolResult(
                    content=[TextContent(type="text", text="只有管理员才能解绑他人的账号")]
                )
            qq_id = target_qq
        user = await self.db.get_user(qq_id)
        if not user:
            return CallToolResult(
                content=[
                    TextContent(
                        type="text", text="用户还没有绑定 Apex 账号，请提示用户先绑定"
                    )
                ]
            )
        await self.db.delete_user(qq_id)
        return CallToolResult(
            content=[
                TextContent(type="text", text=f"已解绑 {user['name']}，请告知用户。")
            ]
        )

    @filter.llm_tool(name="apex_map")
    async def llm_map(self, event: AstrMessageEvent):
        """查询当前 Apex 地图轮换，生成卡片。"""
        import base64
        from mcp.types import CallToolResult, TextContent, ImageContent

        rotation = await self.apex.get_map_rotation()
        if not rotation:
            return CallToolResult(
                content=[TextContent(type="text", text="获取地图轮换失败")]
            )
        img_bytes = await renderer.draw_map_card(rotation)
        img_b64 = base64.b64encode(img_bytes).decode()
        br = rotation.br_current.map if rotation.br_current else "?"
        br_timer = (
            f" (剩余{rotation.br_current.remaining_timer})"
            if rotation.br_current and rotation.br_current.remaining_timer
            else ""
        )
        ranked = rotation.ranked_current.map if rotation.ranked_current else "?"
        r_next = (
            rotation.ranked_next.map
            if rotation.ranked_next and rotation.ranked_next.map
            else ""
        )
        text = (
            f"当前匹配: {br}{br_timer}\n"
            f"下一张匹配: {rotation.br_next.map if rotation.br_next else '?'}\n"
            f"当前排位: {ranked}\n"
        )
        if r_next:
            text += f"下一张排位: {r_next}\n"
        text += "\n请简单介绍一下地图，然后用 send_message_to_user 发送地图卡片图片。"
        return CallToolResult(
            content=[
                TextContent(type="text", text=text),
                ImageContent(type="image", data=img_b64, mimeType="image/png"),
            ]
        )

    @filter.llm_tool(name="apex_server")
    async def llm_server(self, event: AstrMessageEvent):
        """查询 Apex 服务器状态，生成卡片。"""
        import base64
        from mcp.types import CallToolResult, TextContent, ImageContent

        server_status = await self.apex.get_server_status()
        if not server_status or not getattr(server_status, "als", None):
            return CallToolResult(
                content=[TextContent(type="text", text="获取服务器状态失败")]
            )
        img_bytes = await renderer.draw_server_status_card(server_status)
        img_b64 = base64.b64encode(img_bytes).decode()
        als = getattr(server_status, "als", None)
        if als and als.alert_banner:
            text = f"ALS 报告: {als.alert_banner[:100]}\n"
        elif als and als.sections:
            unstable = sum(1 for s in als.sections if "unstable" in s.status.lower() or "slow" in s.status.lower())
            text = f"ALS 报告: {len(als.sections)} 个服务中 {unstable} 个异常\n"
        else:
            text = "服务器状态数据获取成功\n"
        text += "\n请根据服务器状态评论一下，然后用 send_message_to_user 发送服务器状态卡片图片。"
        return CallToolResult(
            content=[
                TextContent(type="text", text=text),
                ImageContent(type="image", data=img_b64, mimeType="image/png"),
            ]
        )

    @filter.llm_tool(name="apex_master")
    async def llm_master(self, event: AstrMessageEvent):
        """查询各平台大师人数和猎杀线分数，生成卡片。"""
        import base64
        from mcp.types import CallToolResult, TextContent, ImageContent

        predator = await self.apex.get_predator()
        if not predator:
            return CallToolResult(
                content=[TextContent(type="text", text="获取大师数据失败")]
            )
        img_bytes = await renderer.draw_master_card(predator)
        img_b64 = base64.b64encode(img_bytes).decode()
        text = "各平台大师/猎杀数据:\n"
        for plat in ["PC", "PS4", "X1", "SWITCH"]:
            pd = predator.platforms.get(plat)
            if pd:
                text += f"{plat}: 猎杀线 {pd.predator_cap:,} RP | 大师/猎杀 {pd.masters_and_preds:,} 人\n"
        text += "\n请简单评论各平台数据，然后用 send_message_to_user 发送大师数据卡片图片。"
        return CallToolResult(
            content=[
                TextContent(type="text", text=text),
                ImageContent(type="image", data=img_b64, mimeType="image/png"),
            ]
        )

    @filter.llm_tool(name="apex_lfg")
    async def llm_lfg(self, event: AstrMessageEvent, action: str = "list", target_qq: str = ""):
        """找队友功能。列出组队列表、注册排位/娱乐、退出。当用户说"组队"、"找队友"、"想打排位"、"想打匹配"时调用，不要因为"组队"随意触发。
        Args:
            action(string): 操作类型: list/ranked/casual/leave
            target_qq(string): 要操作的QQ号，不填则操作自己（仅管理员可用）
        """
        import base64
        from mcp.types import CallToolResult, TextContent, ImageContent

        qq_id = event.get_sender_id()
        if target_qq:
            if not event.is_admin():
                return CallToolResult(
                    content=[TextContent(type="text", text="只有管理员才能为他人操作")]
                )
            qq_id = target_qq
        group_id = event.unified_msg_origin
        action = action.strip().lower()

        if action in ("leave", "退出", "取消"):
            existing = await self.db.get_lfg_user(qq_id, group_id)
            if existing:
                await self.db.remove_lfg_user(qq_id, group_id)
                return CallToolResult(
                    content=[TextContent(type="text", text="已退出找队友列表")]
                )
            return CallToolResult(
                content=[TextContent(type="text", text="你不在找队友列表中")]
            )

        if action in ("ranked", "排位", "casual", "娱乐"):
            mode = "ranked" if action in ("ranked", "排位") else "casual"
            cached = self._profile_cache.get(qq_id)
            if cached:
                user = await self.db.get_user(qq_id)
                if user and str(user["uid"]) != str(cached["uid"]):
                    cached = None
            if not cached:
                user = await self.db.get_user(qq_id)
                if user:
                    stats = await self.apex.get_stats(user["uid"], user["platform"])
                    if stats:
                        cached = {
                            "uid": user["uid"],
                            "name": stats.name,
                            "platform": user["platform"],
                            "rank_name": stats.rank_name,
                            "rank_score": stats.rank_score,
                            "rank_img": stats.rank_img,
                            "level": stats.level,
                            "kills": stats.kills,
                        }
                        self._profile_cache[qq_id] = cached
            if not cached:
                return CallToolResult(
                    content=[TextContent(type="text", text="请先使用 /bind 绑定账号或 /stats 查询战绩后再找队友")]
                )
            # 注册时一并爬取 ALS 数据存入 DB
            bind_user = await self.db.get_user(qq_id)
            als_lookup = bind_user["uid"] if bind_user else cached["uid"]
            badges, stats_lfg = await asyncio.gather(
                fetch_lfg_stats(als_lookup, cached["platform"]),
                self.apex.get_stats(cached["uid"], cached["platform"]),
            )
            lvl_raw = badges.get("level") or (stats_lfg.level if stats_lfg else cached.get("level", 0))
            pr_raw = badges.get("prestige") or (stats_lfg.prestige if stats_lfg else cached.get("prestige", 0))
            kills = badges.get("kills", 0) or (stats_lfg.kills if stats_lfg else cached.get("kills", 0))
            rp = stats_lfg.rank_score if stats_lfg else cached.get("rank_score", 0)
            rn = stats_lfg.rank_name if stats_lfg else cached.get("rank_name", "")
            ri = stats_lfg.rank_img if stats_lfg else cached.get("rank_img", "")
            st = stats_lfg.state if stats_lfg else "offline"
            rp_pos = (stats_lfg.rank_ladder_pos if stats_lfg else 0) or badges.get("rankPos", 0)
            qq_name = event.get_sender_name() or ""
            if qq_id != event.get_sender_id():
                try:
                    info = await event.bot.call_action("get_stranger_info", user_id=int(qq_id), no_cache=False)
                    qq_name = info.get("nickname", "") or info.get("nick", "")
                except Exception:
                    qq_name = ""
            await self.db.upsert_lfg_user(
                qq_id, group_id, cached["uid"], cached["name"], cached["platform"], mode,
                qq_name=qq_name,
                kills=kills, level=lvl_raw, prestige=pr_raw,
                rank_pos=rp_pos, rank_name=rn, rank_score=rp, rank_img=ri, state=st,
            )
            return CallToolResult(
                content=[TextContent(type="text", text=f"已注册找队友 ({'排位' if mode == 'ranked' else '娱乐'})")]
            )

        # list
        lfg_users = await self.db.list_lfg_users(group_id)
        if not lfg_users:
            return CallToolResult(
                content=[TextContent(type="text", text="当前没有人在找队友")]
            )

        entries = []
        rank_dist = await self.apex.get_rank_distribution()
        for u in lfg_users:
            entry = await self._refresh_lfg_entry(u, group_id, rank_dist, event.bot)
            if entry:
                entries.append(entry)

        if not entries:
            return CallToolResult(
                content=[TextContent(type="text", text="没有有效的战绩数据")]
            )

        text_lines = [f"当前找队友列表 ({len(entries)} 人):"]
        for e in entries:
            txt = f"{e['qq_name'] or e['apex_name']} | {e['rank_name']} {e['rank_score']}RP | Lv{e['level']} | {e['kills']}杀 | {e['state']} | {'排位' if e['mode']=='ranked' else '娱乐'}"
            text_lines.append(txt)
        img_bytes = await renderer.draw_lfg_card(entries)
        img_b64 = base64.b64encode(img_bytes).decode()
        return CallToolResult(
            content=[
                TextContent(type="text", text="\n".join(text_lines)),
                ImageContent(type="image", data=img_b64, mimeType="image/png"),
            ]
        )
