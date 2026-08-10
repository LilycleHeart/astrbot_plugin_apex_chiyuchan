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
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                uid         TEXT NOT NULL,
                platform    TEXT NOT NULL DEFAULT 'PC',
                rank_score  INTEGER NOT NULL,
                recorded_at TEXT DEFAULT (datetime('now','localtime'))
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

            CREATE TABLE IF NOT EXISTS badge_cache (
                uid         TEXT NOT NULL,
                platform    TEXT NOT NULL DEFAULT 'PC',
                data        TEXT NOT NULL,
                updated_at  TEXT DEFAULT (datetime('now','localtime')),
                PRIMARY KEY (uid, platform)
            );
        """)
        # migrate: 旧版 rp_history 只有单条记录（(uid,platform) 主键），迁入追加式历史表
        # 幂等处理各种中断残留状态：
        #   - rp_history 已是新结构但 rp_history_old 残留 → 直接删残留
        #   - rp_history 旧结构 + rp_history_old 残留 → 先删残留再迁移（旧表数据才是权威）
        #   - rp_history 缺失但 rp_history_old 残留（RENAME 已提交、建新表前崩溃）→ 恢复新表
        cursor = await conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='rp_history'"
        )
        row = await cursor.fetchone()
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='rp_history_old'"
        )
        old_exists = await cursor.fetchone() is not None
        if row is None and old_exists:
            # 中断最深处：rp_history 已被改走，只剩 rp_history_old → 直接建新表并恢复数据
            await conn.execute("""
                CREATE TABLE rp_history (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    uid         TEXT NOT NULL,
                    platform    TEXT NOT NULL DEFAULT 'PC',
                    rank_score  INTEGER NOT NULL,
                    recorded_at TEXT DEFAULT (datetime('now','localtime'))
                )
            """)
            await conn.execute("""
                INSERT INTO rp_history (uid, platform, rank_score, recorded_at)
                SELECT uid, platform, rank_score, recorded_at FROM rp_history_old
            """)
            await conn.execute("DROP TABLE rp_history_old")
        elif row and "id integer primary key" not in row["sql"].lower():
            # 旧结构需要迁移；残留的 rp_history_old 数据已不可信，直接删
            if old_exists:
                await conn.execute("DROP TABLE rp_history_old")
            await conn.execute("ALTER TABLE rp_history RENAME TO rp_history_old")
            await conn.execute("""
                CREATE TABLE rp_history (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    uid         TEXT NOT NULL,
                    platform    TEXT NOT NULL DEFAULT 'PC',
                    rank_score  INTEGER NOT NULL,
                    recorded_at TEXT DEFAULT (datetime('now','localtime'))
                )
            """)
            await conn.execute("""
                INSERT INTO rp_history (uid, platform, rank_score, recorded_at)
                SELECT uid, platform, rank_score, recorded_at FROM rp_history_old
            """)
            await conn.execute("DROP TABLE rp_history_old")
        elif old_exists:
            # 新结构 + 残留 rp_history_old：可能是中断残留，也可能是正在进行的迁移
            # （CREATE 新表后、INSERT 前崩溃 → 新表为空但 rp_history_old 才是权威数据）
            # 必须先检查新表是否有数据：空表 → 从 rp_history_old 恢复；有数据 → 才是真残留，清理
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM rp_history"
            )
            new_count = (await cursor.fetchone())[0]
            if new_count == 0:
                await conn.execute("""
                    INSERT INTO rp_history (uid, platform, rank_score, recorded_at)
                    SELECT uid, platform, rank_score, recorded_at FROM rp_history_old
                """)
            await conn.execute("DROP TABLE rp_history_old")
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
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_rp_uid_plat ON rp_history(uid, platform, id)")
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
            "SELECT rank_score FROM rp_history WHERE uid = ? AND platform = ? "
            "ORDER BY id DESC LIMIT 1",
            (uid, platform),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        return current_score - row["rank_score"]

    async def save_rp(self, uid: str, platform: str, rank_score: int):
        """追加一条 RP 记录（同值不重复记，避免连续查询刷屏）"""
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT rank_score FROM rp_history WHERE uid = ? AND platform = ? "
            "ORDER BY id DESC LIMIT 1",
            (uid, platform),
        ) as cursor:
            last = await cursor.fetchone()
        if last is not None and last["rank_score"] == rank_score:
            return  # 无变化，不追加
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await conn.execute(
            "INSERT INTO rp_history (uid, platform, rank_score, recorded_at) VALUES (?, ?, ?, ?)",
            (uid, platform, rank_score, now),
        )
        await conn.commit()

    async def get_rp_history(
        self, uid: str, platform: str, limit: int = 12
    ) -> list[dict]:
        """按时间正序返回 RP 历史（最新 limit 条），用于折线图"""
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT rank_score, recorded_at FROM rp_history "
            "WHERE uid = ? AND platform = ? "
            "ORDER BY id DESC LIMIT ?",
            (uid, platform, limit),
        ) as cursor:
            rows = await cursor.fetchall()
        return [{"score": r["rank_score"], "at": r["recorded_at"]} for r in reversed(rows)]

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

    # ── 徽章缓存 ──

    async def get_badge_cache(self, uid: str, platform: str = "PC") -> dict | None:
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT data, updated_at FROM badge_cache WHERE uid = ? AND platform = ?",
            (uid, platform),
        ) as cursor:
            row = await cursor.fetchone()
        if row:
            import json
            return {"data": json.loads(row["data"]), "updated_at": row["updated_at"]}
        return None

    async def set_badge_cache(self, uid: str, platform: str, data: dict):
        import json
        conn = await self._get_conn()
        await conn.execute(
            "INSERT OR REPLACE INTO badge_cache (uid, platform, data, updated_at) VALUES (?, ?, ?, datetime('now','localtime'))",
            (uid, platform, json.dumps(data)),
        )
        await conn.commit()
