"""OmniPublish V2.0 — PostgreSQL 数据库管理（asyncpg 连接池）"""

import asyncpg
import json
import os
from typing import Optional

from config import settings

# 数据库连接 URL
DATABASE_URL = os.environ.get("DATABASE_URL", settings.database_url)

# 全局连接池
_pool: Optional[asyncpg.Pool] = None


# ══════════════════════════════════════
# 建表 SQL（PostgreSQL 语法）
# ══════════════════════════════════════

SCHEMA_SQL = [
    # 用户表
    """
    CREATE TABLE IF NOT EXISTS users (
        id           SERIAL PRIMARY KEY,
        username     TEXT NOT NULL UNIQUE,
        password     TEXT NOT NULL,
        display_name TEXT NOT NULL DEFAULT '',
        dept         TEXT DEFAULT '',
        role         TEXT DEFAULT 'editor',
        is_active    INTEGER DEFAULT 1,
        created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,

    # 业务线/平台配置表
    """
    CREATE TABLE IF NOT EXISTS platforms (
        id              SERIAL PRIMARY KEY,
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
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,

    # 发帖任务主表
    """
    CREATE TABLE IF NOT EXISTS tasks (
        id                 SERIAL PRIMARY KEY,
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
        created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        finished_at        TIMESTAMP DEFAULT NULL
    )
    """,

    # 步骤状态表
    """
    CREATE TABLE IF NOT EXISTS task_steps (
        id          SERIAL PRIMARY KEY,
        task_id     INTEGER NOT NULL REFERENCES tasks(id),
        step        INTEGER NOT NULL,
        status      TEXT DEFAULT 'pending',
        started_at  TIMESTAMP DEFAULT NULL,
        finished_at TIMESTAMP DEFAULT NULL,
        data        TEXT DEFAULT '{}',
        error       TEXT DEFAULT NULL,
        UNIQUE(task_id, step)
    )
    """,

    # 平台子任务表
    """
    CREATE TABLE IF NOT EXISTS platform_tasks (
        id                 SERIAL PRIMARY KEY,
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
        created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(task_id, platform_id)
    )
    """,

    # 操作日志表
    """
    CREATE TABLE IF NOT EXISTS task_logs (
        id          SERIAL PRIMARY KEY,
        task_id     INTEGER NOT NULL REFERENCES tasks(id),
        step        INTEGER DEFAULT NULL,
        platform_id INTEGER DEFAULT NULL,
        level       TEXT DEFAULT 'info',
        message     TEXT NOT NULL,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,

    # ── 索引（基础） ──
    "CREATE INDEX IF NOT EXISTS idx_tasks_created_by ON tasks(created_by)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_platform_tasks_task ON platform_tasks(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_task_logs_task ON task_logs(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_task_steps_task ON task_steps(task_id)",

    # ── 索引（性能优化） ──
    "CREATE INDEX IF NOT EXISTS idx_tasks_status_created ON tasks(status, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON tasks(created_by, status)",
    "CREATE INDEX IF NOT EXISTS idx_pt_platform ON platform_tasks(platform_id)",
    "CREATE INDEX IF NOT EXISTS idx_pt_platform_publish ON platform_tasks(platform_id, publish_status)",
    "CREATE INDEX IF NOT EXISTS idx_logs_created ON task_logs(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_logs_task_step ON task_logs(task_id, step)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_no ON tasks(task_no)",
]

DEFAULT_ADMIN_SQL = """
    INSERT INTO users (username, password, display_name, dept, role)
    VALUES ($1, $2, $3, $4, $5)
    ON CONFLICT (username) DO NOTHING
"""


# ══════════════════════════════════════
# 连接池管理
# ══════════════════════════════════════

async def get_pool() -> asyncpg.Pool:
    """获取全局连接池。"""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=20,
            command_timeout=60,
        )
    return _pool


async def get_db() -> asyncpg.Connection:
    """从连接池获取连接（向后兼容旧接口）。"""
    pool = await get_pool()
    return await pool.acquire()


async def release_db(conn: asyncpg.Connection):
    """归还连接到连接池。"""
    pool = await get_pool()
    await pool.release(conn)


async def init_db():
    """初始化数据库（建表 + 默认数据）。"""
    print(f"[DB] Initializing PostgreSQL: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL}")
    pool = await get_pool()

    async with pool.acquire() as conn:
        # 逐条执行建表语句
        for sql in SCHEMA_SQL:
            sql = sql.strip()
            if sql:
                await conn.execute(sql)

        # 插入默认管理员
        # 密码: admin123 (bcrypt hash)
        await conn.execute(
            DEFAULT_ADMIN_SQL,
            'admin',
            '$2b$12$8DgwGZ8lNtWmiC/967ocIuldJep3UNUNbkeJXrYh1wuHggDoHRVqq',
            '管理员',
            '系统',
            'admin',
        )

        # 统计
        user_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        platform_count = await conn.fetchval("SELECT COUNT(*) FROM platforms")
        task_count = await conn.fetchval("SELECT COUNT(*) FROM tasks")
        print(f"[DB] Users: {user_count}, Platforms: {platform_count}, Tasks: {task_count}")

        # 启动时清理过期日志
        deleted = await cleanup_old_logs(conn)
        if deleted and int(deleted.split()[-1]) > 0:
            print(f"[DB] Cleaned up old log entries")

    print("[DB] PostgreSQL initialized successfully")


async def close_db():
    """关闭连接池。"""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def get_next_task_no() -> str:
    """生成下一个任务编号 #0001 格式。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        max_id = await conn.fetchval("SELECT COALESCE(MAX(id), 0) FROM tasks")
        return f"#{max_id + 1:04d}"


# ══════════════════════════════════════
# 日志清理
# ══════════════════════════════════════

async def cleanup_old_logs(conn: asyncpg.Connection, days: int = 30) -> str:
    """清理超过 N 天的操作日志。"""
    import datetime
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    return await conn.execute(
        "DELETE FROM task_logs WHERE created_at < $1",
        cutoff,
    )


async def get_db_stats() -> dict:
    """获取数据库统计信息。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        stats = {}
        for table in ['users', 'platforms', 'tasks', 'task_steps', 'platform_tasks', 'task_logs']:
            stats[table] = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")

        # 数据库大小
        db_size = await conn.fetchval(
            "SELECT pg_database_size(current_database())"
        )
        stats['db_size_mb'] = round(db_size / 1024 / 1024, 2) if db_size else 0

        # 今日任务数
        stats['today_tasks'] = await conn.fetchval(
            "SELECT COUNT(*) FROM tasks WHERE created_at::date = CURRENT_DATE"
        )

        return stats
