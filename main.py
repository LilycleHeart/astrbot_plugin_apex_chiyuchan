"""小赤羽 — Apex Legends QQ Bot 插件入口"""

from __future__ import annotations

import asyncio
import os
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
from .libs.steamcharts_scraper import fetch_steamcharts
from .libs.season_scraper import fetch_season_info, fetch_meta_top5


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
    "Apex 战绩查询 / 地图轮换 / 大师数据 / 组队系统 / Steam 日活",
    "1.2.0",
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
        self._rp_update_task: asyncio.Task | None = None

        from .libs.config import preload_fonts
        preload_fonts()

        if config.get("use_local_fonts", False):
            try:
                from .libs.playwright_renderer import set_use_local_fonts
                set_use_local_fonts(True)
            except Exception:
                pass

        # 时区 & 卡片主题
        from .libs.playwright_manager import set_timezone, set_color_scheme
        set_timezone(config.get("timezone", "Asia/Shanghai"))
        set_color_scheme(config.get("color_scheme", "dark"))

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

    @staticmethod
    def _unwrap_event(ctx):
        """兼容 v4.26.0 ContextWrapper 和旧版 AstrMessageEvent"""
        if hasattr(ctx, 'context') and hasattr(ctx.context, 'event'):
            return ctx.context.event
        return ctx

    @staticmethod
    def _save_temp_image(img_bytes: bytes) -> str | None:
        """将图片字节保存为临时文件，返回文件路径"""
        import tempfile
        try:
            fd, path = tempfile.mkstemp(suffix=".png", dir=str(Path(get_astrbot_data_path()) / "temp"))
            with os.fdopen(fd, 'wb') as f:
                f.write(img_bytes)
            return path
        except Exception:
            return None

    async def _on_init(self):
        await self.db.init()
        from .libs.image_renderer import _download_moe_digits_async
        from .libs.ttl_cache import start_cleaner
        from .libs.playwright_manager import get_browser
        from .libs import disk_cache

        # 启动时清理过期缓存
        try:
            cleaned = await disk_cache.cleanup()
            if cleaned > 0:
                logger.info(f"[小赤羽] 启动时清理了 {cleaned} 个过期缓存文件")
        except Exception as e:
            logger.warning(f"[小赤羽] 缓存清理失败: {e}")

        asyncio.create_task(get_browser())
        asyncio.create_task(_download_moe_digits_async())
        start_cleaner()
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        self._rp_update_task = asyncio.create_task(self._rp_update_loop())

    async def terminate(self):
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
        if self._rp_update_task and not self._rp_update_task.done():
            self._rp_update_task.cancel()
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
        # div=1 是段位最高小段（如 Diamond I），同段位内没人比自己高
        # div=4 是最低小段，同段位内 75% 比自己高
        div = max(1, min(rank_div, 4))
        above += tier_count * (div - 1) / 4
        return round(above / total * 100, 2)

    def _extract_at_target(self, event: AstrMessageEvent, args: str) -> tuple[str | None, str]:
        """从消息中提取 @QQ，返回 (target_qq, cleaned_args)。
        优先从消息链的 At 消息段提取，兼容 CQ 码格式。
        args 是已经移除命令名的参数字符串。
        自身 QQ 会被忽略（@机器人只是触发命令，不是指定目标）。"""
        import astrbot.api.message_components as Comp
        
        target_qq = None
        self_qq = event.get_self_id()
        
        # 从消息链提取 At 消息段（跳过 @机器人 自身）
        msg_obj = event.message_obj
        if msg_obj and hasattr(msg_obj, 'message'):
            for seg in msg_obj.message:
                if isinstance(seg, Comp.At):
                    qq = str(seg.qq)
                    if qq != self_qq:
                        target_qq = qq
                        break
        
        # 从纯文本中提取 CQ 码或 @数字 格式（兜底），同样跳过自身
        if not target_qq:
            m = re.search(r'\[CQ:at,qq=(\d+)\]', args)
            if m:
                qq = m.group(1)
                if qq != self_qq:
                    target_qq = qq
            else:
                m = re.search(r'@(\d+)', args)
                if m:
                    qq = m.group(1)
                    if qq != self_qq:
                        target_qq = qq
        
        # 从纯文本中移除 @相关内容
        cleaned = re.sub(r'\[CQ:at,qq=\d+\]', '', args).strip()
        cleaned = re.sub(r'@\d+', '', cleaned).strip()
        # 移除 @昵称(数字) 格式
        cleaned = re.sub(r'@\S+\(\d+\)', '', cleaned).strip()
        
        return target_qq, cleaned

    async def _resolve_admin_target(
        self, event: AstrMessageEvent, args: str
    ) -> tuple[str | None, str, str | None]:
        """解析命令中的 @目标。管理员可为他人操作。
        Returns (target_qq, cleaned_args, error_msg).
        若 non-admin 使用 @目标，返回 (None, cleaned_args, 错误消息)。
        """
        target_qq, cleaned = self._extract_at_target(event, args)
        if target_qq and not event.is_admin():
            return None, cleaned, "只有管理员才能为他人操作"
        return target_qq or event.get_sender_id(), cleaned, None

    async def _get_badges_cached(self, uid: str, platform: str) -> dict:
        """获取战绩页数据。实时从 ALS 抓取排名/击杀数据；媒体资源（赛季/特殊徽章）
        首次成功后永久存 DB，不再重爬。爬虫失败时用 DB 媒体兜底，但保留实时数据。"""
        cached = await self.db.get_badge_cache(uid, platform)
        media = cached["data"] if cached else {}
        # 实时抓取（force=True 跳过内存缓存）
        badges = await fetch_badges(uid, platform, force=True)
        if badges.get("seasons") or badges.get("special"):
            await self.db.set_badge_cache(uid, platform, badges)
            return badges
        # 爬虫失败：用 DB 媒体兜底，保留实时数据（level_icon/kills/level/prestige/rank等）
        if media:
            for k in ("level_icon", "kills", "level", "prestige", "rankPos", "rankScore", "rankTopPct", "rankPcPos"):
                if badges.get(k):
                    media[k] = badges[k]
            badges = media
        return badges

    async def _send_card(
        self, event: AstrMessageEvent, img_bytes: bytes | None, suffix: str = ".png",
        fallback_text: str = "渲染失败", **kwargs,
    ):
        """发送图片消息；img_bytes 为 None 时降级为纯文本"""
        if not img_bytes:
            yield event.plain_result(fallback_text)
            return
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
                yield event.plain_result(f"绑定成功：{r['name']} (UID {r['uid']}, {plat})")
                return

        results = await search_players(name, platform)
        if results:
            if len(results) == 1:
                r = results[0]
                await self.db.upsert_user(qq_id, r["uid"], r["name"], platform)
                yield event.plain_result(f"绑定成功：{r['name']} (UID {r['uid']}, {platform})")
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
            yield event.plain_result(f"绑定失败，找不到玩家 '{name}'")
            return
        if len(api_results) > 1:
            lines = [f"找到 {len(api_results)} 个匹配玩家，请用 /bind_uid <UID> 绑定:"]
            for r in api_results:
                lines.append(f"  {r.name} — UID: {r.uid}")
            yield event.plain_result("\n".join(lines))
            return
        api_result = api_results[0]

        expected = name.strip().lower().replace(" ", "")
        actual = api_result.name.lower().replace(" ", "")
        if expected not in actual and actual not in expected:
            yield event.plain_result(
                f"名字可能不匹配：搜索 '{name}' 返回了 '{api_result.name}' (UID: {api_result.uid})\n"
                f"绑定将继续。如果不对，请用 /bind_uid {api_result.uid} 重新绑定"
            )

        await self.db.upsert_user(qq_id, api_result.uid, api_result.name, platform)
        yield event.plain_result(f"绑定成功：{api_result.name} (UID {api_result.uid}, {platform})")

    @filter.command("bind_uid", alias={"绑定UID"})
    async def cmd_bind_uid(self, event: AstrMessageEvent, uid: str, platform: str = "PC"):
        """直接通过 UID 绑定 — /bind_uid <UID> [平台] [@目标 仅管理员]"""
        if platform.upper() not in ("PC", "PS4", "X1"):
            yield event.plain_result("平台仅支持 PC / PS4 / X1")
            return
        platform = platform.upper()
        msg = event.get_message_str().strip()
        rest = msg.split(maxsplit=1)[1] if " " in msg else ""
        qq_id, _, err = await self._resolve_admin_target(event, rest)
        if err:
            yield event.plain_result(err)
            return
        stats = await self.apex.get_stats(uid, platform)
        if not stats:
            yield event.plain_result(f"找不到 UID '{uid}'")
            return
        await self.db.upsert_user(qq_id, uid, stats.name, platform)
        yield event.plain_result(f"绑定成功：{stats.name} (UID {uid}, {platform})")

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
        yield event.plain_result("已解绑 Apex 账号")

    # ═══════════════════════════════════════════════
    #  战绩查询
    # ═══════════════════════════════════════════════

    @filter.command("stats", alias={"战绩", "查询", "profile", "卡片"})
    async def cmd_stats(self, event: AstrMessageEvent):
        """查询 Apex 战绩 — /stats [玩家名或UID] [@目标]"""
        qq_id = event.get_sender_id()
        msg = event.get_message_str().strip()
        rest = msg.split(maxsplit=1)[1] if " " in msg else ""

        # 提取 @目标
        target_qq, cleaned = self._extract_at_target(event, rest)
        name = cleaned.strip()

        if target_qq:
            # @某人：查对方绑定
            target_user = await self.db.get_user(target_qq)
            if not target_user:
                yield event.plain_result("对方未绑定 Apex 账号")
                return
            uid = target_user["uid"]
            platform = target_user.get("platform", "PC")
        elif name:
            if name.strip().isdigit():
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
                        yield event.plain_result(f"找不到玩家 '{name}'")
                        return
                    uid = api_results[0].uid
                    platform = "PC"
        else:
            user = await self.db.get_user(qq_id)
            if not user:
                yield event.plain_result("请先使用 /bind <玩家名> 绑定账号")
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
            yield event.plain_result("无法获取战绩数据")
            return

        # ── RP 变化（距上次查询）+ 历史折线图数据（并入本次查询分数）──
        rp_delta = await self.db.get_rp_delta(stats.uid, platform, stats.rank_score)
        rp_history = await self.db.get_rp_history_for_chart(stats.uid, platform, stats.rank_score, limit=12)
        self._fire_and_forget(self.db.save_rp(stats.uid, platform, stats.rank_score), "保存RP")

        # ── 构建渲染数据 ──
        display_qq = target_qq or qq_id
        qq_avatar = f"https://q1.qlogo.cn/g?b=qq&nk={display_qq}&s=640"
        _lv = badges.get("level") or stats.level
        _pr = badges.get("prestige") or stats.prestige
        global_pct = badges.get("rankTopPct") or self._calc_global_pct(stats.rank_name, stats.rank_div, rank_dist) or stats.rank_top_pct
        rank_ladder_pos = badges.get("rankPcPos") or badges.get("rankPos", 0) or stats.rank_ladder_pos
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
            "level_icon": f"https://apexlegendsstatus.com/core/level_badge/?level={_pr * 500 + _lv if _pr else _lv}",
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
            "rp_history": rp_history,
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
        rp_pos = badges.get("rankPcPos") or badges.get("rankPos", 0) or stats.rank_ladder_pos
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
                yield event.plain_result("当前没有人在找队友")
                return

            entries = []
            rank_dist = await self.apex.get_rank_distribution()
            for u in lfg_users:
                entry = await self._refresh_lfg_entry(u, group_id, rank_dist, event.bot)
                if entry:
                    entries.append(entry)

            if not entries:
                yield event.plain_result("没有有效的战绩数据")
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
            yield event.plain_result("用法: /lfg [排位|娱乐|列表|退出]")
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
            yield event.plain_result("请先使用 /bind 绑定账号或 /stats 查询战绩后再找队友")
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
        rp_pos = badges.get("rankPcPos") or badges.get("rankPos", 0) or (stats_lfg.rank_ladder_pos if stats_lfg else 0)

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
            yield event.plain_result("无法获取地图轮换数据")
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
            yield event.plain_result("无法获取大师 / 猎杀数据")
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
            yield event.plain_result("无法获取服务器状态")
            return
        img = await renderer.draw_server_status_card(server_status)
        async for r in self._send_card(event, img):
            yield r

    @filter.command("online", alias={"在线", "在线人数", "日活"})
    async def cmd_online(self, event: AstrMessageEvent):
        """查询 Apex Steam 日活 / 当前在线人数"""
        data = await fetch_steamcharts()
        if not data:
            yield event.plain_result("无法获取 Steam 日活数据，稍后再试")
            return
        img = await renderer.draw_steamcharts_card(data)
        async for r in self._send_card(event, img):
            yield r

    @filter.command("season", alias={"赛季", "赛季信息"})
    async def cmd_season(self, event: AstrMessageEvent):
        """查询当前 Apex 赛季信息 / META 胜率"""
        season_info = await fetch_season_info()
        if not season_info:
            yield event.plain_result("无法获取赛季信息，稍后再试")
            return
        meta_top5 = await fetch_meta_top5()
        img = await renderer.draw_season_card(season_info, meta_top5)
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

    async def _rp_update_loop(self):
        """定时更新绑定玩家积分（RP）到 rp_history，供折线图积累数据"""
        interval = int(self.config.get("rp_update_interval", 21600))
        if interval <= 0:
            logger.info("[RP更新] 已关闭 (rp_update_interval<=0)")
            return
        interval = max(60, interval)
        logger.info(f"[RP更新] loop 启动, 每 {interval}s 更新一次绑定玩家积分")
        while True:
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("[RP更新] loop 被终止")
                return
            try:
                await self._rp_update_tick()
            except Exception as e:
                logger.error(f"[RP更新] tick 异常: {e}")

    async def _rp_update_tick(self):
        users = await self.db.get_all_users()
        if not users:
            logger.debug("[RP更新] 无绑定玩家, 跳过")
            return
        sem = asyncio.Semaphore(3)  # 限流并发，避免打爆 API

        async def _update(u: dict):
            platform = u.get("platform", "PC")
            async with sem:
                stats = await self.apex.get_stats(u["uid"], platform, force=True)
                if not stats:
                    return False
                await self.db.save_rp(stats.uid, platform, stats.rank_score)
                return True

        results = await asyncio.gather(
            *[_update(u) for u in users], return_exceptions=True
        )
        ok = sum(1 for r in results if r is True)
        logger.info(f"[RP更新] 完成: 成功 {ok}/{len(users)}")

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

    @filter.command("cache", alias={"缓存"})
    async def cmd_cache(self, event: AstrMessageEvent, action: str = "stats"):
        """管理图片磁盘缓存 — /cache [stats|clear|cleanup]"""
        from .libs import disk_cache

        action = action.strip().lower()

        if action in ("stats", ""):
            stats = disk_cache.get_cache_stats()
            msg = (
                f"📊 图片缓存统计\n"
                f"缓存目录: {stats['cache_dir']}\n"
                f"文件数量: {stats['file_count']}\n"
                f"总大小: {stats['total_size_mb']:.1f} MB"
            )
            yield event.plain_result(msg)

        elif action == "clear":
            await disk_cache.clear()
            yield event.plain_result("✅ 图片缓存已清空")

        elif action in ("cleanup", "clean"):
            cleaned = await disk_cache.cleanup()
            yield event.plain_result(f"✅ 缓存清理完成，清理了 {cleaned} 个文件")

        else:
            yield event.plain_result("❌ 未知操作，可用: stats, clear, cleanup")

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
    async def llm_stats(self, event: AstrMessageEvent, player_name: str = "", uid: str = "", target_qq: str = ""):
        """获取 Apex Legends 游戏内战绩数据并生成卡片。仅当用户明确要求查询 Apex 段位、击杀、胜场、KD 等游戏数据时调用。不要因为用户说"介绍我"或"评价我"就触发。
        ⚠️ 查别人战绩（@某人）时，必须传 target_qq 参数（从 @提及 解析出的 QQ 号），不要用 player_name 搜索（同名玩家会查错）。
        ⚠️ 如果有 UID（从绑定记录或用户提到的数字），必须传 uid 参数。

        Args:
            player_name(string): 玩家名或数字序号（仅在无 uid 且无 target_qq 时使用）
            uid(string): Apex 数字 UID，有 UID 时优先使用
            target_qq(string): 要查询的 QQ 号（@某人查战绩时使用，从绑定记录取 UID，避免同名搜索错误）
        """
        event = self._unwrap_event(event)
        import base64

        qq_id = event.get_sender_id()
        # 优先 target_qq：从绑定记录取 UID，避免同名搜索错误
        if target_qq.strip():
            target_user = await self.db.get_user(target_qq.strip())
            if not target_user:
                yield event.plain_result(f"对方 (QQ {target_qq}) 未绑定 Apex 账号")
                return
            uid = target_user["uid"]
            platform = target_user.get("platform", "PC")
        elif uid.strip():
            uid_val = uid.strip()
            platform = "PC"
            # 尝试从绑定记录取平台
            for try_qq in (qq_id,):
                u = await self.db.get_user(try_qq)
                if u and u["uid"] == uid_val:
                    platform = u.get("platform", "PC")
                    break
        elif player_name:
            # 处理 @提及：查对方绑定
            at_match = re.search(r'\[CQ:at,qq=(\d+)\]', player_name) or re.search(r'@(\d+)', player_name)
            if at_match:
                target_qq = at_match.group(1)
                target_user = await self.db.get_user(target_qq)
                if not target_user:
                    yield event.plain_result(f"对方 (QQ {target_qq}) 未绑定 Apex 账号")
                    return
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
                        if img_bytes:
                            yield event.plain_result(f"找到 {len(search_results)} 个匹配玩家。请发送卡片图片，用户回复数字后，直接将该数字作为 player_name 参数再次调用 apex_stats 即可。")
                            img_path = self._save_temp_image(img_bytes)
                            if img_path:
                                yield event.image_result(img_path)
                            return
                else:
                    api_results = await self.apex.name_to_uid_all(player_name.strip())
                    if not api_results:
                        yield event.plain_result(f"找不到玩家 '{player_name}'")
                        return
                    if len(api_results) > 1:
                        lines = [f"找到 {len(api_results)} 个匹配玩家:"]
                        for r in api_results:
                            lines.append(f"{r.name} — UID {r.uid}")
                        lines.append("请让用户选择一个 UID，然后用 UID 直接查询。")
                        yield event.plain_result("\n".join(lines))
                        return
                    uid, platform = api_results[0].uid, "PC"
        else:
            user = await self.db.get_user(qq_id)
            if not user:
                yield event.plain_result("用户还没有绑定 Apex 账号，提示用户使用 /bind 命令绑定")
                return
            uid, platform = user["uid"], user["platform"]

        stats_task = self.apex.get_stats(uid, platform)
        badges_task = self._get_badges_cached(uid, platform)
        rankdist_task = self.apex.get_rank_distribution()
        stats, badges, rank_dist = await asyncio.gather(
            stats_task, badges_task, rankdist_task
        )
        if not stats:
            yield event.plain_result("无法获取战绩数据")
            return

        rp_delta = await self.db.get_rp_delta(stats.uid, platform, stats.rank_score)
        rp_history = await self.db.get_rp_history_for_chart(stats.uid, platform, stats.rank_score, limit=12)
        self._fire_and_forget(self.db.save_rp(stats.uid, platform, stats.rank_score), "保存RP")

        display_qq = target_qq.strip() if target_qq.strip() else qq_id
        qq_avatar = f"https://q1.qlogo.cn/g?b=qq&nk={display_qq}&s=640"
        _lv2 = badges.get("level") or stats.level
        _pr2 = badges.get("prestige") or stats.prestige
        global_pct = badges.get("rankTopPct") or self._calc_global_pct(stats.rank_name, stats.rank_div, rank_dist) or stats.rank_top_pct
        rank_ladder_pos = badges.get("rankPcPos") or badges.get("rankPos", 0) or stats.rank_ladder_pos
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
            "level_icon": f"https://apexlegendsstatus.com/core/level_badge/?level={_pr2 * 500 + _lv2 if _pr2 else _lv2}",
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
            "rp_history": rp_history,
        }
        img_bytes = await renderer.draw_profile_card(profile_data)
        img_b64 = base64.b64encode(img_bytes).decode() if img_bytes else ""

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

        yield event.plain_result(text)
        if img_bytes:
            img_path = self._save_temp_image(img_bytes)
            if img_path:
                yield event.image_result(img_path)

    @filter.llm_tool(name="apex_bind")
    async def llm_bind(
        self, event: AstrMessageEvent, player_name: str = "", platform: str = "PC", target_qq: str = "", uid: str = ""
    ):
        """绑定 Apex 账号到当前 QQ（管理员可绑定到其他人的 QQ）。
        ⚠️ 重要：如果用户提供了 UID 数字，必须用 uid 参数绑定，禁止用 player_name 搜索（同名玩家会导致绑错账号）。
        只有用户只提供玩家名没提供 UID 时，才用 player_name 搜索。
        Args:
            player_name(string): 玩家名或数字序号（仅在无 uid 时使用）
            uid(string): Apex 数字 UID。用户提到 UID 时必须传此参数，不要转成 player_name
            platform(string): 平台，PC/PS4/X1，默认PC
            target_qq(string): 要绑定到的QQ号，不填则绑定给自己（仅管理员可用）
        """
        event = self._unwrap_event(event)
        import base64

        if platform.upper() not in ("PC", "PS4", "X1"):
            yield event.plain_result("平台仅支持 PC / PS / XBOX ，请提示用户")
            return
        platform = platform.upper()
        qq_id = event.get_sender_id()

        # admin 可为他人绑定
        if target_qq:
            if not event.is_admin():
                yield event.plain_result("只有管理员才能为他人绑定账号")
                return
            qq_id = target_qq

        # 优先 UID 直接绑定，避免同名搜索错误
        if uid.strip():
            stats = await self.apex.get_stats(uid.strip(), platform)
            if not stats:
                yield event.plain_result(f"找不到 UID '{uid}'，请提示用户检查 UID")
                return
            await self.db.upsert_user(qq_id, uid.strip(), stats.name, platform)
            yield event.plain_result(f"已成功绑定 {stats.name} (UID {uid.strip()}, {platform})。请告知用户绑定成功。")
            return

        if not player_name.strip():
            yield event.plain_result("请提供玩家名或 UID 来绑定账号")
            return

        if player_name.strip().isdigit():
            idx = int(player_name.strip())
            cached = self._last_search.get(qq_id, [])
            if 1 <= idx <= len(cached):
                r = cached[idx - 1]
                plat = r.get("platform", platform)
                await self.db.upsert_user(qq_id, r["uid"], r["name"], plat)
                yield event.plain_result(f"已成功绑定 {r['name']} (UID {r['uid']}, {plat})。请告知用户绑定成功。")
                return
            yield event.plain_result(f"序号 {idx} 无效，请先搜索玩家名后再用数字选择。")
            return

        results = await search_players(player_name.strip(), platform)
        if results:
            if len(results) == 1:
                r = results[0]
                plat = r.get("platform", platform)
                await self.db.upsert_user(qq_id, r["uid"], r["name"], plat)
                yield event.plain_result(f"已成功绑定 {r['name']} (UID {r['uid']}, {plat})。请告知用户绑定成功。")
                return
            self._last_search[qq_id] = results
            img_bytes = await renderer.draw_player_list_card(results, f"共 {len(results)} 个结果，回复数字选择")
            yield event.plain_result(f"找到 {len(results)} 个匹配玩家。请发送卡片图片，用户回复数字后重新调用 apex_bind 传入该数字即可。")
            if img_bytes:
                img_path = self._save_temp_image(img_bytes)
                if img_path:
                    yield event.image_result(img_path)
            return

        api_results = await self.apex.name_to_uid_all(player_name, platform)
        if not api_results:
            yield event.plain_result(f"找不到玩家 '{player_name}'，请提示用户检查名字")
            return
        if len(api_results) > 1:
            lines = [f"找到 {len(api_results)} 个匹配玩家:"]
            for r in api_results:
                lines.append(f"{r.name} — UID {r.uid}")
            lines.append("请让用户选择一个 UID，用 /bind_uid <UID> 绑定。")
            yield event.plain_result("\n".join(lines))
            return
        result = api_results[0]
        await self.db.upsert_user(qq_id, result.uid, result.name, platform)
        yield event.plain_result(f"已成功绑定 {result.name} (UID {result.uid}, {platform})。请告知用户绑定成功。")

    @filter.llm_tool(name="apex_unbind")
    async def llm_unbind(self, event: AstrMessageEvent, target_qq: str = ""):
        """解绑 QQ 的 Apex 账号（管理员可解绑其他人的 QQ）。
        Args:
            target_qq(string): 要解绑的QQ号，不填则解绑自己（仅管理员可用）
        """
        event = self._unwrap_event(event)
        qq_id = event.get_sender_id()
        if target_qq:
            if not event.is_admin():
                yield event.plain_result("只有管理员才能解绑他人的账号")
                return
            qq_id = target_qq
        user = await self.db.get_user(qq_id)
        if not user:
            yield event.plain_result("用户还没有绑定 Apex 账号，请提示用户先绑定")
            return
        await self.db.delete_user(qq_id)
        yield event.plain_result(f"已解绑 {user['name']}，请告知用户。")

    @filter.llm_tool(name="apex_map")
    async def llm_map(self, event: AstrMessageEvent):
        """查询当前 Apex 地图轮换，生成卡片。"""
        event = self._unwrap_event(event)
        import base64

        rotation = await self.apex.get_map_rotation()
        if not rotation:
            yield event.plain_result("获取地图轮换失败")
            return
        img_bytes = await renderer.draw_map_card(rotation)
        img_b64 = base64.b64encode(img_bytes).decode() if img_bytes else ""
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
        yield event.plain_result(text)
        if img_bytes:
            img_path = self._save_temp_image(img_bytes)
            if img_path:
                yield event.image_result(img_path)

    @filter.llm_tool(name="apex_server")
    async def llm_server(self, event: AstrMessageEvent):
        """查询 Apex 服务器状态，生成卡片。"""
        event = self._unwrap_event(event)
        import base64

        server_status = await self.apex.get_server_status()
        if not server_status or not getattr(server_status, "als", None):
            yield event.plain_result("获取服务器状态失败")
            return
        img_bytes = await renderer.draw_server_status_card(server_status)
        img_b64 = base64.b64encode(img_bytes).decode() if img_bytes else ""
        als = getattr(server_status, "als", None)
        if als and als.alert_banner:
            text = f"ALS 报告: {als.alert_banner[:100]}\n"
        elif als and als.sections:
            unstable = sum(1 for s in als.sections if "unstable" in s.status.lower() or "slow" in s.status.lower())
            text = f"ALS 报告: {len(als.sections)} 个服务中 {unstable} 个异常\n"
        else:
            text = "服务器状态数据获取成功\n"
        text += "\n请根据服务器状态评论一下，然后用 send_message_to_user 发送服务器状态卡片图片。"
        yield event.plain_result(text)
        if img_bytes:
            img_path = self._save_temp_image(img_bytes)
            if img_path:
                yield event.image_result(img_path)

    @filter.llm_tool(name="apex_online")
    async def llm_online(self, event: AstrMessageEvent):
        """查询 Apex Legends Steam 当前在线人数和月度日活趋势，生成卡片。当用户询问在线人数、日活、活跃玩家数、有多少人在玩 Apex 等问题时调用。
        """
        event = self._unwrap_event(event)
        import base64

        data = await fetch_steamcharts()
        if not data:
            yield event.plain_result("获取 Steam 日活数据失败，稍后再试")
            return
        img_bytes = await renderer.draw_steamcharts_card(data)
        img_b64 = base64.b64encode(img_bytes).decode() if img_bytes else ""

        recent_avg = data.months[0].avg_players if data.months else 0
        text = (
            f"Apex Legends Steam 数据:\n"
            f"当前在线: {data.current_online:,}\n"
            f"24 小时峰值: {data.peak_24h:,}\n"
            f"历史峰值: {data.peak_all_time:,}\n"
            f"近 30 天日均: {int(recent_avg):,}\n"
            f"\n请简短评论一下 Apex 当前的人气，然后用 send_message_to_user 发送日活卡片图片。"
        )
        yield event.plain_result(text)
        if img_bytes:
            img_path = self._save_temp_image(img_bytes)
            if img_path:
                yield event.image_result(img_path)

    @filter.llm_tool(name="apex_master")
    async def llm_master(self, event: AstrMessageEvent):
        """查询各平台大师人数和猎杀线分数，生成卡片。"""
        event = self._unwrap_event(event)
        import base64

        predator = await self.apex.get_predator()
        if not predator:
            yield event.plain_result("获取大师数据失败")
            return
        img_bytes = await renderer.draw_master_card(predator)
        img_b64 = base64.b64encode(img_bytes).decode() if img_bytes else ""
        text = "各平台大师/猎杀数据:\n"
        for plat in ["PC", "PLAYSTATION", "XBOX", "SWITCH"]:
            pd = predator.platforms.get(plat)
            if pd:
                text += f"{plat}: 猎杀分数线 {pd.predator_cap:,} RP | 大师/猎杀 {pd.masters_and_preds:,} 人\n"
        text += "\n请简单评论各平台数据，然后用 send_message_to_user 发送大师数据卡片图片。"
        yield event.plain_result(text)
        if img_bytes:
            img_path = self._save_temp_image(img_bytes)
            if img_path:
                yield event.image_result(img_path)

    @filter.llm_tool(name="apex_season")
    async def llm_season(self, event: AstrMessageEvent):
        """查询当前 Apex 赛季信息、META 英雄胜率 Top5。当用户说"赛季"、"当前赛季"、"赛季倒计时"、"META"、"胜率"时调用。"""
        event = self._unwrap_event(event)
        import base64

        season_info = await fetch_season_info()
        if not season_info:
            yield event.plain_result("获取赛季信息失败")
            return
        meta_top5 = await fetch_meta_top5()
        img_bytes = await renderer.draw_season_card(season_info, meta_top5)
        img_b64 = base64.b64encode(img_bytes).decode() if img_bytes else ""

        meta_text = ""
        if meta_top5:
            meta_text = "META Top 6:\n"
            for i, m in enumerate(meta_top5[:6], 1):
                meta_text += f"  #{i} {m.name}({m.en}) — 胜率 {m.win_rate} / 选取率 {m.pick_rate}\n"

        text = (
            f"当前为第{season_info.season_number}赛季「{season_info.season_name}」 {season_info.split_label}\n"
            f"赛季结束: {season_info.season_end}\n"
            f"倒计时: {season_info.days_left}天 {season_info.hours_left}小时 {season_info.minutes_left}分钟\n"
            f"\n{meta_text}"
            f"\n请简短评论一下当前赛季，然后用 send_message_to_user 发送赛季卡片图片。"
        )
        yield event.plain_result(text)
        if img_bytes:
            img_path = self._save_temp_image(img_bytes)
            if img_path:
                yield event.image_result(img_path)

    @filter.llm_tool(name="apex_lfg")
    async def llm_lfg(self, event: AstrMessageEvent, action: str = "list", target_qq: str = ""):
        """找队友功能。列出组队列表、注册排位/娱乐、退出。当用户说"组队"、"找队友"、"想打排位"、"想打匹配"时调用，不要因为"组队"随意触发。
        Args:
            action(string): 操作类型: list/ranked/casual/leave
            target_qq(string): 要操作的QQ号，不填则操作自己（仅管理员可用）
        """
        event = self._unwrap_event(event)
        import base64

        qq_id = event.get_sender_id()
        if target_qq:
            if not event.is_admin():
                yield event.plain_result("只有管理员才能为他人操作")
                return
            qq_id = target_qq
        group_id = event.unified_msg_origin
        action = action.strip().lower()

        if action in ("leave", "退出", "取消"):
            existing = await self.db.get_lfg_user(qq_id, group_id)
            if existing:
                await self.db.remove_lfg_user(qq_id, group_id)
                yield event.plain_result("已退出找队友列表")
                return
            yield event.plain_result("你不在找队友列表中")
            return

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
                yield event.plain_result("请先使用 /bind 绑定账号或 /stats 查询战绩后再找队友")
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
            rp_pos = badges.get("rankPcPos") or badges.get("rankPos", 0) or (stats_lfg.rank_ladder_pos if stats_lfg else 0)
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
            yield event.plain_result(f"已注册找队友 ({'排位' if mode == 'ranked' else '娱乐'})")
            return

        # list
        lfg_users = await self.db.list_lfg_users(group_id)
        if not lfg_users:
            yield event.plain_result("当前没有人在找队友")
            return

        entries = []
        rank_dist = await self.apex.get_rank_distribution()
        for u in lfg_users:
            entry = await self._refresh_lfg_entry(u, group_id, rank_dist, event.bot)
            if entry:
                entries.append(entry)

        if not entries:
            yield event.plain_result("没有有效的战绩数据")
            return

        text_lines = [f"当前找队友列表 ({len(entries)} 人):"]
        for e in entries:
            txt = f"{e['qq_name'] or e['apex_name']} | {e['rank_name']} {e['rank_score']}RP | Lv{e['level']} | {e['kills']}杀 | {e['state']} | {'排位' if e['mode']=='ranked' else '娱乐'}"
            text_lines.append(txt)
        img_bytes = await renderer.draw_lfg_card(entries)
        img_b64 = base64.b64encode(img_bytes).decode() if img_bytes else ""
        yield event.plain_result(text)
        if img_bytes:
            img_path = self._save_temp_image(img_bytes)
            if img_path:
                yield event.image_result(img_path)
