"""OmniPublish V2.0 — SQLite 数据库管理（aiosqlite，兼容 asyncpg API）"""

import aiosqlite
import asyncio
import json
import os
import re
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from config import settings

# 数据库文件路径（优先环境变量，其次 config.json，最后 data/ 默认目录）
_default_db = Path(__file__).parent.parent / "data" / "omnipub.db"
DB_PATH: str = os.environ.get("DB_PATH", settings.db_path or str(_default_db))

# 确保 data 目录存在
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════
# PostgreSQL → SQLite SQL 转换
# ══════════════════════════════════════

def _pg_to_sqlite(sql: str) -> str:
    """把 asyncpg 风格的 SQL 转成 SQLite 语法。"""
    # EXTRACT(EPOCH FROM (x - y)) → (julianday(x) - julianday(y)) * 86400
    sql = re.sub(
        r"EXTRACT\s*\(\s*EPOCH\s+FROM\s*\(([^)]+?)\s*-\s*([^)]+?)\)\s*\)",
        r"(julianday(\1) - julianday(\2)) * 86400",
        sql,
        flags=re.IGNORECASE,
    )
    # = ANY($N) → IN (?)  -- placeholder; actual expansion in _expand_any()
    sql = re.sub(r"=\s*ANY\s*\(\s*\$\d+\s*\)", "IN (?)", sql, flags=re.IGNORECASE)
    # $1, $2 → ?
    sql = re.sub(r'\$\d+', '?', sql)
    # col::date → date(col)
    sql = re.sub(r'(\w+)::date', r'date(\1)', sql)
    # CURRENT_DATE - 1 → date('now', '-1 day')
    sql = re.sub(r"CURRENT_DATE\s*-\s*(\d+)", r"date('now', '-\1 day')", sql)
    # CURRENT_DATE → date('now')
    sql = sql.replace('CURRENT_DATE', "date('now')")
    # INTERVAL 'N days' → handled in specific queries
    sql = re.sub(r"CURRENT_TIMESTAMP\s*-\s*INTERVAL\s+'(\d+)\s+days?'",
                 r"datetime('now', '-\1 days')", sql)
    return sql


def _expand_any(sql: str, args: tuple) -> tuple[str, tuple]:
    """Expand IN (?) placeholders that correspond to list arguments.

    When asyncpg-style ``= ANY($N)`` is used with a list argument,
    ``_pg_to_sqlite`` converts it to ``IN (?)``.  This helper further
    expands each ``IN (?)`` whose matching positional arg is a list/tuple
    into ``IN (?,?,?...)`` and flattens the args accordingly.
    """
    # Fast path – no IN (?) at all
    if "IN (?)" not in sql:
        return sql, args

    parts: list[str] = []
    new_args: list[Any] = []
    arg_idx = 0
    i = 0
    while i < len(sql):
        # Look for the next '?'
        qpos = sql.find("?", i)
        if qpos == -1:
            parts.append(sql[i:])
            break
        # Check if this '?' is preceded by 'IN ('
        prefix_check = sql[:qpos].rstrip()
        if arg_idx < len(args) and isinstance(args[arg_idx], (list, tuple)):
            if prefix_check.endswith("IN ("):
                lst = args[arg_idx]
                placeholders = ",".join("?" for _ in lst) if lst else "'__EMPTY__'"
                parts.append(sql[i:qpos])
                parts.append(placeholders)
                new_args.extend(lst)
                arg_idx += 1
                i = qpos + 1
                continue
        parts.append(sql[i:qpos + 1])
        if arg_idx < len(args):
            new_args.append(args[arg_idx])
        arg_idx += 1
        i = qpos + 1
    return "".join(parts), tuple(new_args)


# ══════════════════════════════════════
# 行包装器（让 dict 访问与 asyncpg 一致）
# ══════════════════════════════════════

class _Row(dict):
    """dict 子类，支持 row["col"] 和 dict(row)，与 asyncpg Record 兼容。"""
    pass


def _make_rows(cursor: aiosqlite.Cursor, raw_rows) -> list[_Row]:
    cols = [d[0] for d in cursor.description] if cursor.description else []
    return [_Row(zip(cols, row)) for row in raw_rows]


# ══════════════════════════════════════
# 连接包装器（提供 asyncpg 同名方法）
# ══════════════════════════════════════

