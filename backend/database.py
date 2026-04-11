"""OmniPublish V2.0 — SQLite 数据库管理"""

import aiosqlite
import json
import os
from pathlib import Path
from config import settings


DB_PATH = settings.db_path

# 建表 SQL（首次启动自动执行）
SCHEMA_SQL = """
-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT NOT NULL UNIQUE,
    password    TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    dept        TEXT DEFAULT '',
    role        TEXT DEFAULT 'editor',
    is_active   INTEGER DEFAULT 1,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

-- 业务线/平台配置表
CREATE TABLE IF NOT EXISTS platforms (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    dept        TEXT DEFAULT '',
    categories  TEXT DEFAULT '[]',
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
    is_active   INTEGER DEFAULT 1,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

-- 发帖任务主表
CREATE TABLE IF NOT EXISTS tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_no         TEXT NOT NULL UNIQUE,
    title           TEXT DEFAULT '',
    folder_path     TEXT NOT NULL,
    created_by      INTEGER NOT NULL REFERENCES users(id),
    current_step    INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'draft',
    target_platforms TEXT DEFAULT '[]',
    file_manifest   TEXT DEFAULT '{}',
    protagonist     TEXT DEFAULT '',
    event_desc      TEXT DEFAULT '',
    style           TEXT DEFAULT '反转打脸风',
    author          TEXT DEFAULT '',
    categories      TEXT DEFAULT '[]',
    confirmed_title TEXT DEFAULT '',
    confirmed_keywords TEXT DEFAULT '',
    confirmed_body  TEXT DEFAULT '',
    rename_prefix   TEXT DEFAULT '',
    rename_mapping  TEXT DEFAULT '[]',
    cover_layout    TEXT DEFAULT 'triple',
    cover_path      TEXT DEFAULT '',
    cover_candidates TEXT DEFAULT '[]',
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    finished_at     TEXT DEFAULT NULL
);

-- 步骤状态表
CREATE TABLE IF NOT EXISTS task_steps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER NOT NULL REFERENCES tasks(id),
    step        INTEGER NOT NULL,
    status      TEXT DEFAULT 'pending',
    started_at  TEXT DEFAULT NULL,
    finished_at TEXT DEFAULT NULL,
    data        TEXT DEFAULT '{}',
    error       TEXT DEFAULT NULL,
    UNIQUE(task_id, step)
);

-- 平台子任务表
CREATE TABLE IF NOT EXISTS platform_tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         INTEGER NOT NULL REFERENCES tasks(id),
    platform_id     INTEGER NOT NULL REFERENCES platforms(id),
    wm_status       TEXT DEFAULT 'pending',
    wm_progress     REAL DEFAULT 0,
    wm_images_dir   TEXT DEFAULT '',
    wm_video_path   TEXT DEFAULT '',
    wm_cover_path   TEXT DEFAULT '',
    wm_error        TEXT DEFAULT NULL,
    upload_status   TEXT DEFAULT 'pending',
    upload_progress REAL DEFAULT 0,
    mp4_url         TEXT DEFAULT '',
    transcode_status TEXT DEFAULT 'pending',
    transcode_progress REAL DEFAULT 0,
    video_url       TEXT DEFAULT '',
    publish_status  TEXT DEFAULT 'pending',
    publish_result  TEXT DEFAULT '{}',
    publish_error   TEXT DEFAULT NULL,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(task_id, platform_id)
);

-- 操作日志表
CREATE TABLE IF NOT EXISTS task_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER NOT NULL REFERENCES tasks(id),
    step        INTEGER DEFAULT NULL,
    platform_id INTEGER DEFAULT NULL,
    level       TEXT DEFAULT 'info',
    message     TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now'))
);

-- ══════════════════════════════════════
-- 索引（基础）
-- ══════════════════════════════════════
CREATE INDEX IF NOT EXISTS idx_tasks_created_by ON tasks(created_by);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_platform_tasks_task ON platform_tasks(task_id);
CREATE INDEX IF NOT EXISTS idx_task_logs_task ON task_logs(task_id);
CREATE INDEX IF NOT EXISTS idx_task_steps_task ON task_steps(task_id);

-- ══════════════════════════════════════
-- 索引（性能优化 — 31平台×15条/天场景）
-- ══════════════════════════════════════

-- 任务看板：按状态+时间排序（最常用查询）
CREATE INDEX IF NOT EXISTS idx_tasks_status_created ON tasks(status, created_at DESC);

-- 任务看板：按编辑筛选自己的任务
CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON tasks(created_by, status);

-- 任务看板：按日期范围查（今日/本周/本月统计）
CREATE INDEX IF NOT EXISTS idx_tasks_date_status ON tasks(date(created_at), status);

-- 平台子任务：按平台查发布历史
CREATE INDEX IF NOT EXISTS idx_pt_platform ON platform_tasks(platform_id);

-- 平台子任务：查某平台的发布状态
CREATE INDEX IF NOT EXISTS idx_pt_platform_publish ON platform_tasks(platform_id, publish_status);

-- 平台子任务：查水印处理中的任务
CREATE INDEX IF NOT EXISTS idx_pt_wm_status ON platform_tasks(wm_status) WHERE wm_status != 'done';

-- 日志表：按时间清理
CREATE INDEX IF NOT EXISTS idx_logs_created ON task_logs(created_at);

-- 日志表：按任务+步骤查
CREATE INDEX IF NOT EXISTS idx_logs_task_step ON task_logs(task_id, step);

-- 任务编号查找
CREATE INDEX IF NOT EXISTS idx_tasks_no ON tasks(task_no);
"""

