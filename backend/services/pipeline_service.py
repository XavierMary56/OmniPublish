"""OmniPublish V2.0 — 流水线状态机引擎

负责 6 步流水线的状态流转、自动推进、异常处理。
所有步骤的业务逻辑委托给对应的 Service。
"""

import asyncio
import json
from datetime import datetime
from typing import Optional

import aiosqlite
from database import get_db
from websocket.manager import ws_manager


class PipelineService:
    """流水线状态机核心引擎。"""

    STEP_NAMES = ["素材&平台", "文案生成", "图片重命名", "封面制作", "水印处理", "上传&发布"]

    async def get_task(self, task_id: int) -> Optional[dict]:
        """获取任务完整数据。"""
        db = await get_db()
        try:
            cursor = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = await cursor.fetchone()
            if not row:
                return None
            task = dict(row)
            for field in ["target_platforms", "file_manifest", "categories",
                          "rename_mapping", "cover_candidates"]:
                val = task.get(field)
                if val and isinstance(val, str):
                    try:
                        task[field] = json.loads(val)
                    except (json.JSONDecodeError, TypeError):
                        pass
            return task
        finally:
            await db.close()

    async def advance_step(self, task_id: int, from_step: int, to_step: int):
        """推进步骤：标记当前步骤 done，下一步 pending→对应初始状态。"""
        db = await get_db()
        try:
            now = datetime.now().isoformat()

            # 完成当前步骤
            await db.execute(
                "UPDATE task_steps SET status = 'done', finished_at = ? WHERE task_id = ? AND step = ?",
                (now, task_id, from_step),
            )

            # 更新下一步状态
            next_status = self._initial_status_for_step(to_step)
            await db.execute(
                "UPDATE task_steps SET status = ?, started_at = ? WHERE task_id = ? AND step = ?",
                (next_status, now, task_id, to_step),
            )

            # 更新任务主表
            task_status = "awaiting_confirm" if next_status == "awaiting_confirm" else "running"
            await db.execute(
                "UPDATE tasks SET current_step = ?, status = ?, updated_at = ? WHERE id = ?",
                (to_step, task_status, now, task_id),
            )

            await db.commit()

            # WebSocket 推送
            await ws_manager.send_to_task(task_id, {
                "type": "step_changed",
                "from_step": from_step,
                "to_step": to_step,
                "step_name": self.STEP_NAMES[to_step] if to_step < 6 else "完成",
                "status": next_status,
            })

        finally:
            await db.close()

    async def update_step_status(self, task_id: int, step: int, status: str,
                                  error: str = None, data: dict = None):
        """更新某步骤的状态。"""
        db = await get_db()
        try:
            now = datetime.now().isoformat()
            updates = ["status = ?", "finished_at = ?" if status in ("done", "failed") else "started_at = ?"]
            params = [status, now]

            if error:
                updates.append("error = ?")
                params.append(error)
            if data:
                updates.append("data = ?")
                params.append(json.dumps(data, ensure_ascii=False))

            params.extend([task_id, step])
            await db.execute(
                f"UPDATE task_steps SET {', '.join(updates)} WHERE task_id = ? AND step = ?",
                params,
            )
            await db.commit()

            await ws_manager.send_to_task(task_id, {
                "type": "step_changed",
                "step": step,
                "status": status,
                "error": error,
            })
        finally:
            await db.close()

    async def update_task_status(self, task_id: int, status: str):
        """更新任务总体状态。"""
        db = await get_db()
        try:
            now = datetime.now().isoformat()
            finished = now if status in ("done", "failed", "partial") else None
            await db.execute(
                "UPDATE tasks SET status = ?, updated_at = ?, finished_at = ? WHERE id = ?",
                (status, now, finished, task_id),
            )
            await db.commit()
        finally:
            await db.close()

    async def update_platform_task(self, task_id: int, platform_id: int, **kwargs):
        """更新平台子任务状态。"""
        if not kwargs:
            return
        db = await get_db()
        try:
            updates = [f"{k} = ?" for k in kwargs]
            updates.append("updated_at = ?")
            params = list(kwargs.values()) + [datetime.now().isoformat(), task_id, platform_id]
            await db.execute(
                f"UPDATE platform_tasks SET {', '.join(updates)} WHERE task_id = ? AND platform_id = ?",
                params,
            )
            await db.commit()

            # 推送进度
            await ws_manager.send_to_task(task_id, {
                "type": "platform_update",
                "platform_id": platform_id,
                **kwargs,
            })
        finally:
            await db.close()

    async def add_log(self, task_id: int, message: str, step: int = None,
                       platform_id: int = None, level: str = "info"):
        """记录任务日志。"""
        db = await get_db()
        try:
            await db.execute(
                "INSERT INTO task_logs (task_id, step, platform_id, level, message) VALUES (?, ?, ?, ?, ?)",
                (task_id, step, platform_id, level, message),
            )
            await db.commit()
        finally:
            await db.close()

    async def compute_task_status(self, task_id: int) -> str:
        """根据各步骤和平台子任务状态计算任务总体状态。"""
        db = await get_db()
        try:
            # 检查步骤状态
            cursor = await db.execute(
                "SELECT step, status FROM task_steps WHERE task_id = ? ORDER BY step", (task_id,)
            )
            steps = {row["step"]: row["status"] for row in await cursor.fetchall()}

            for s in range(6):
                st = steps.get(s, "pending")
                if st == "awaiting_confirm":
                    return "awaiting_confirm"
                if st == "running":
                    return "running"
                if st == "failed":
                    return "failed"

            # 检查平台子任务
            cursor = await db.execute(
                "SELECT publish_status, transcode_status FROM platform_tasks WHERE task_id = ?",
                (task_id,),
            )
            rows = await cursor.fetchall()
            if not rows:
                return steps.get(5, "running")

            published = sum(1 for r in rows if r["publish_status"] == "published")
            failed = sum(1 for r in rows if r["publish_status"] == "failed")
            transcoding = sum(1 for r in rows if r["transcode_status"] == "transcoding")

            if published == len(rows):
                return "done"
            if published > 0 and failed > 0:
                return "partial"
            if failed == len(rows):
                return "failed"
            if transcoding > 0:
                return "slicing"
            return "running"
        finally:
            await db.close()

    def _initial_status_for_step(self, step: int) -> str:
        """每步的初始状态。"""
        # Step 0: 用户操作
        # Step 1: AI 生成后等待确认
        # Step 2: 展示预览等待确认
        # Step 3: 生成候选等待确认
        # Step 4: 展示方案等待确认
        # Step 5: 并行上传
        if step in (1, 2, 3, 4):
            return "awaiting_confirm"
        return "running"


# 全局单例
pipeline_service = PipelineService()