class _Conn:
    def __init__(self, conn: aiosqlite.Connection):
        self._c = conn
        self._in_transaction = False

    @asynccontextmanager
    async def transaction(self):
        """Async context manager for explicit transactions.

        Usage::

            async with conn.transaction():
                await conn.execute(...)
                await conn.execute(...)
        """
        await self._c.execute("BEGIN")
        self._in_transaction = True
        try:
            yield self
            await self._c.execute("COMMIT")
        except BaseException:
            await self._c.execute("ROLLBACK")
            raise
        finally:
            self._in_transaction = False

    async def execute(self, sql: str, *args) -> str:
        sql = _pg_to_sqlite(sql)
        sql, args = _expand_any(sql, args)
        await self._c.execute(sql, args)
        if not self._in_transaction:
            await self._c.commit()
        return f"OK"

    async def executemany(self, sql: str, args_list) -> None:
        sql = _pg_to_sqlite(sql)
        await self._c.executemany(sql, args_list)
        if not self._in_transaction:
            await self._c.commit()

    async def fetch(self, sql: str, *args) -> list[_Row]:
        sql = _pg_to_sqlite(sql)
        sql, args = _expand_any(sql, args)
        async with self._c.execute(sql, args) as cur:
            rows = await cur.fetchall()
            return _make_rows(cur, rows)

    async def fetchrow(self, sql: str, *args) -> Optional[_Row]:
        sql = _pg_to_sqlite(sql)
        sql, args = _expand_any(sql, args)
        async with self._c.execute(sql, args) as cur:
            row = await cur.fetchone()
            if row is None:
                return None
            return _make_rows(cur, [row])[0]

    async def fetchval(self, sql: str, *args) -> Any:
        sql = _pg_to_sqlite(sql)
        sql, args = _expand_any(sql, args)
        async with self._c.execute(sql, args) as cur:
            row = await cur.fetchone()
            return row[0] if row else None

    # 便捷：在同一事务内多次写操作
    async def execute_many_ddl(self, statements: list[str]) -> None:
        for sql in statements:
            sql = sql.strip()
            if sql:
                await self._c.execute(sql)
        await self._c.commit()


# ══════════════════════════════════════
# 连接池（单机版：共享同一个连接）
# ══════════════════════════════════════

class _Pool:
    """
    单机 SQLite 伪连接池。
    因 SQLite 文件锁限制，使用单连接 + asyncio.Lock 串行访问。
    WAL 模式下读并发没问题，写操作自动排队。
    """
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._conn = await aiosqlite.connect(self._db_path)
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA foreign_keys=ON")
            await self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn

    @asynccontextmanager
    async def acquire(self):
        """with pool.acquire() as conn: — 与 asyncpg Pool 接口一致。"""
        async with self._lock:
            raw = await self._get_conn()
            yield _Conn(raw)

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None


# ══════════════════════════════════════
# 全局池单例
# ══════════════════════════════════════

_pool: Optional[_Pool] = None
_pool_lock = asyncio.Lock()


async def get_pool() -> _Pool:
    global _pool
    if _pool is not None:
        return _pool
    async with _pool_lock:
        if _pool is None:
            _pool = _Pool(DB_PATH)
    return _pool


async def get_db() -> _Conn:
    """向后兼容旧接口（不推荐直接用，请用 pool.acquire()）。

    NOTE: acquires the pool lock so the caller MUST release quickly.
    Prefer ``async with pool.acquire() as conn`` instead.
    """
    pool = await get_pool()
    # Properly acquire through the pool lock
    await pool._lock.acquire()
    raw = await pool._get_conn()
    return _Conn(raw)


# ══════════════════════════════════════
# 建表 SQL（SQLite 语法）
# ══════════════════════════════════════

