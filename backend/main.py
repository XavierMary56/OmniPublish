#!/usr/bin/env python3
"""OmniPublish V2.0 — FastAPI 主入口"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import settings, ROOT_DIR, BACKEND_DIR
from database import init_db
from websocket.manager import ws_manager

# ── 路由导入 ──
from routers import auth, pipeline, tasks, platforms, stats, tools


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
    print("[OmniPublish] Shutting down...")


async def _daily_cleanup():
    """每天凌晨 3 点清理过期日志。"""
    from database import cleanup_old_logs, get_db
    while True:
        try:
            await asyncio.sleep(24 * 3600)  # 每 24 小时执行一次
            db = await get_db()
            try:
                deleted = await cleanup_old_logs(db, days=30)
                if deleted > 0:
                    print(f"[Cleanup] Deleted {deleted} old log entries")
            finally:
                await db.close()
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[Cleanup] Error: {e}")


# ── FastAPI 实例 ──
app = FastAPI(
    title="OmniPublish V2.0",
    description="全链路发帖工作台 API",
    version="2.0.0",
    lifespan=lifespan,
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


# ── WebSocket 端点 ──
@app.websocket("/ws/pipeline/{task_id}")
async def ws_pipeline(websocket: WebSocket, task_id: int):
    """流水线任务实时进度推送。"""
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
async def ws_notifications(websocket: WebSocket):
    """全局通知推送。"""
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
        "db_path": settings.db_path,
        "ws_connections": {
            "tasks": ws_manager.task_count,
            "notifications": ws_manager.notification_count,
        },
    }


# ── 静态文件（前端 dist）──
frontend_dist = ROOT_DIR / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")


# ── 启动 ──
def main():
    parser = argparse.ArgumentParser(description="OmniPublish V2.0 Server")
    parser.add_argument("--port", type=int, default=settings.server.port)
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
║  DB:   {Path(settings.db_path).name:34s} ║
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
