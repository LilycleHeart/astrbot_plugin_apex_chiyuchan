"""SQLite 异步数据库层 — 用户绑定 / 队伍管理 (持久连接 + WAL 模式)"""

from __future__ import annotations

import asyncio
import aiosqlite
from pathlib import Path
from datetime import datetime, timedelta
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.api import logger


class Database:
    def __init__(self):
        data_dir = Path(get_astrbot_data_path()) / "plugin_data" / "apex_xiaochiyu"
        data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = data_dir / "xiaochiyu.db"
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._conn = await aiosqlite.connect(str(self.db_path))
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.row_factory = aiosqlite.Row
        return self._conn

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def init(self):
        conn = await self._get_conn()
        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                qq_id      TEXT PRIMARY KEY,
                uid        TEXT NOT NULL,
                name       TEXT NOT NULL,
                platform   TEXT DEFAULT 'PC',
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS teams (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                owner_qq    TEXT NOT NULL,
                ttl_hours   INTEGER DEFAULT 12,
                created_at  TEXT DEFAULT (datetime('now','localtime')),
                expires_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS team_members (
                team_id     INTEGER NOT NULL,
                qq_id       TEXT NOT NULL,
                joined_at   TEXT DEFAULT (datetime('now','localtime')),
                PRIMARY KEY (team_id, qq_id)
            );

            CREATE TABLE IF NOT EXISTS rp_history (
                uid         TEXT NOT NULL,
                platform    TEXT NOT NULL DEFAULT 'PC',
                rank_score  INTEGER NOT NULL,
                recorded_at TEXT DEFAULT (datetime('now','localtime')),
                PRIMARY KEY (uid, platform)
            );
        """)
        await conn.commit()
        logger.info("[Database] SQLite tables ready (WAL mode)")

    async def upsert_user(self, qq_id: str, uid: str, name: str, platform: str):
        conn = await self._get_conn()
        await conn.execute(
            "INSERT OR REPLACE INTO users (qq_id, uid, name, platform) VALUES (?, ?, ?, ?)",
            (qq_id, uid, name, platform),
        )
        await conn.commit()

    async def get_user(self, qq_id: str) -> dict | None:
        conn = await self._get_conn()
        async with conn.execute("SELECT * FROM users WHERE qq_id = ?", (qq_id,)) as cursor:
            row = await cursor.fetchone()
        if row:
            return dict(row)
        return None

    async def delete_user(self, qq_id: str):
        conn = await self._get_conn()
        await conn.execute("DELETE FROM users WHERE qq_id = ?", (qq_id,))
        await conn.commit()

    # ── 队伍操作 ──

    async def create_team(self, name: str, owner_qq: str, ttl_hours: int = 12) -> int | None:
        existing = await self.get_team_by_member(owner_qq)
        if existing:
            return None

        expires_at = datetime.now() + timedelta(hours=ttl_hours)
        expires_str = expires_at.strftime("%Y-%m-%d %H:%M:%S")

        conn = await self._get_conn()
        async with self._lock:
            cursor = await conn.execute(
                "INSERT INTO teams (name, owner_qq, ttl_hours, expires_at) VALUES (?, ?, ?, ?)",
                (name, owner_qq, ttl_hours, expires_str),
            )
            team_id = cursor.lastrowid
            await conn.execute(
                "INSERT INTO team_members (team_id, qq_id) VALUES (?, ?)",
                (team_id, owner_qq),
            )
            await conn.commit()
        return team_id

    async def join_team(self, name: str, qq_id: str) -> str | None:
        existing = await self.get_team_by_member(qq_id)
        if existing:
            return "你已在队伍中"

        conn = await self._get_conn()
        async with conn.execute(
            "SELECT id, owner_qq, ttl_hours FROM teams WHERE name = ?", (name,)
        ) as cursor:
            team = await cursor.fetchone()

        if not team:
            return "队伍不存在"
        team_id = team[0]

        async with conn.execute(
            "SELECT COUNT(*) FROM team_members WHERE team_id = ?", (team_id,)
        ) as cursor:
            count = (await cursor.fetchone())[0]

        if count >= 3:
            return "队伍已满（上限3人）"

        await conn.execute(
            "INSERT INTO team_members (team_id, qq_id) VALUES (?, ?)",
            (team_id, qq_id),
        )
        await conn.commit()
        return None

    async def leave_team(self, qq_id: str) -> str | None:
        team = await self.get_team_by_member(qq_id)
        if not team:
            return "你不在任何队伍中"

        team_id = team["id"]
        conn = await self._get_conn()
        await conn.execute("DELETE FROM team_members WHERE team_id = ? AND qq_id = ?", (team_id, qq_id))
        if team["owner_qq"] == qq_id:
            await conn.execute("DELETE FROM team_members WHERE team_id = ?", (team_id,))
            await conn.execute("DELETE FROM teams WHERE id = ?", (team_id,))
        else:
            async with conn.execute("SELECT COUNT(*) FROM team_members WHERE team_id = ?", (team_id,)) as cursor:
                remaining = (await cursor.fetchone())[0]
            if remaining == 0:
                await conn.execute("DELETE FROM teams WHERE id = ?", (team_id,))
        await conn.commit()
        return None

    async def disband_team(self, qq_id: str) -> str | None:
        team = await self.get_team_by_member(qq_id)
        if not team:
            return "你不在任何队伍中"
        if team["owner_qq"] != qq_id:
            return "只有队长才能解散队伍"

        team_id = team["id"]
        conn = await self._get_conn()
        await conn.execute("DELETE FROM team_members WHERE team_id = ?", (team_id,))
        await conn.execute("DELETE FROM teams WHERE id = ?", (team_id,))
        await conn.commit()
        return None

    async def get_team_by_member(self, qq_id: str) -> dict | None:
        conn = await self._get_conn()
        async with conn.execute("""
            SELECT t.id, t.name, t.owner_qq, t.ttl_hours, t.created_at, t.expires_at
            FROM teams t JOIN team_members m ON t.id = m.team_id
            WHERE m.qq_id = ?
        """, (qq_id,)) as cursor:
            row = await cursor.fetchone()
        if row:
            return dict(row)
        return None

    async def get_team_members(self, team_id: int) -> list[str]:
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT qq_id FROM team_members WHERE team_id = ?", (team_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]

    async def get_all_teams(self) -> list[dict]:
        conn = await self._get_conn()
        async with conn.execute("""
            SELECT t.id, t.name, t.owner_qq, t.ttl_hours, t.created_at, t.expires_at,
                   m.qq_id as member_qq
            FROM teams t
            LEFT JOIN team_members m ON t.id = m.team_id
            ORDER BY t.id
        """) as cursor:
            rows = await cursor.fetchall()

        teams_map: dict[int, dict] = {}
        for row in rows:
            tid = row[0]
            if tid not in teams_map:
                teams_map[tid] = {
                    "id": row[0], "name": row[1], "owner_qq": row[2],
                    "ttl_hours": row[3], "created_at": row[4], "expires_at": row[5],
                    "members": [],
                }
            member_qq = row[6]
            if member_qq:
                teams_map[tid]["members"].append(member_qq)

        result = list(teams_map.values())
        for t in result:
            t["member_count"] = len(t["members"])
        return result

    async def set_team_ttl(self, qq_id: str, hours: int) -> str | None:
        team = await self.get_team_by_member(qq_id)
        if not team:
            return "你不在任何队伍中"
        if team["owner_qq"] != qq_id:
            return "只有队长才能修改时限"
        if hours < 1 or hours > 48:
            return "时限范围 1~48 小时"

        expires_at = datetime.now() + timedelta(hours=hours)
        expires_str = expires_at.strftime("%Y-%m-%d %H:%M:%S")

        conn = await self._get_conn()
        await conn.execute(
            "UPDATE teams SET ttl_hours = ?, expires_at = ? WHERE id = ?",
            (hours, expires_str, team["id"]),
        )
        await conn.commit()
        return None

    async def expire_teams(self) -> list[dict]:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = await self._get_conn()

        async with conn.execute(
            "SELECT id, name, owner_qq FROM teams WHERE expires_at <= ?", (now,)
        ) as cursor:
            rows = await cursor.fetchall()
            expired_ids = [row[0] for row in rows]

        if not expired_ids:
            return []

        expired = [{"id": row[0], "name": row[1], "owner_qq": row[2]} for row in rows]

        placeholders = ",".join("?" * len(expired_ids))
        await conn.execute(f"DELETE FROM team_members WHERE team_id IN ({placeholders})", expired_ids)
        await conn.execute(f"DELETE FROM teams WHERE id IN ({placeholders})", expired_ids)
        await conn.commit()
        return expired

    async def get_rp_delta(self, uid: str, platform: str, current_score: int) -> int | None:
        """距上次查询的 RP 变化，无记录返回 None"""
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT rank_score FROM rp_history WHERE uid = ? AND platform = ?",
            (uid, platform),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        return current_score - row[0]

    async def save_rp(self, uid: str, platform: str, rank_score: int):
        conn = await self._get_conn()
        await conn.execute(
            "INSERT OR REPLACE INTO rp_history (uid, platform, rank_score) VALUES (?, ?, ?)",
            (uid, platform, rank_score),
        )
        await conn.commit()
