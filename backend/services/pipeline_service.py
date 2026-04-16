"""OmniPublish V2.0 — 流水线状态机引擎

负责 6 步流水线的状态流转、自动推进、异常处理。
所有步骤的业务逻辑委托给对应的 Service。
"""

import asyncio
import json
from datetime import datetime
from typing import Optional

from database import get_pool
from websocket.manager import ws_manager


class PipelineService:
    """流水线状态机核心引擎。"""

    STEP_NAMES = ["素材&平台", "文案生成", "图片重命名", "封面制作", "水印处理", "上传&发布"]

    async def get_task(self, task_id: int) -> Optional[dict]:
        """获取任务完整数据。"""
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
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

    async def advance_step(self, task_id: int, from_step: int, to_step: int):
        """推进步骤：标记当前步骤 done，下一步 pending→对应初始状态。"""
        # Validate step range and adjacency
        if not (0 <= from_step < to_step <= 5):
            raise ValueError(f"Invalid step range: from_step={from_step}, to_step={to_step} (must be 0 <= from < to <= 5)")
        if to_step != from_step + 1:
            raise ValueError(f"Steps must be adjacent: from_step={from_step}, to_step={to_step} (to must equal from + 1)")

        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                now = datetime.now()

                # Check task exists
                task = await conn.fetchrow("SELECT id FROM tasks WHERE id = $1", task_id)
                if not task:
                    raise ValueError(f"Task not found: {task_id}")

                # 完成当前步骤
                await conn.execute(
                    "UPDATE task_steps SET status = 'done', finished_at = $1 WHERE task_id = $2 AND step = $3",
                    now, task_id, from_step,
                )

                # 更新下一步状态 — only set started_at if it's currently NULL
                next_status = self._initial_status_for_step(to_step)
                await conn.execute(
                    "UPDATE task_steps SET status = $1, started_at = CASE WHEN started_at IS NULL THEN $2 ELSE started_at END WHERE task_id = $3 AND step = $4",
                    next_status, now, task_id, to_step,
                )

                # 更新任务主表
                task_status = "awaiting_confirm" if next_status == "awaiting_confirm" else "running"
                await conn.execute(
                    "UPDATE tasks SET current_step = $1, status = $2, updated_at = $3 WHERE id = $4",
                    to_step, task_status, now, task_id,
                )

        # WebSocket 推送
        await ws_manager.send_to_task(task_id, {
            "type": "step_changed",
            "from_step": from_step,
            "to_step": to_step,
            "step_name": self.STEP_NAMES[to_step] if to_step < 6 else "完成",
            "status": next_status,
        })

    async def update_step_status(self, task_id: int, step: int, status: str,
                                  error: str = None, data: dict = None):
        """更新某步骤的状态。"""
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Check task exists
            task = await conn.fetchrow("SELECT id FROM tasks WHERE id = $1", task_id)
            if not task:
                raise ValueError(f"Task not found: {task_id}")

            now = datetime.now()
            # Build dynamic SET clause with numbered params
            set_parts = ["status = $1"]
            params = [status]
            param_idx = 1

            if status in ("done", "failed"):
                param_idx += 1
                set_parts.append(f"finished_at = ${param_idx}")
                params.append(now)
            else:
                # Only set started_at if it's currently NULL
                param_idx += 1
                set_parts.append(f"started_at = CASE WHEN started_at IS NULL THEN ${param_idx} ELSE started_at END")
                params.append(now)

            if error:
                param_idx += 1
                set_parts.append(f"error = ${param_idx}")
                params.append(error)
            if data:
                param_idx += 1
                set_parts.append(f"data = ${param_idx}")
                params.append(json.dumps(data, ensure_ascii=False))

            param_idx += 1
            task_id_param = param_idx
            param_idx += 1
            step_param = param_idx
            params.extend([task_id, step])

            await conn.execute(
                f"UPDATE task_steps SET {', '.join(set_parts)} WHERE task_id = ${task_id_param} AND step = ${step_param}",
                *params,
            )

        await ws_manager.send_to_task(task_id, {
            "type": "step_changed",
            "step": step,
            "status": status,
            "error": error,
        })

    async def update_task_status(self, task_id: int, status: str):
        """更新任务总体状态。"""
        pool = await get_pool()
        async with pool.acquire() as conn:
            now = datetime.now()
            finished = now if status in ("done", "failed", "partial") else None
            await conn.execute(
                "UPDATE tasks SET status = $1, updated_at = $2, finished_at = $3 WHERE id = $4",
                status, now, finished, task_id,
            )

    async def update_platform_task(self, task_id: int, platform_id: int, **kwargs):
        """更新平台子任务状态。"""
        if not kwargs:
            return
        # 安全校验：只允许已知列名，防止 SQL 注入
        ALLOWED_COLUMNS = {
            "publish_status", "publish_error", "publish_result",
            "upload_progress", "transcode_status",
            "wm_status", "wm_progress", "wm_error", "wm_images_dir",
        }
        for k in kwargs:
            if k not in ALLOWED_COLUMNS:
                raise ValueError(f"不允许更新列: {k}")
        pool = await get_pool()
        async with pool.acquire() as conn:
            set_parts = []
            params = []
            param_idx = 0
            for k, v in kwargs.items():
                param_idx += 1
                set_parts.append(f"{k} = ${param_idx}")
                params.append(v)

            param_idx += 1
            set_parts.append(f"updated_at = ${param_idx}")
            params.append(datetime.now())

            param_idx += 1
            task_id_param = param_idx
            param_idx += 1
            platform_id_param = param_idx
            params.extend([task_id, platform_id])

            await conn.execute(
                f"UPDATE platform_tasks SET {', '.join(set_parts)} WHERE task_id = ${task_id_param} AND platform_id = ${platform_id_param}",
                *params,
            )

        # 推送进度
        await ws_manager.send_to_task(task_id, {
            "type": "platform_update",
            "platform_id": platform_id,
            **kwargs,
        })

    async def add_log(self, task_id: int, message: str, step: int = None,
                       platform_id: int = None, level: str = "info"):
        """记录任务日志。"""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO task_logs (task_id, step, platform_id, level, message) VALUES ($1, $2, $3, $4, $5)",
                task_id, step, platform_id, level, message,
            )

    async def compute_task_status(self, task_id: int) -> str:
        """根据各步骤和平台子任务状态计算任务总体状态。"""
        pool = await get_pool()
        async with pool.acquire() as conn:
            # 检查步骤状态
            rows = await conn.fetch(
                "SELECT step, status FROM task_steps WHERE task_id = $1 ORDER BY step", task_id,
            )
            steps = {row["step"]: row["status"] for row in rows}

            for s in range(6):
                st = steps.get(s, "pending")
                if st == "awaiting_confirm":
                    return "awaiting_confirm"
                if st == "running":
                    return "running"
                if st == "failed":
                    return "failed"

            # 检查平台子任务
            rows = await conn.fetch(
                "SELECT publish_status, transcode_status FROM platform_tasks WHERE task_id = $1",
                task_id,
            )
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

    def _initial_status_for_step(self, step: int) -> str:
        """每步的初始状态。"""
        if step == 0:
            return "done"
        if step in (1, 2, 3, 4):
            return "awaiting_confirm"
        return "running"


# 全局单例
pipeline_service = PipelineService()
