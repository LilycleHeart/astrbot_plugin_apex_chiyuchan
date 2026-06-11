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
        data_dir = Path(get_astrbot_data_path()) / "plugin_data" / "astrbot_plugin_apex_chiyuchan"
        data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = data_dir / "chiyuchan.db"
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            async with self._lock:
                if self._conn is None:
                    self._conn = await aiosqlite.connect(str(self.db_path))
                    await self._conn.execute("PRAGMA journal_mode=WAL")
                    await self._conn.execute("PRAGMA foreign_keys=ON")
                    self._conn.row_factory = aiosqlite.Row
        else:
            try:
                await self._conn.execute("SELECT 1")
            except Exception:
                async with self._lock:
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

            CREATE TABLE IF NOT EXISTS rp_history (
                uid         TEXT NOT NULL,
                platform    TEXT NOT NULL DEFAULT 'PC',
                rank_score  INTEGER NOT NULL,
                recorded_at TEXT DEFAULT (datetime('now','localtime')),
                PRIMARY KEY (uid, platform)
            );

            CREATE TABLE IF NOT EXISTS monitor (
                session_id    TEXT PRIMARY KEY,
                enabled       INTEGER DEFAULT 1,
                last_state    TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS lfg_users (
                qq_id       TEXT NOT NULL,
                group_id    TEXT NOT NULL DEFAULT 'global',
                uid         TEXT NOT NULL,
                name        TEXT NOT NULL,
                qq_name     TEXT DEFAULT '',
                platform    TEXT DEFAULT 'PC',
                mode        TEXT DEFAULT 'ranked',
                registered_at TEXT DEFAULT (datetime('now','localtime')),
                PRIMARY KEY (group_id, qq_id)
            );
        """)
        # migrate: add qq_name / group_id columns; recreate PK if old schema
        try:
            await conn.execute("ALTER TABLE lfg_users ADD COLUMN qq_name TEXT DEFAULT ''")
        except Exception:
            pass
        try:
            await conn.execute("ALTER TABLE lfg_users ADD COLUMN group_id TEXT NOT NULL DEFAULT 'global'")
        except Exception:
            pass
        # check if old schema (single PK on qq_id) — recreate with composite PK
        cursor = await conn.execute("PRAGMA table_info(lfg_users)")
        cols = {row[1]: row for row in await cursor.fetchall()}
        pk_cols = [name for name, info in cols.items() if info[5] == 1]
        if pk_cols == ["qq_id"]:  # old single-column PK
            await conn.execute("""
                CREATE TABLE lfg_users_new (
                    qq_id TEXT NOT NULL, group_id TEXT NOT NULL DEFAULT 'global',
                    uid TEXT NOT NULL, name TEXT NOT NULL, qq_name TEXT DEFAULT '',
                    platform TEXT DEFAULT 'PC', mode TEXT DEFAULT 'ranked',
                    registered_at TEXT DEFAULT (datetime('now','localtime')),
                    kills INTEGER DEFAULT 0, level INTEGER DEFAULT 0,
                    prestige INTEGER DEFAULT 0, rank_pos INTEGER DEFAULT 0,
                    rank_name TEXT DEFAULT '', rank_score INTEGER DEFAULT 0,
                    rank_img TEXT DEFAULT '', state TEXT DEFAULT 'offline', stats_updated_at TEXT,
                    PRIMARY KEY (group_id, qq_id)
                )
            """)
            await conn.execute("""
                INSERT OR IGNORE INTO lfg_users_new
                SELECT qq_id, COALESCE(group_id,'global'), uid, name, COALESCE(qq_name,''),
                       platform, mode, registered_at,
                       0,0,0,0,'',0,'','offline',NULL FROM lfg_users
            """)
            await conn.execute("DROP TABLE lfg_users")
            await conn.execute("ALTER TABLE lfg_users_new RENAME TO lfg_users")
        else:
            # add stats columns if missing
            for col_def in (
                "kills INTEGER DEFAULT 0", "level INTEGER DEFAULT 0",
                "prestige INTEGER DEFAULT 0", "rank_pos INTEGER DEFAULT 0",
                "rank_score INTEGER DEFAULT 0", "state TEXT DEFAULT 'offline'",
                "rank_name TEXT DEFAULT ''", "rank_img TEXT DEFAULT ''",
                "stats_updated_at TEXT",
            ):
                col_name = col_def.split()[0]
                if col_name not in cols:
                    try:
                        await conn.execute(f"ALTER TABLE lfg_users ADD COLUMN {col_def}")
                    except Exception:
                        pass
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_rp_uid_plat ON rp_history(uid, platform)")
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
        async with conn.execute(
            "SELECT * FROM users WHERE qq_id = ?", (qq_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row:
            return dict(row)
        return None

    async def delete_user(self, qq_id: str):
        conn = await self._get_conn()
        await conn.execute("DELETE FROM users WHERE qq_id = ?", (qq_id,))
        await conn.commit()

    # ── RP 操作 ──

    async def get_rp_delta(
        self, uid: str, platform: str, current_score: int
    ) -> int | None:
        """距上次查询的 RP 变化，无记录返回 None"""
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT rank_score FROM rp_history WHERE uid = ? AND platform = ?",
            (uid, platform),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        return current_score - row["rank_score"]

    async def save_rp(self, uid: str, platform: str, rank_score: int):
        conn = await self._get_conn()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await conn.execute(
            "INSERT OR REPLACE INTO rp_history (uid, platform, rank_score, recorded_at) VALUES (?, ?, ?, ?)",
            (uid, platform, rank_score, now),
        )
        await conn.commit()

    async def get_monitor(self, session_id: str) -> dict | None:
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT * FROM monitor WHERE session_id = ?", (session_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def set_monitor(self, session_id: str, enabled: bool, last_state: str = ""):
        conn = await self._get_conn()
        await conn.execute(
            "INSERT OR REPLACE INTO monitor (session_id, enabled, last_state) VALUES (?, ?, ?)",
            (session_id, int(enabled), last_state),
        )
        await conn.commit()

    async def remove_monitor(self, session_id: str):
        conn = await self._get_conn()
        await conn.execute("DELETE FROM monitor WHERE session_id = ?", (session_id,))
        await conn.commit()

    async def list_monitor_sessions(self) -> list[dict]:
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT * FROM monitor WHERE enabled = 1"
        ) as cursor:
            rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def update_monitor_state(self, session_id: str, last_state: str):
        conn = await self._get_conn()
        await conn.execute(
            "UPDATE monitor SET last_state = ? WHERE session_id = ?",
            (last_state, session_id),
        )
        await conn.commit()

    async def upsert_lfg_user(self, qq_id: str, group_id: str, uid: str, name: str, platform: str, mode: str = "ranked", qq_name: str = "", kills: int = 0, level: int = 0, prestige: int = 0, rank_pos: int = 0, rank_name: str = "", rank_score: int = 0, rank_img: str = "", state: str = "offline"):
        conn = await self._get_conn()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await conn.execute(
            "INSERT OR REPLACE INTO lfg_users (qq_id, group_id, uid, name, qq_name, platform, mode, registered_at, kills, level, prestige, rank_pos, rank_name, rank_score, rank_img, state, stats_updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'), ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (qq_id, group_id, uid, name, qq_name, platform, mode, kills, level, prestige, rank_pos, rank_name, rank_score, rank_img, state, now),
        )
        await conn.commit()

    async def remove_lfg_user(self, qq_id: str, group_id: str):
        conn = await self._get_conn()
        await conn.execute("DELETE FROM lfg_users WHERE qq_id = ? AND group_id = ?", (qq_id, group_id))
        await conn.commit()

    async def get_lfg_user(self, qq_id: str, group_id: str) -> dict | None:
        conn = await self._get_conn()
        async with conn.execute("SELECT * FROM lfg_users WHERE qq_id = ? AND group_id = ?", (qq_id, group_id)) as cursor:
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_lfg_users(self, group_id: str = "") -> list[dict]:
        conn = await self._get_conn()
        if group_id:
            async with conn.execute("SELECT * FROM lfg_users WHERE group_id = ? ORDER BY registered_at DESC", (group_id,)) as cursor:
                rows = await cursor.fetchall()
        else:
            async with conn.execute("SELECT * FROM lfg_users ORDER BY registered_at DESC") as cursor:
                rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def update_lfg_qq_name(self, qq_id: str, group_id: str, qq_name: str):
        conn = await self._get_conn()
        await conn.execute(
            "UPDATE lfg_users SET qq_name = ? WHERE qq_id = ? AND group_id = ?",
            (qq_name, qq_id, group_id),
        )
        await conn.commit()

    async def get_all_lfg_uids(self) -> list[dict]:
        conn = await self._get_conn()
        async with conn.execute("SELECT qq_id, group_id, uid, platform FROM lfg_users") as cursor:
            rows = await cursor.fetchall()
        return [dict(r) for r in rows]
