"""OmniPublish V2.0 — WebSocket 连接管理器"""

import json
import asyncio
import logging
from typing import Dict, Set
from fastapi import WebSocket

logger = logging.getLogger(__name__)

# Connection limits
MAX_TOTAL_CONNECTIONS = 100
MAX_CONNECTIONS_PER_TASK = 10


class ConnectionManager:
    """管理 WebSocket 连接，支持按 task_id 和全局广播。"""

    def __init__(self):
        # task_id -> set of WebSocket connections
        self._task_connections: Dict[str, Set[WebSocket]] = {}
        # 全局通知连接
        self._notification_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    @property
    def total_connections(self) -> int:
        """Total number of active connections (task + notification)."""
        count = sum(len(s) for s in self._task_connections.values())
        count += len(self._notification_connections)
        return count

    async def connect_task(self, task_id: int, ws: WebSocket):
        """连接到特定任务的进度频道。"""
        key = str(task_id)
        async with self._lock:
            # Check total connection limit
            if self.total_connections >= MAX_TOTAL_CONNECTIONS:
                await ws.close(code=1013, reason="Server at max connections")
                logger.warning(f"WebSocket rejected: total connections at limit ({MAX_TOTAL_CONNECTIONS})")
                return
            # Check per-task connection limit
            task_conns = self._task_connections.get(key, set())
            if len(task_conns) >= MAX_CONNECTIONS_PER_TASK:
                await ws.close(code=1013, reason=f"Task {task_id} at max connections")
                logger.warning(f"WebSocket rejected: task {task_id} at limit ({MAX_CONNECTIONS_PER_TASK})")
                return
            await ws.accept()
            if key not in self._task_connections:
                self._task_connections[key] = set()
            self._task_connections[key].add(ws)
            logger.info(f"WebSocket connected: task={task_id}, task_conns={len(self._task_connections[key])}, total={self.total_connections}")

    async def connect_notifications(self, ws: WebSocket):
        """连接到全局通知频道。"""
        async with self._lock:
            if self.total_connections >= MAX_TOTAL_CONNECTIONS:
                await ws.close(code=1013, reason="Server at max connections")
                logger.warning(f"WebSocket notification rejected: total at limit ({MAX_TOTAL_CONNECTIONS})")
                return
            await ws.accept()
            self._notification_connections.add(ws)
            logger.info(f"WebSocket notification connected, total={self.total_connections}")

    async def disconnect_task(self, task_id: int, ws: WebSocket):
        """断开任务频道连接。"""
        key = str(task_id)
        async with self._lock:
            if key in self._task_connections:
                self._task_connections[key].discard(ws)
                if not self._task_connections[key]:
                    del self._task_connections[key]

    async def disconnect_notifications(self, ws: WebSocket):
        """断开通知频道连接。"""
        async with self._lock:
            self._notification_connections.discard(ws)

    async def send_to_task(self, task_id: int, data: dict):
        """向特定任务的所有连接发送消息。"""
        key = str(task_id)
        dead = []
        connections = self._task_connections.get(key, set()).copy()
        for ws in connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        # 清理断开的连接
        for ws in dead:
            await self.disconnect_task(task_id, ws)

    async def send_notification(self, data: dict):
        """向所有通知频道连接广播。"""
        dead = []
        connections = self._notification_connections.copy()
        for ws in connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect_notifications(ws)

    @property
    def task_count(self) -> int:
        return len(self._task_connections)

    @property
    def notification_count(self) -> int:
        return len(self._notification_connections)


# 全局单例
ws_manager = ConnectionManager()
