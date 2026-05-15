"""小赤羽 — Apex Legends QQ Bot 插件入口"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .libs.apex_client import ApexClient
from .libs.database import Database
from .libs import image_renderer as renderer
from .libs.als_scraper import fetch_badges


@register("apex_xiaochiyu", "小赤羽", "Apex 战绩查询 / 地图轮换 / 大师数据 / 组队系统", "1.0.0")
class XiaoChiyu(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        api_key = config.get("apex_api_key", "")
        self.apex = ApexClient(api_key)
        self.db = Database()

        self._temp_dir = (
            Path(get_astrbot_data_path()) / "temp" / "apex_xiaochiyu"
        )
        self._temp_dir.mkdir(parents=True, exist_ok=True)

        asyncio.create_task(self._on_init())

    async def _on_init(self):
        await self.db.init()
        from .libs.image_renderer import _download_moe_digits_async
        asyncio.create_task(_download_moe_digits_async())

    async def terminate(self):
        await self.apex.close()
        await self.db.close()
        from .libs.playwright_manager import close_browser
        from .libs.http_client import close_clients
        await close_browser()
        await close_clients()

    def _save_temp(self, img_bytes: bytes, suffix: str = ".png") -> str:
        path = self._temp_dir / f"{uuid.uuid4()}{suffix}"
        path.write_bytes(img_bytes)
        return str(path)

    async def _send_card(self, event: AstrMessageEvent, img_bytes: bytes,
                         suffix: str = ".png", **kwargs):
        """直接发送图片消息"""
        path = self._save_temp(img_bytes, suffix)
        yield event.image_result(path)

    # ═══════════════════════════════════════════════
    #  绑定 / 解绑
    # ═══════════════════════════════════════════════

    @filter.command("bind", alias={"绑定"})
    async def cmd_bind(self, event: AstrMessageEvent, name: str, platform: str = "PC"):
        '''绑定 Apex 账号 — /bind <玩家名> [平台]'''
        if platform.upper() not in ("PC", "PS4", "X1"):
            yield event.plain_result("平台仅支持 PC / PS4 / X1")
            return

        platform = platform.upper()
        qq_id = event.get_sender_id()

        result = await self.apex.name_to_uid(name, platform)
        if not result:
            img = await renderer.draw_text_card("绑定失败", f"找不到玩家 '{name}'", is_error=True)
            async for r in self._send_card(event, img):
                yield r
            return

        await self.db.upsert_user(qq_id, result.uid, result.name, platform)
        img = await renderer.draw_bind_card(result.uid, result.name, platform)
        async for r in self._send_card(event, img):
            yield r

    @filter.command("unbind", alias={"解绑"})
    async def cmd_unbind(self, event: AstrMessageEvent):
        '''解绑 Apex 账号'''
        qq_id = event.get_sender_id()
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
    async def cmd_stats(self, event: AstrMessageEvent, name: str = ""):
        '''查询 Apex 战绩 — /stats [玩家名]'''
        qq_id = event.get_sender_id()

        if name:
            result = await self.apex.name_to_uid(name.strip())
            if not result:
                img = await renderer.draw_text_card("查询失败", f"找不到玩家 '{name}'", is_error=True)
                async for r in self._send_card(event, img):
                    yield r
                return
            uid = result.uid
            platform = "PC"
        else:
            user = await self.db.get_user(qq_id)
            if not user:
                img = await renderer.draw_text_card("未绑定", "请先使用 /bind <玩家名> 绑定账号", is_error=True)
                async for r in self._send_card(event, img):
                    yield r
                return
            uid = user["uid"]
            platform = user["platform"]

        # ── API 获取基础数据 + 网站抓取徽章 + 段位分布（并行）──
        stats_task = self.apex.get_stats(uid, platform)
        badges_task = fetch_badges(uid, platform)
        rankdist_task = self.apex.get_rank_distribution()
        stats, badges, rank_dist = await asyncio.gather(stats_task, badges_task, rankdist_task)

        if not stats:
            img = await renderer.draw_text_card("查询失败", "无法获取战绩数据", is_error=True)
            async for r in self._send_card(event, img):
                yield r
            return

        # ── RP 变化（距上次查询）──
        rp_delta = await self.db.get_rp_delta(stats.uid, platform, stats.rank_score)
        asyncio.create_task(self.db.save_rp(stats.uid, platform, stats.rank_score))

        # ── 构建渲染数据 ──
        qq_avatar = f"https://q1.qlogo.cn/g?b=qq&nk={qq_id}&s=640"

        # ── 构建渲染数据 ──
        profile_data = {
            "name": stats.name,
            "tag": stats.tag,
            "uid": stats.uid,
            "avatar_url": qq_avatar,
            "platform": platform,
            "online": stats.state,
            "level": badges.get("level", stats.level),
            "level_pct": stats.to_next_level_pct,
            "prestige": badges.get("prestige", stats.prestige),
            "rank_name": stats.rank_name,
            "rank_div": stats.rank_div,
            "rank_score": stats.rank_score,
            "rank_img": stats.rank_img,
            "rank_top_pct": stats.rank_top_pct,
            "rank_top_pct_global": stats.rank_top_pct,
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

        img = await renderer.draw_profile_card(profile_data)
        async for r in self._send_card(event, img):
            yield r

    # ═══════════════════════════════════════════════
    #  地图轮换
    # ═══════════════════════════════════════════════

    @filter.command("map", alias={"地图"})
    async def cmd_map(self, event: AstrMessageEvent):
        '''查询当前 Apex 地图轮换'''
        rotation = await self.apex.get_map_rotation()
        if not rotation:
            img = await renderer.draw_text_card("查询失败", "无法获取地图轮换数据", is_error=True)
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
        '''查询大师 / 猎杀数据'''
        predator = await self.apex.get_predator()
        if not predator:
            img = await renderer.draw_text_card("查询失败", "无法获取大师 / 猎杀数据", is_error=True)
            async for r in self._send_card(event, img, title="小赤羽·错误"):
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
        '''查询 Apex 服务器状态'''
        server_status = await self.apex.get_server_status()
        if not server_status or not server_status.servers:
            img = await renderer.draw_text_card("查询失败", "无法获取服务器状态", is_error=True)
            async for r in self._send_card(event, img):
                yield r
            return
        img = await renderer.draw_server_status_card(server_status)
        async for r in self._send_card(event, img):
            yield r

    # ═══════════════════════════════════════════════
    #  队伍系统
    # ═══════════════════════════════════════════════

    @filter.command_group("team")
    def team(self):
        pass

    @team.command("create", alias={"创建"})
    async def team_create(self, event: AstrMessageEvent, name: str):
        '''创建队伍 — /team create <队伍名>'''
        qq_id = event.get_sender_id()
        team_id = await self.db.create_team(name, qq_id)
        if team_id is None:
            img = await renderer.draw_text_card("创建失败", "你已在队伍中，请先退出当前队伍", is_error=True)
        else:
            img = await renderer.draw_text_card("队伍创建成功", f"'{name}' 已创建\n默认 12 小时后自动解散\n使用 /team ttl <小时> 修改时限")
        async for r in self._send_card(event, img):
            yield r

    @team.command("join", alias={"加入"})
    async def team_join(self, event: AstrMessageEvent, name: str):
        '''加入队伍 — /team join <队伍名>'''
        qq_id = event.get_sender_id()
        err = await self.db.join_team(name, qq_id)
        if err:
            img = await renderer.draw_text_card("加入失败", err, is_error=True)
        else:
            img = await renderer.draw_text_card("加入成功", f"你已加入队伍 '{name}'")
        async for r in self._send_card(event, img):
            yield r

    @team.command("leave", alias={"离开"})
    async def team_leave(self, event: AstrMessageEvent):
        '''离开当前队伍'''
        qq_id = event.get_sender_id()
        err = await self.db.leave_team(qq_id)
        if err:
            img = await renderer.draw_text_card("操作失败", err, is_error=True)
        else:
            img = await renderer.draw_text_card("已离开", "你已退出队伍")
        async for r in self._send_card(event, img):
            yield r

    @team.command("info", alias={"信息"})
    async def team_info(self, event: AstrMessageEvent):
        '''查看当前队伍信息'''
        qq_id = event.get_sender_id()
        team = await self.db.get_team_by_member(qq_id)
        if not team:
            img = await renderer.draw_text_card("队伍信息", "你不在任何队伍中", is_error=True)
        else:
            team["members"] = await self.db.get_team_members(team["id"])
            team["member_count"] = len(team["members"])
            img = await renderer.draw_team_card(team)
        async for r in self._send_card(event, img):
            yield r

    @team.command("list", alias={"列表"})
    async def team_list(self, event: AstrMessageEvent):
        '''查看所有活跃队伍'''
        teams = await self.db.get_all_teams()
        img = await renderer.draw_team_list_card(teams)
        async for r in self._send_card(event, img):
            yield r

    @team.command("disband", alias={"解散"})
    async def team_disband(self, event: AstrMessageEvent):
        '''解散队伍 (仅队长)'''
        qq_id = event.get_sender_id()
        err = await self.db.disband_team(qq_id)
        if err:
            img = await renderer.draw_text_card("解散失败", err, is_error=True)
        else:
            img = await renderer.draw_text_card("已解散", "队伍已解散")
        async for r in self._send_card(event, img):
            yield r

    @team.command("ttl", alias={"时限", "时效"})
    async def team_ttl(self, event: AstrMessageEvent, hours: int):
        '''修改队伍存活时限 — /team ttl <小时> (1~48 仅队长)'''
        qq_id = event.get_sender_id()
        err = await self.db.set_team_ttl(qq_id, hours)
        if err:
            img = await renderer.draw_text_card("修改失败", err, is_error=True)
        else:
            img = await renderer.draw_text_card("修改成功", f"队伍将在 {hours} 小时后自动解散")
        async for r in self._send_card(event, img):
            yield r

    # ═══════════════════════════════════════════════
    #  后台自动清理过期队伍
    # ═══════════════════════════════════════════════

    @filter.on_astrbot_loaded()
    async def start_cleaner(self):
        asyncio.create_task(self._auto_clean_expired_teams())

    async def _auto_clean_expired_teams(self):
        while True:
            await asyncio.sleep(60)
            try:
                expired = await self.db.expire_teams()
                for team in expired:
                    logger.info(f"[小赤羽] 队伍 '{team['name']}' 已过期，自动解散")
            except Exception as e:
                logger.error(f"[小赤羽] 清理过期队伍失败: {e}")
    # ═══════════════════════════════════════════════
    #  LLM 工具 — 返文本数据给LLM，图片缓存用于send_message_to_user
    # ═══════════════════════════════════════════════

    @filter.llm_tool(name="apex_stats")
    async def llm_stats(self, event: AstrMessageEvent, player_name: str = ""):
        '''查询 Apex 玩家战绩并生成卡片。不传玩家名则查已绑定账号。

        Args:
            player_name(string): 玩家名或UID，留空查绑定账号
        '''
        import base64
        from mcp.types import CallToolResult, TextContent, ImageContent

        qq_id = event.get_sender_id()
        if player_name:
            if player_name.strip().isdigit():
                uid, platform = player_name.strip(), "PC"
            else:
                result = await self.apex.name_to_uid(player_name.strip())
                if not result:
                    return CallToolResult(content=[TextContent(type="text", text=f"找不到玩家 '{player_name}'")])
                uid, platform = result.uid, "PC"
        else:
            user = await self.db.get_user(qq_id)
            if not user:
                return CallToolResult(content=[TextContent(type="text", text="用户还没有绑定 Apex 账号，提示用户使用 /bind 命令绑定")])
            uid, platform = user["uid"], user["platform"]

        stats_task = self.apex.get_stats(uid, platform)
        badges_task = fetch_badges(uid, platform)
        rankdist_task = self.apex.get_rank_distribution()
        stats, badges, rank_dist = await asyncio.gather(stats_task, badges_task, rankdist_task)
        if not stats:
            return CallToolResult(content=[TextContent(type="text", text="无法获取战绩数据")])

        rp_delta = await self.db.get_rp_delta(stats.uid, platform, stats.rank_score)
        asyncio.create_task(self.db.save_rp(stats.uid, platform, stats.rank_score))

        qq_avatar = f"https://q1.qlogo.cn/g?b=qq&nk={qq_id}&s=640"
        profile_data = {
            "name": stats.name, "tag": stats.tag, "uid": stats.uid,
            "avatar_url": qq_avatar, "platform": platform, "online": stats.state,
            "level": badges.get("level") or stats.level,
            "level_pct": stats.to_next_level_pct,
            "prestige": badges.get("prestige") or stats.prestige,
            "rank_name": stats.rank_name, "rank_div": stats.rank_div,
            "rank_score": stats.rank_score, "rank_img": stats.rank_img,
            "rank_top_pct": stats.rank_top_pct, "rank_top_pct_global": stats.rank_top_pct,
            "rp_delta": rp_delta,
            "kills": badges.get("kills", 0) or stats.kills,
            "damage": stats.damage, "wins": stats.wins, "kd": stats.kd,
            "top_legends": [{"name": l["name"], "kills": l["kills"], "icon_url": l.get("icon","")} for l in stats.top_legends[:3]],
            "selected_legend": stats.selected_legend_data,
            "season_badges": badges.get("seasons", []),
            "special_badges": badges.get("special", []),
            "rank_dist_entries": rank_dist.entries if rank_dist else None,
        }
        img_bytes = await renderer.draw_profile_card(profile_data)
        img_b64 = base64.b64encode(img_bytes).decode()

        rank_zh = {"Rookie":"菜鸟","Bronze":"青铜","Silver":"白银","Gold":"黄金",
                    "Platinum":"白金","Diamond":"钻石","Master":"大师","Predator":"猎杀"}
        div_zh = {0:"4",1:"3",2:"2",3:"1"}
        rn = rank_zh.get(profile_data["rank_name"].split(" ")[0], profile_data["rank_name"])
        rd = div_zh.get(profile_data["rank_div"], str(profile_data["rank_div"]))
        state = "在线" if profile_data["online"] in ("online","in_game") else "离线"
        delta_str = f" (较上次查询 {rp_delta:+d} RP)" if rp_delta is not None else ""

        text = (
            f"玩家 {profile_data['name']} (UID {profile_data['uid']})\n"
            f"等级 Lv.{profile_data['level']} | 状态 {state}\n"
            f"段位 {rn}{rd} | RP {profile_data['rank_score']:,}{delta_str} | 全服 Top {profile_data['rank_top_pct']}%\n"
            f"生涯击杀 {profile_data['kills']:,} | 总伤害 {profile_data['damage']:,} | BR 胜场 {profile_data['wins']:,}\n"
        )
        if profile_data["top_legends"]:
            text += "常用英雄: " + ", ".join(f"{l['name']} ({l['kills']}杀)" for l in profile_data["top_legends"][:3]) + "\n"
        if rank_dist and rank_dist.entries:
            text += "段位分布: " + ", ".join(f"{e.name} {e.pct}%" for e in rank_dist.entries) + "\n"
        text += "\n请根据以上数据评论一下用户的战绩，然后用 send_message_to_user 发送战绩卡片图片。发送后不要再发任何额外消息。"

        return CallToolResult(content=[
            TextContent(type="text", text=text),
            ImageContent(type="image", data=img_b64, mimeType="image/png"),
        ])

    @filter.llm_tool(name="apex_bind")
    async def llm_bind(self, event: AstrMessageEvent, player_name: str, platform: str = "PC"):
        '''绑定 Apex 账号到当前 QQ。
        Args:
            player_name(string): 要绑定的玩家名
            platform(string): 平台，PC/PS4/X1，默认PC
        '''
        from mcp.types import CallToolResult, TextContent

        if platform.upper() not in ("PC", "PS4", "X1"):
            return CallToolResult(content=[TextContent(type="text", text="平台仅支持 PC / PS4 / X1，请提示用户")])
        platform = platform.upper()
        qq_id = event.get_sender_id()
        result = await self.apex.name_to_uid(player_name, platform)
        if not result:
            return CallToolResult(content=[TextContent(type="text", text=f"找不到玩家 '{player_name}'，请提示用户检查名字")])
        await self.db.upsert_user(qq_id, result.uid, result.name, platform)
        return CallToolResult(content=[TextContent(type="text", text=f"已成功绑定 {result.name} (UID {result.uid}, {platform})。请告知用户绑定成功。")])

    @filter.llm_tool(name="apex_unbind")
    async def llm_unbind(self, event: AstrMessageEvent):
        '''解绑当前 QQ 的 Apex 账号。'''
        from mcp.types import CallToolResult, TextContent

        qq_id = event.get_sender_id()
        user = await self.db.get_user(qq_id)
        if not user:
            return CallToolResult(content=[TextContent(type="text", text="用户还没有绑定 Apex 账号，请提示用户先绑定")])
        await self.db.delete_user(qq_id)
        return CallToolResult(content=[TextContent(type="text", text=f"已解绑 {user['name']}，请告知用户。")])

    @filter.llm_tool(name="apex_map")
    async def llm_map(self, event: AstrMessageEvent):
        '''查询当前 Apex 地图轮换，生成卡片。'''
        import base64
        from mcp.types import CallToolResult, TextContent, ImageContent

        rotation = await self.apex.get_map_rotation()
        if not rotation:
            return CallToolResult(content=[TextContent(type="text", text="获取地图轮换失败")])
        img_bytes = await renderer.draw_map_card(rotation)
        img_b64 = base64.b64encode(img_bytes).decode()
        br = rotation.br_current.map if rotation.br_current else "?"
        br_timer = f" (剩余{rotation.br_current.remaining_timer})" if rotation.br_current and rotation.br_current.remaining_timer else ""
        ranked = rotation.ranked_current.map if rotation.ranked_current else "?"
        r_next = rotation.ranked_next.map if rotation.ranked_next and rotation.ranked_next.map else ""
        text = (
            f"当前匹配: {br}{br_timer}\n"
            f"下一张匹配: {rotation.br_next.map if rotation.br_next else '?'}\n"
            f"当前排位: {ranked}\n"
        )
        if r_next:
            text += f"下一张排位: {r_next}\n"
        text += "\n请简单介绍一下地图，然后用 send_message_to_user 发送地图卡片图片。发送后不要再发任何额外消息。"
        return CallToolResult(content=[
            TextContent(type="text", text=text),
            ImageContent(type="image", data=img_b64, mimeType="image/png"),
        ])

    @filter.llm_tool(name="apex_server")
    async def llm_server(self, event: AstrMessageEvent):
        '''查询 Apex 服务器状态，生成卡片。'''
        import base64
        from mcp.types import CallToolResult, TextContent, ImageContent

        server_status = await self.apex.get_server_status()
        if not server_status or not server_status.servers:
            return CallToolResult(content=[TextContent(type="text", text="获取服务器状态失败")])
        img_bytes = await renderer.draw_server_status_card(server_status)
        img_b64 = base64.b64encode(img_bytes).decode()
        up = sum(1 for s in server_status.servers if s.is_up)
        total = len(server_status.servers)
        down_servers = [s.display_name for s in server_status.servers if not s.is_up]
        text = f"服务器状态: {up}/{total} 正常\n"
        if down_servers:
            text += f"异常服务: {', '.join(down_servers)}\n"
        text += "\n请根据服务器状态评论一下，然后用 send_message_to_user 发送服务器状态卡片图片。发送后不要再发任何额外消息。"
        return CallToolResult(content=[
            TextContent(type="text", text=text),
            ImageContent(type="image", data=img_b64, mimeType="image/png"),
        ])

    @filter.llm_tool(name="apex_master")
    async def llm_master(self, event: AstrMessageEvent):
        '''查询各平台大师人数和猎杀线分数，生成卡片。'''
        import base64
        from mcp.types import CallToolResult, TextContent, ImageContent

        predator = await self.apex.get_predator()
        if not predator:
            return CallToolResult(content=[TextContent(type="text", text="获取大师数据失败")])
        img_bytes = await renderer.draw_master_card(predator)
        img_b64 = base64.b64encode(img_bytes).decode()
        text = "各平台大师/猎杀数据:\n"
        for plat in ["PC", "PS4", "X1", "SWITCH"]:
            pd = predator.platforms.get(plat)
            if pd:
                text += f"{plat}: 猎杀线 {pd.predator_cap:,} RP | 大师/猎杀 {pd.masters_and_preds:,} 人\n"
        text += "\n请简单评论各平台数据，然后用 send_message_to_user 发送大师数据卡片图片。发送后不要再发任何额外消息。"
        return CallToolResult(content=[
            TextContent(type="text", text=text),
            ImageContent(type="image", data=img_b64, mimeType="image/png"),
        ])
