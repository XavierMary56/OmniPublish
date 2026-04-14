#!/usr/bin/env python3
"""OmniPublish V2.0 — FastAPI 主入口"""

import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from contextlib import asynccontextmanager

import json as _json

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles


class UnicodeJSONResponse(JSONResponse):
    """JSON 响应，中文不转义为 \\uXXXX"""
    def render(self, content) -> bytes:
        return _json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")

from config import settings, ROOT_DIR, BACKEND_DIR, UPLOADS_DIR
from database import init_db, close_db
from websocket.manager import ws_manager
from middleware.auth import decode_token

# ── 路由导入 ──
from routers import auth, pipeline, tasks, platforms, stats, tools, accounts


# ── 生命周期 ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化数据库，启动定时清理任务。"""
    await init_db()
    print(f"[OmniPublish] Server ready on port {settings.server.port}")
    print(f"[OmniPublish] API docs: http://127.0.0.1:{settings.server.port}/docs")

    # 启动每日日志清理定时任务
    cleanup_task = asyncio.create_task(_daily_cleanup())
    yield
    cleanup_task.cancel()
    await close_db()
    print("[OmniPublish] Shutting down...")


async def _daily_cleanup():
    """启动时立即执行一次清理，之后每 24 小时执行一次。"""
    from database import cleanup_old_logs, get_pool
    first_run = True
    while True:
        try:
            if first_run:
                await asyncio.sleep(60)  # 启动后等 1 分钟再首次清理（等数据库就绪）
                first_run = False
            else:
                await asyncio.sleep(24 * 3600)  # 之后每 24 小时
            pool = await get_pool()
            async with pool.acquire() as conn:
                deleted = await cleanup_old_logs(conn, days=30)
                if isinstance(deleted, str):
                    deleted = int(deleted) if deleted.isdigit() else 0
                if deleted > 0:
                    print(f"[Cleanup] Deleted {deleted} old log entries")

            # 清理超过 7 天的上传临时文件
            await _cleanup_stale_uploads(days=7)

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[Cleanup] Error: {e}")


async def _cleanup_stale_uploads(days: int = 7):
    """清理 uploads/ 和 tmp/ 下超过 N 天的孤立文件。"""
    import shutil
    cutoff = time.time() - days * 86400
    cleaned = 0

    for dir_path in [UPLOADS_DIR, ROOT_DIR / "tmp"]:
        if not dir_path.exists():
            continue
        for item in dir_path.iterdir():
            try:
                mtime = item.stat().st_mtime
                if mtime < cutoff:
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                    else:
                        item.unlink(missing_ok=True)
                    cleaned += 1
            except OSError:
                continue

    if cleaned > 0:
        print(f"[Cleanup] Removed {cleaned} stale upload/tmp items (>{days} days)")


# ── FastAPI 实例 ──
app = FastAPI(
    title="OmniPublish V2.0",
    description="全链路发帖工作台 API",
    version="2.0.0",
    lifespan=lifespan,
    default_response_class=UnicodeJSONResponse,
)

# ── CORS ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.server.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 注册路由 ──
app.include_router(auth.router)
app.include_router(pipeline.router)
app.include_router(tasks.router)
app.include_router(platforms.router)
app.include_router(stats.router)
app.include_router(tools.router)
app.include_router(accounts.router)

# ── 静态文件：上传目录（封面预览等） ──
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


# ── WebSocket 认证辅助 ──
async def _ws_authenticate(websocket: WebSocket, token: str = None) -> bool:
    """验证 WebSocket 连接的 JWT token。
    无效/过期 token 拒绝连接并关闭 WebSocket。
    注意：不在这里 accept()，由 ws_manager.connect_* 负责 accept。"""
    logger = logging.getLogger("omnipublish")
    if not token:
        logger.warning("WebSocket 连接被拒绝：缺少认证 token")
        await websocket.accept()
        await websocket.close(code=4001, reason="Missing authentication token")
        return False
    try:
        decode_token(token)
        return True
    except Exception:
        logger.warning("WebSocket 连接被拒绝：token 无效或已过期")
        await websocket.accept()
        await websocket.close(code=4003, reason="Invalid or expired token")
        return False


# ── WebSocket 端点 ──
@app.websocket("/ws/pipeline/{task_id}")
async def ws_pipeline(websocket: WebSocket, task_id: int, token: str = Query(default=None)):
    """流水线任务实时进度推送（需要 JWT 认证）。"""
    if not await _ws_authenticate(websocket, token):
        return
    await ws_manager.connect_task(task_id, websocket)
    try:
        while True:
            # 保持连接，等待客户端关闭
            data = await websocket.receive_text()
            # 客户端可以发送 ping
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        await ws_manager.disconnect_task(task_id, websocket)


@app.websocket("/ws/notifications")
async def ws_notifications(websocket: WebSocket, token: str = Query(default=None)):
    """全局通知推送（需要 JWT 认证）。"""
    if not await _ws_authenticate(websocket, token):
        return
    await ws_manager.connect_notifications(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        await ws_manager.disconnect_notifications(websocket)


# ── 健康检查 ──
@app.get("/api/ping")
async def ping():
    return {"ok": True, "version": "2.0.0"}


@app.get("/api/info")
async def info():
    return {
        "version": "2.0.0",
        "database": "postgresql",
        "ws_connections": {
            "tasks": ws_manager.task_count,
            "notifications": ws_manager.notification_count,
        },
    }


# ── 静态文件（前端 dist）──
from starlette.responses import FileResponse

frontend_dist = ROOT_DIR / "frontend" / "dist"
if frontend_dist.exists():
    # index.html 不缓存，确保每次获取最新版本引用
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = frontend_dist / full_path
        if full_path and file_path.exists() and file_path.is_file():
            # 静态资源（JS/CSS/图片）带 hash，可长缓存
            return FileResponse(
                str(file_path),
                headers={"Cache-Control": "public, max-age=31536000, immutable"}
            )
        # 所有其他路径返回 index.html（SPA 路由），不缓存
        return FileResponse(
            str(frontend_dist / "index.html"),
            headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"}
        )


# ── 启动 ──
def main():
    parser = argparse.ArgumentParser(description="OmniPublish V2.0 Server")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", settings.server.port)))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--reload", action="store_true", help="开发模式热重载")
    args = parser.parse_args()

    print(f"""
╔══════════════════════════════════════════╗
║        OmniPublish V2.0                 ║
║        全链路发帖工作台                    ║
╠══════════════════════════════════════════╣
║  URL:  http://{args.host}:{args.port}          ║
║  Docs: http://{args.host}:{args.port}/docs     ║
║  DB:   PostgreSQL                        ║
╚══════════════════════════════════════════╝
    """)

    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
