"""Tracker.gg API 封装 — 玩家资料 / 对局历史 / 搜索"""

from __future__ import annotations

import asyncio
import time
from typing import Optional
import httpx
from astrbot.api import logger

TRACKER_BASE = "https://public-api.tracker.gg/v2/apex/standard"


class TrackerClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=TRACKER_BASE,
                timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0),
                headers={"TRN-Api-Key": self.api_key},
                limits=httpx.Limits(max_connections=5, max_keepalive_connections=3),
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _get(self, path: str, params: dict = None) -> dict:
        client = await self._get_client()
        resp = await client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    async def search_player(self, query: str, platform: str = "origin") -> Optional[dict]:
        try:
            data = await self._get("/search", {"platform": platform, "query": query})
            items = data.get("data", [])
            return items[0] if items else None
        except Exception as e:
            logger.error(f"[TrackerClient] search failed: {e}")
            return None

    async def get_profile(self, platform: str, identifier: str) -> Optional[dict]:
        try:
            return await self._get(f"/profile/{platform}/{identifier}")
        except Exception as e:
            logger.error(f"[TrackerClient] profile failed: {e}")
            return None

    async def get_sessions(self, platform: str, identifier: str) -> Optional[dict]:
        try:
            return await self._get(f"/profile/{platform}/{identifier}/sessions")
        except Exception as e:
            logger.error(f"[TrackerClient] sessions failed: {e}")
            return None

    def _extract_stat(self, stats: dict, key: str) -> int:
        val = stats.get(key, {}).get("value", 0)
        if isinstance(val, str):
            val = val.replace(",", "")
        try:
            return int(val)
        except (ValueError, TypeError):
            return 0

    def parse_profile(self, data: dict) -> dict:
        """将 tracker.gg profile 响应转为与小赤羽兼容的 dict"""
        result = {
            "name": "", "uid": "", "platform": "PC", "level": 0,
            "kills": 0, "damage": 0, "wins": 0, "rank_score": 0,
            "rank_name": "Unranked", "rank_div": 0, "rank_img": "",
            "rank_top_pct": 0, "state": "offline",
            "top_legends": [], "selected_legend_data": None,
        }

        d = data.get("data", {})
        platform_info = d.get("platformInfo", {})
        result["platform"] = platform_info.get("platformSlug", "PC")
        result["name"] = platform_info.get("platformUserHandle", "") or platform_info.get("platformUserId", "")
        result["uid"] = platform_info.get("platformUserId", "") or platform_info.get("platformUserHandle", "")

        for segment in d.get("segments", []):
            seg_type = segment.get("type", "")
            stats = segment.get("stats", {})

            if seg_type == "overview":
                result["level"] = self._extract_stat(stats, "level")

            elif seg_type == "ranked":
                rank_meta = segment.get("metadata", {})
                result["rank_name"] = rank_meta.get("rankName", "Unranked")
                result["rank_div"] = rank_meta.get("division", {}).get("value", 0)
                result["rank_score"] = self._extract_stat(stats, "rankScore")
                result["rank_img"] = rank_meta.get("iconUrl", "")
                # RP delta from ranked segment
                rp_stat = stats.get("rankScore", {})
                rank_info = rp_stat.get("metadata", {}) if isinstance(rp_stat, dict) else {}
                result["rank_top_pct"] = rank_info.get("percentile", 0)

            elif seg_type == "legend" and segment.get("metadata", {}).get("isActive"):
                meta = segment.get("metadata", {})
                result["selected_legend_data"] = {
                    "name": meta.get("name", ""),
                    "icon_url": meta.get("iconUrl", ""),
                    "stats": [
                        {"name": k, "value": str(v.get("displayValue", v.get("value", "")))}
                        for k, v in stats.items()
                    ],
                }

        return result

    async def calc_rp_delta_24h(self, platform: str, identifier: str, current_rp: int) -> Optional[int]:
        """根据 sessions 对局历史计算24h内RP净变化，无数据返回 None"""
        try:
            data = await self.get_sessions(platform, identifier)
        except Exception:
            return None

        if not data:
            return None

        items = data.get("data", {}).get("items", [])
        now = time.time()
        delta = 0
        found_any = False

        for session in items:
            for match in session.get("matches", []):
                ts = match.get("metadata", {}).get("timestamp")
                if not ts:
                    continue
                try:
                    match_time = float(ts) / 1000 if ts > 1e12 else float(ts)
                except (ValueError, TypeError):
                    continue

                if now - match_time > 86400:
                    continue

                for seg in match.get("segments", []):
                    if seg.get("type") != "overview":
                        continue
                    rp_stat = seg.get("stats", {}).get("rankScore", {})
                    if not isinstance(rp_stat, dict):
                        continue
                    rank_info = rp_stat.get("rank", {}) or rp_stat.get("metadata", {})
                    old_val = rank_info.get("old") or rank_info.get("previousValue")
                    new_val = rank_info.get("new") or rank_info.get("value")
                    if old_val is not None and new_val is not None:
                        try:
                            delta += int(new_val) - int(old_val)
                            found_any = True
                        except (ValueError, TypeError):
                            pass

        return delta if found_any else None
