"""OmniPublish V2.0 — 图片重命名服务"""

import asyncio
import json
import os
import sys
from pathlib import Path

from services.pipeline_service import pipeline_service
from config import BACKEND_DIR

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from image_rename import rename_files, IMG_EXTS

# Allowed base directories for path traversal protection
UPLOAD_ROOT = os.path.realpath(os.path.join(str(BACKEND_DIR), "uploads", "tasks"))


class RenameService:
    """图片重命名服务。"""

    def _validate_path(self, folder_path: str) -> str:
        """Validate folder_path is within allowed directories. Returns resolved path."""
        resolved = os.path.realpath(folder_path)
        if not resolved.startswith(UPLOAD_ROOT + os.sep) and resolved != UPLOAD_ROOT:
            raise ValueError(f"路径不在允许的范围内: {folder_path}")
        if not os.path.isdir(resolved):
            raise ValueError(f"目录不存在: {folder_path}")
        return resolved

    async def preview(self, folder_path: str, prefix: str, start: int = 1,
                      digits: int = 2, separator: str = "_") -> list:
        """预览重命名结果（dry-run）。"""
        resolved = self._validate_path(folder_path)
        files = sorted([
            f for f in os.listdir(resolved)
            if os.path.splitext(f)[1].lower() in IMG_EXTS
            and not f.startswith(".")
            and "_cover" not in f.lower()
        ])

        preview = []
        for i, fname in enumerate(files):
            ext = os.path.splitext(fname)[1]
            num = str(start + i).zfill(digits)
            new_name = f"{prefix}{separator}{num}{ext}"
            preview.append({"old": fname, "new": new_name})

        return preview

    async def execute(self, task_id: int, folder_path: str, prefix: str,
                      start: int = 1, digits: int = 2, separator: str = "_") -> list:
        """执行重命名并更新任务状态。"""
        resolved = self._validate_path(folder_path)
        await pipeline_service.update_step_status(task_id, step=2, status="running")
        await pipeline_service.add_log(task_id, f"开始重命名: 前缀={prefix}", step=2)

        try:
            # 先获取预览（用于记录映射）— use resolved path consistently
            preview = await self.preview(resolved, prefix, start, digits, separator)

            # 在线程池执行重命名 — use resolved path
            success = await asyncio.to_thread(
                rename_files, resolved, prefix, start, digits, separator, False, False
            )

            if success is False:
                raise RuntimeError("重命名执行失败，已自动回滚")

            # 更新数据库
            from database import get_pool
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE tasks SET rename_prefix = $1, rename_mapping = $2, updated_at = CURRENT_TIMESTAMP WHERE id = $3",
                    prefix, json.dumps(preview, ensure_ascii=False), task_id,
                )

            # 推进到 Step 4
            await pipeline_service.advance_step(task_id, from_step=2, to_step=3)
            await pipeline_service.add_log(task_id, f"重命名完成: {len(preview)} 个文件", step=2)

            return preview

        except Exception as e:
            await pipeline_service.update_step_status(
                task_id, step=2, status="failed", error=str(e)
            )
            await pipeline_service.add_log(task_id, f"重命名失败: {e}", step=2, level="error")
            raise


rename_service = RenameService()