# 默认管理员账号（首次初始化插入）
DEFAULT_ADMIN_SQL = """
INSERT OR IGNORE INTO users (username, password, display_name, dept, role)
VALUES ('admin', '$2b$12$8DgwGZ8lNtWmiC/967ocIuldJep3UNUNbkeJXrYh1wuHggDoHRVqq', '管理员', '系统', 'admin');
"""
# 默认密码: admin123 (bcrypt hash, 使用 passlib bcrypt 生成)


import asyncio
from contextlib import asynccontextmanager

# ══════════════════════════════════════
# 连接池（SQLite 并发写入优化）
# ══════════════════════════════════════

_db_lock = asyncio.Lock()  # 写操作全局锁，防止 SQLITE_BUSY


async def _create_connection() -> aiosqlite.Connection:
    """创建并配置一个数据库连接。"""
    db = await aiosqlite.connect(DB_PATH, timeout=30)
    db.row_factory = aiosqlite.Row
    # WAL 模式：允许并发读，写不阻塞读
    await db.execute("PRAGMA journal_mode=WAL")
    # WAL 检查点阈值（1000页 ≈ 4MB 后自动合并）
    await db.execute("PRAGMA wal_autocheckpoint=1000")
    # 外键约束
    await db.execute("PRAGMA foreign_keys=ON")
    # 缓存 8MB（默认 2MB，提升查询速度）
    await db.execute("PRAGMA cache_size=-8000")
    # 同步模式 NORMAL（比 FULL 快，WAL 模式下安全）
    await db.execute("PRAGMA synchronous=NORMAL")
    # 临时表存内存
    await db.execute("PRAGMA temp_store=MEMORY")
    # 忙等待超时 5 秒（避免立即报 SQLITE_BUSY）
    await db.execute("PRAGMA busy_timeout=5000")
    return db


async def get_db() -> aiosqlite.Connection:
    """获取数据库连接（读操作用）。"""
    return await _create_connection()


@asynccontextmanager
async def get_db_write():
    """获取写操作数据库连接（带锁，防止并发写冲突）。
    用法：
        async with get_db_write() as db:
            await db.execute(...)
            await db.commit()
    """
    async with _db_lock:
        db = await _create_connection()
        try:
            yield db
        finally:
            await db.close()


async def init_db():
    """初始化数据库（建表 + 默认数据）。"""
    print(f"[DB] Initializing database: {DB_PATH}")
    db = await _create_connection()
    try:
        await db.executescript(SCHEMA_SQL)
        await db.execute(DEFAULT_ADMIN_SQL)
        await db.commit()
        print("[DB] Database initialized successfully")

        # 统计
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        user_count = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COUNT(*) FROM platforms")
        platform_count = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COUNT(*) FROM tasks")
        task_count = (await cursor.fetchone())[0]
        print(f"[DB] Users: {user_count}, Platforms: {platform_count}, Tasks: {task_count}")

        # 启动时自动清理过期日志
        deleted = await cleanup_old_logs(db)
        if deleted > 0:
            print(f"[DB] Cleaned up {deleted} old log entries")
    finally:
        await db.close()


async def get_next_task_no() -> str:
    """生成下一个任务编号 #0001 格式。"""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT MAX(id) FROM tasks")
        row = await cursor.fetchone()
        next_id = (row[0] or 0) + 1
        return f"#{next_id:04d}"
    finally:
        await db.close()


# ══════════════════════════════════════
# 日志自动清理（保留 30 天）
# ══════════════════════════════════════

async def cleanup_old_logs(db: aiosqlite.Connection, days: int = 30) -> int:
    """清理超过 N 天的操作日志。"""
    cursor = await db.execute(
        "DELETE FROM task_logs WHERE created_at < datetime('now', ?)",
        (f"-{days} days",),
    )
    await db.commit()
    return cursor.rowcount


async def get_db_stats() -> dict:
    """获取数据库统计信息（管理后台用）。"""
    db = await get_db()
    try:
        stats = {}
        for table in ['users', 'platforms', 'tasks', 'task_steps', 'platform_tasks', 'task_logs']:
            cursor = await db.execute(f"SELECT COUNT(*) FROM {table}")
            stats[table] = (await cursor.fetchone())[0]

        # 数据库文件大小
        db_size = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
        stats['db_size_mb'] = round(db_size / 1024 / 1024, 2)

        # WAL 文件大小
        wal_path = DB_PATH + '-wal'
        wal_size = os.path.getsize(wal_path) if os.path.exists(wal_path) else 0
        stats['wal_size_mb'] = round(wal_size / 1024 / 1024, 2)

        # 今日任务数
        cursor = await db.execute(
            "SELECT COUNT(*) FROM tasks WHERE date(created_at) = date('now')"
        )
        stats['today_tasks'] = (await cursor.fetchone())[0]

        return stats
    finally:
        await db.close()
