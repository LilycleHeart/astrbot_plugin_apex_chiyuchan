"""Apex Legends API 封装层 — 基于真实 API 响应结构"""

from __future__ import annotations

import httpx
from typing import Optional
from astrbot.api import logger

BASE_URL = "https://api.mozambiquehe.re"


class NameToUIDResult:
    def __init__(self, data: dict):
        self.name = data.get("name", "")
        self.uid = str(data.get("uid", ""))
        self.avatar = data.get("avatar", "")


class PlayerStats:
    def __init__(self, data: dict):
        g = data.get("global", {})
        rank = g.get("rank", {})
        realtime = data.get("realtime", {})
        total = data.get("total", {})
        legends = data.get("legends", {})

        self.name = g.get("name", "Unknown")
        self.tag = g.get("tag", "")
        self.uid = str(g.get("uid", ""))
        self.avatar = g.get("avatar", "")
        self.level = g.get("level", 0)
        self.to_next_level_pct = g.get("toNextLevelPercent", 0)
        self.prestige = g.get("levelPrestige", 0)

        self.rank_name = rank.get("rankName", "Unranked")
        self.rank_div = rank.get("rankDiv", 0)
        self.rank_score = rank.get("rankScore", 0)
        self.rank_img = rank.get("rankImg", "")
        self.rank_top_pct = rank.get("ALStopPercent", 0)

        self.state = realtime.get("currentState", "offline")
        self.selected_legend = realtime.get("selectedLegend", "")

        self.kills = self._total_val(total, "kills")
        self.damage = self._total_val(total, "damage")
        self.wins = self._total_val(total, "wins")
        self.kd = self._parse_kd(self._dict_val(total, "kd", "value"))

        self.top_legends = self._extract_top_legends(legends)
        self.selected_legend_data = self._extract_selected_legend(legends)

    @staticmethod
    def _total_val(total: dict, key: str) -> int:
        inner = total.get(key, {})
        if isinstance(inner, dict):
            val = inner.get("value", 0)
        else:
            val = inner
        try:
            return int(val)
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _dict_val(d: dict, key: str, sub: str):
        inner = d.get(key, {})
        if isinstance(inner, dict):
            return inner.get(sub, 0)
        return 0

    @staticmethod
    def _parse_kd(val) -> Optional[float]:
        try:
            v = float(val)
            return v if v >= 0 else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _extract_top_legends(legends: dict) -> list[dict]:
        result = []
        all_legends = legends.get("all", {})
        for legend_name, info in all_legends.items():
            if legend_name == "Global":
                continue
            kills = 0
            for tracker in info.get("data", []):
                if "kills" in tracker.get("key", "").lower() and "season" not in tracker.get("key", "").lower():
                    kills = max(kills, tracker.get("value", 0))
            if kills > 0:
                icon = info.get("ImgAssets", {}).get("icon", "")
                result.append({"name": legend_name, "kills": kills, "icon": icon})
        result.sort(key=lambda x: x["kills"], reverse=True)
        return result[:3]


    @staticmethod
    def _extract_selected_legend(legends: dict) -> dict | None:
        sel = legends.get("selected", {})
        name = sel.get("LegendName", "")
        if not name:
            return None
        icon = sel.get("ImgAssets", {}).get("icon", "")
        stats = []
        for tracker in sel.get("data", []):
            if not tracker.get("global", False):
                stats.append({
                    "name": tracker.get("name", ""),
                    "value": tracker.get("value", 0),
                })
        return {"name": name, "icon_url": icon, "stats": stats}


class MapData:
    def __init__(self, data: dict):
        self.map = data.get("map", "")
        self.code = data.get("code", "")
        self.remaining_timer = data.get("remainingTimer", "")
        self.remaining_mins = data.get("remainingMins", 0)
        self.asset = data.get("asset", "")


class LTMMode:
    def __init__(self, data: dict):
        self.event_name = data.get("eventName", "")
        self.map = data.get("map", "")
        self.remaining_timer = data.get("remainingTimer", "")