SCHEMA_SQL = [
    # 用户表
    """
    CREATE TABLE IF NOT EXISTS users (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        username     TEXT NOT NULL UNIQUE,
        password     TEXT NOT NULL,
        display_name TEXT NOT NULL DEFAULT '',
        dept         TEXT DEFAULT '',
        role         TEXT DEFAULT 'editor',
        is_active    INTEGER DEFAULT 1,
        created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,

    # 业务线/平台配置表
    """
    CREATE TABLE IF NOT EXISTS platforms (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT NOT NULL UNIQUE,
        dept            TEXT DEFAULT '',
        categories      TEXT DEFAULT '[]',
        img_wm_file     TEXT DEFAULT '',
        img_wm_position TEXT DEFAULT 'bottom-right',
        img_wm_width    INTEGER DEFAULT 264,
        img_wm_opacity  INTEGER DEFAULT 100,
        vid_wm_file     TEXT DEFAULT '',
        vid_wm_mode     TEXT DEFAULT 'corner-cycle',
        vid_wm_scale    INTEGER DEFAULT 35,
        vid_wm_file2    TEXT DEFAULT '',
        api_base_url    TEXT DEFAULT '',
        project_code    TEXT DEFAULT '',
        layout_template TEXT DEFAULT '',
        cms_username    TEXT DEFAULT '',
        cms_password    TEXT DEFAULT '',
        session_token   TEXT DEFAULT '',
        session_expires TEXT DEFAULT '',
        is_active       INTEGER DEFAULT 1,
        created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,

    # 发帖任务主表
    """
    CREATE TABLE IF NOT EXISTS tasks (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        task_no            TEXT NOT NULL UNIQUE,
        title              TEXT DEFAULT '',
        folder_path        TEXT NOT NULL,
        created_by         INTEGER NOT NULL REFERENCES users(id),
        current_step       INTEGER DEFAULT 0,
        status             TEXT DEFAULT 'draft',
        target_platforms   TEXT DEFAULT '[]',
        file_manifest      TEXT DEFAULT '{}',
        protagonist        TEXT DEFAULT '',
        event_desc         TEXT DEFAULT '',
        style              TEXT DEFAULT '反转打脸风',
        author             TEXT DEFAULT '',
        categories         TEXT DEFAULT '[]',
        confirmed_title    TEXT DEFAULT '',
        confirmed_keywords TEXT DEFAULT '',
        confirmed_body     TEXT DEFAULT '',
        rename_prefix      TEXT DEFAULT '',
        rename_mapping     TEXT DEFAULT '[]',
        cover_layout       TEXT DEFAULT 'triple',
        cover_path         TEXT DEFAULT '',
        cover_candidates   TEXT DEFAULT '[]',
        created_at         DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at         DATETIME DEFAULT CURRENT_TIMESTAMP,
        finished_at        DATETIME DEFAULT NULL
    )
    """,

    # 步骤状态表
    """
    CREATE TABLE IF NOT EXISTS task_steps (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id     INTEGER NOT NULL REFERENCES tasks(id),
        step        INTEGER NOT NULL,
        status      TEXT DEFAULT 'pending',
        started_at  DATETIME DEFAULT NULL,
        finished_at DATETIME DEFAULT NULL,
        data        TEXT DEFAULT '{}',
        error       TEXT DEFAULT NULL,
        UNIQUE(task_id, step)
    )
    """,

    # 平台子任务表
    """
    CREATE TABLE IF NOT EXISTS platform_tasks (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id            INTEGER NOT NULL REFERENCES tasks(id),
        platform_id        INTEGER NOT NULL REFERENCES platforms(id),
        wm_status          TEXT DEFAULT 'pending',
        wm_progress        REAL DEFAULT 0,
        wm_images_dir      TEXT DEFAULT '',
        wm_video_path      TEXT DEFAULT '',
        wm_cover_path      TEXT DEFAULT '',
        wm_error           TEXT DEFAULT NULL,
        upload_status      TEXT DEFAULT 'pending',
        upload_progress    REAL DEFAULT 0,
        mp4_url            TEXT DEFAULT '',
        transcode_status   TEXT DEFAULT 'pending',
        transcode_progress REAL DEFAULT 0,
        video_url          TEXT DEFAULT '',
        publish_status     TEXT DEFAULT 'pending',
        publish_result     TEXT DEFAULT '{}',
        publish_error      TEXT DEFAULT NULL,
        created_at         DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at         DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(task_id, platform_id)
    )
    """,

    # 操作日志表
    """
    CREATE TABLE IF NOT EXISTS task_logs (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id     INTEGER NOT NULL REFERENCES tasks(id),
        step        INTEGER DEFAULT NULL,
        platform_id INTEGER DEFAULT NULL,
        level       TEXT DEFAULT 'info',
        message     TEXT NOT NULL,
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,

    # 账号表
    """
    CREATE TABLE IF NOT EXISTS accounts (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        platform_id         INTEGER NOT NULL REFERENCES platforms(id) ON DELETE CASCADE,
        username            TEXT DEFAULT '',
        password_encrypted  TEXT DEFAULT '',
        login_status        TEXT DEFAULT 'unknown',
        last_login_at       DATETIME DEFAULT NULL,
        last_error          TEXT DEFAULT '',
        created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(platform_id)
    )
    """,

    # 索引
    "CREATE INDEX IF NOT EXISTS idx_tasks_created_by ON tasks(created_by)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_platform_tasks_task ON platform_tasks(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_task_logs_task ON task_logs(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_task_steps_task ON task_steps(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_status_created ON tasks(status, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON tasks(created_by, status)",
    "CREATE INDEX IF NOT EXISTS idx_pt_platform ON platform_tasks(platform_id)",
    "CREATE INDEX IF NOT EXISTS idx_pt_platform_publish ON platform_tasks(platform_id, publish_status)",
    "CREATE INDEX IF NOT EXISTS idx_logs_created ON task_logs(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_logs_task_step ON task_logs(task_id, step)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_no ON tasks(task_no)",
]


# ══════════════════════════════════════
# 初始化 / 关闭
# ══════════════════════════════════════

async def init_db():
    """初始化数据库（建表 + 默认数据）。"""
    print(f"[DB] Initializing SQLite: {DB_PATH}")
    pool = await get_pool()

    async with pool.acquire() as conn:
        # 建表
        await conn.execute_many_ddl(SCHEMA_SQL)

        # 插入默认管理员（admin / admin123）
        await conn.execute(
            """INSERT INTO users (username, password, display_name, dept, role)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT (username) DO NOTHING""",
            'admin',
            '$2b$12$8DgwGZ8lNtWmiC/967ocIuldJep3UNUNbkeJXrYh1wuHggDoHRVqq',
            '管理员', '系统', 'admin',
        )

        # 统计
        user_count     = await conn.fetchval("SELECT COUNT(*) FROM users")
        platform_count = await conn.fetchval("SELECT COUNT(*) FROM platforms")
        task_count     = await conn.fetchval("SELECT COUNT(*) FROM tasks")
        print(f"[DB] Users: {user_count}, Platforms: {platform_count}, Tasks: {task_count}")

        # 清理过期日志
        await cleanup_old_logs(conn)

    print("[DB] SQLite initialized successfully")


async def close_db():
    """关闭连接池。"""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def get_next_task_no() -> str:
    """生成下一个任务编号 #0001 格式。

    NOTE: 仍有微小竞态窗口。调用方（create_task）应捕获
    IntegrityError 并重试。
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        max_no = await conn.fetchval(
            "SELECT COALESCE(MAX(CAST(SUBSTR(task_no, 2) AS INTEGER)), 0) FROM tasks"
        )
        return f"#{max_no + 1:04d}"


# ══════════════════════════════════════
# 维护工具
# ══════════════════════════════════════

async def cleanup_old_logs(conn: _Conn, days: int = 30) -> int:
    """清理超过 N 天的操作日志。"""
    result = await conn.fetchval(
        "SELECT COUNT(*) FROM task_logs WHERE created_at < datetime('now', '-' || ? || ' days')",
        str(days),
    )
    await conn.execute(
        "DELETE FROM task_logs WHERE created_at < datetime('now', '-' || ? || ' days')",
        str(days),
    )
    return result or 0


async def get_db_stats() -> dict:
    """获取数据库统计信息。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        stats = {}
        for table in ['users', 'platforms', 'tasks', 'task_steps', 'platform_tasks', 'task_logs']:
            stats[table] = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")

        # SQLite 文件大小
        try:
            size_bytes = os.path.getsize(DB_PATH)
            stats['db_size_mb'] = round(size_bytes / 1024 / 1024, 2)
        except OSError:
            stats['db_size_mb'] = 0

        # 今日任务数
        stats['today_tasks'] = await conn.fetchval(
            "SELECT COUNT(*) FROM tasks WHERE date(created_at) = date('now')"
        )

        return stats
