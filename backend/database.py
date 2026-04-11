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

-- 索引
CREATE INDEX IF NOT EXISTS idx_tasks_created_by ON tasks(created_by);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_platform_tasks_task ON platform_tasks(task_id);
CREATE INDEX IF NOT EXISTS idx_task_logs_task ON task_logs(task_id);
CREATE INDEX IF NOT EXISTS idx_task_steps_task ON task_steps(task_id);
"""

# 默认管理员账号（首次初始化插入）
DEFAULT_ADMIN_SQL = """
INSERT OR IGNORE INTO users (username, password, display_name, dept, role)
VALUES ('admin', '$2b$12$8DgwGZ8lNtWmiC/967ocIuldJep3UNUNbkeJXrYh1wuHggDoHRVqq', '管理员', '系统', 'admin');
"""
# 默认密码: admin123 (bcrypt hash, 使用 passlib bcrypt 生成)


async def get_db() -> aiosqlite.Connection:
    """获取数据库连接。"""
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db():
    """初始化数据库（建表 + 默认数据）。"""
    print(f"[DB] Initializing database: {DB_PATH}")
    db = await get_db()
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
        print(f"[DB] Users: {user_count}, Platforms: {platform_count}")
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