class MapRotation:
    def __init__(self, data: dict):
        br = data.get("battle_royale", {})
        ranked = data.get("ranked", {})
        ltm = data.get("ltm", {})

        self.br_current = MapData(br.get("current", {}))
        self.br_next = MapData(br.get("next", {}))

        self.ranked_current = MapData(ranked.get("current", {}))
        self.ranked_next = MapData(ranked.get("next", {}))

        self.ltm_current = LTMMode(ltm.get("current", {}))
        self.ltm_next = LTMMode(ltm.get("next", {}))


class PlatformData:
    def __init__(self, data: dict):
        self.predator_cap = data.get("val", 0)
        self.masters_and_preds = data.get("totalMastersAndPreds", 0)


class PredatorData:
    def __init__(self, data: dict):
        rp = data.get("RP", {})
        self.platforms = {
            "PC": PlatformData(rp.get("PC", {})),
            "PS4": PlatformData(rp.get("PS4", {})),
            "X1": PlatformData(rp.get("X1", {})),
            "SWITCH": PlatformData(rp.get("SWITCH", {})),
        }


class ServerInfo:
    def __init__(self, name: str, data: dict):
        self.name = name
        # API may return "Status", "status", or only have ResponseTime
        raw_status = data.get("Status") or data.get("status") or ""
        self.status = str(raw_status).upper() if raw_status else (
            "UP" if data.get("ResponseTime", 0) > 0 else "UNKNOWN"
        )
        self.response_time = data.get("ResponseTime", 0)
        self.https_code = data.get("HTTPSResponseCode", 0)

    @property
    def is_up(self) -> bool:
        return self.status.upper() == "UP"

    @property
    def status_text(self) -> str:
        s = self.status.upper()
        if s == "UP":
            return "UP"
        if s == "DOWN":
            return "DOWN"
        if s == "SLOW":
            return "SLOW"
        return s

    @property
    def display_name(self) -> str:
        name = self.name.rsplit(".", 1)[-1] if "." in self.name else self.name
        return name.replace("_", " ") \
                   .replace("Origin login", "Origin Login") \
                   .replace("EA novafusion", "EA Novafusion") \
                   .replace("EA accounts", "EA Accounts") \
                   .replace("EA datacenter", "EA Datacenter")


class ServerStatus:
    def __init__(self, data: dict):
        self.servers: list[ServerInfo] = []
        self._parse(data)
        self.servers.sort(key=lambda s: (not s.is_up, s.name))

    def _parse(self, data, prefix: str = ""):
        if isinstance(data, list):
            for i, item in enumerate(data):
                self._parse(item, f"{prefix}[{i}]")
        elif isinstance(data, dict):
            # Check if this dict itself is a server entry (has Status or ResponseTime key)
            if "Status" in data or "status" in data or "ResponseTime" in data:
                self.servers.append(ServerInfo(prefix, data))
            else:
                for name, info in data.items():
                    next_prefix = f"{prefix}.{name}" if prefix else name
                    self._parse(info, next_prefix)


class ApexClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=BASE_URL,
                timeout=httpx.Timeout(15.0),
                headers={"Authorization": self.api_key},
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _get(self, endpoint: str, params: dict = None) -> dict:
        client = await self._get_client()
        try:
            resp = await client.get(endpoint, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"[ApexClient] HTTP {e.response.status_code} for {endpoint}")
            raise
        except Exception as e:
            logger.error(f"[ApexClient] Request failed: {e}")
            raise

    async def name_to_uid(self, name: str, platform: str = "PC") -> Optional[NameToUIDResult]:
        try:
            data = await self._get("/nametouid", {"player": name, "platform": platform})
            if not data.get("uid"):
                return None
            return NameToUIDResult(data)
        except Exception:
            return None

    async def get_stats(self, uid: str, platform: str = "PC") -> Optional[PlayerStats]:
        try:
            from .ttl_cache import get as cache_get, set as cache_set
            cache_key = f"stats:{platform}:{uid}"
            cached = await cache_get(cache_key)
            if cached is not None:
                return PlayerStats(cached)

            data = await self._get("/bridge", {
                "uid": uid, "platform": platform, "merge": "1"
            })
            stats = PlayerStats(data) if data else None
            if data:
                await cache_set(cache_key, data, 60)
            return stats
        except Exception:
            return None

    async def get_map_rotation(self) -> Optional[MapRotation]:
        try:
            from .ttl_cache import get as cache_get, set as cache_set
            cache_key = "map_rotation"
            cached = await cache_get(cache_key)
            if cached is not None:
                return MapRotation(cached)

            data = await self._get("/maprotation", {"version": "2"})
            if data:
                await cache_set(cache_key, data, 300)
            return MapRotation(data) if data else None
        except Exception:
            return None

    async def get_predator(self) -> Optional[PredatorData]:
        try:
            from .ttl_cache import get as cache_get, set as cache_set
            cache_key = "predator"
            cached = await cache_get(cache_key)
            if cached is not None:
                return PredatorData(cached)

            data = await self._get("/predator")
            if data:
                await cache_set(cache_key, data, 600)
            return PredatorData(data) if data else None
        except Exception:
            return None

    async def get_server_status(self) -> Optional[ServerStatus]:
        try:
            from .ttl_cache import get as cache_get, set as cache_set
            cache_key = "server_status"
            cached = await cache_get(cache_key)
            if cached is not None:
                return ServerStatus(cached)

            data = await self._get("/servers")
            if data:
                logger.info(f"[ApexClient] Server status raw keys: {list(data.keys())[:5]}")
                await cache_set(cache_key, data, 120)
                result = ServerStatus(data)
                logger.info(f"[ApexClient] Parsed {len(result.servers)} servers")
                return result
            return None
        except Exception:
            logger.error(f"[ApexClient] Failed to get server status", exc_info=True)
            return None


    async def get_rank_distribution(self) -> Optional[RankDistribution]:
        try:
            from .ttl_cache import get as cache_get, set as cache_set
            cache_key = "rank_distribution"
            cached = await cache_get(cache_key)
            if cached is not None:
                return RankDistribution(cached)

            client = await self._get_client()
            resp = await client.get(
                "https://apexlegendsstatus.com/lib/php/rankdistrib.php",
                params={"unranked": "yes"},
            )
            resp.raise_for_status()
            data = resp.json()
            if data:
                await cache_set(cache_key, data, 1800)
            return RankDistribution(data) if data else None
        except Exception:
            return None


class RankDistEntry:
    def __init__(self, name: str, color: str, pct: float, count: int):
        self.name = name
        self.color = color
        self.pct = pct
        self.count = count


class RankDistribution:
    def __init__(self, data: list):
        self.entries: list[RankDistEntry] = []
        if not data or len(data) < 2:
            return

        # API 返回带细分的段位（如 "Rookie IV"），按大段位聚合
        major_map: dict[str, tuple[str, float, int]] = {}
        for item in data[1:]:
            raw_name = item.get("name", "")
            color = item.get("color", "#666666")
            count = item.get("totalCount", 0)
            pct = 0.0
            for v in item.get("data", []):
                if v > 0:
                    pct = float(v)
                    break
            if not raw_name:
                continue
            major = raw_name.split(" ")[0]
            if major in major_map:
                prev_color, prev_pct, prev_count = major_map[major]
                major_map[major] = (color, prev_pct + pct, prev_count + count)
            else:
                major_map[major] = (color, pct, count)

        tier_order = ["Rookie", "Bronze", "Silver", "Gold", "Platinum", "Diamond", "Master", "Predator"]
        for tier in tier_order:
            if tier in major_map:
                color, pct, count = major_map[tier]
                self.entries.append(RankDistEntry(tier, color, round(pct, 2), count))

