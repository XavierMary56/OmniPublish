"""OmniPublish V2.0 — 封面制作服务"""

import asyncio
import json
import sys
from pathlib import Path

from services.pipeline_service import pipeline_service

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from make_cover import make_cover, LAYOUT_CONFIG


class CoverService:
    """封面制作服务。"""

    def get_layouts(self) -> dict:
        """获取可用布局列表。"""
        return {
            k: {"width": v["width"], "height": v["height"], "panels": v["count"]}
            for k, v in LAYOUT_CONFIG.items()
        }

    async def generate_candidates(self, task_id: int, folder_path: str,
                                   layout: str = "triple", candidates: int = 3,
                                   head_margin: float = 0.15) -> list:
        """生成候选封面。"""
        await pipeline_service.update_step_status(task_id, step=3, status="running")
        await pipeline_service.add_log(
            task_id, f"开始生成封面候选: layout={layout}, candidates={candidates}", step=3
        )

        try:
            # 在线程池执行（Pillow + YOLO 是 CPU 密集型）
            cover_paths = await asyncio.to_thread(
                make_cover, folder_path, folder_path, layout, head_margin, 95, candidates
            )

            if not cover_paths:
                raise RuntimeError("未能生成任何封面候选")

            # 更新数据库
            from database import get_db
            db = await get_db()
            try:
                await db.execute(
                    "UPDATE tasks SET cover_candidates = ?, cover_layout = ?, updated_at = datetime('now') WHERE id = ?",
                    (json.dumps(cover_paths, ensure_ascii=False), layout, task_id),
                )
                await db.commit()
            finally:
                await db.close()

            # 状态：等待用户确认
            await pipeline_service.update_step_status(
                task_id, step=3, status="awaiting_confirm",
                data={"candidates": cover_paths, "count": len(cover_paths)},
            )
            await pipeline_service.add_log(
                task_id, f"封面生成完成: {len(cover_paths)} 个候选", step=3
            )

            return cover_paths

        except Exception as e:
            await pipeline_service.update_step_status(
                task_id, step=3, status="failed", error=str(e)
            )
            await pipeline_service.add_log(task_id, f"封面生成失败: {e}", step=3, level="error")
            raise

    async def confirm_cover(self, task_id: int, cover_index: int) -> str:
        """确认选中的封面，推进到 Step 5。"""
        from database import get_db
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT cover_candidates FROM tasks WHERE id = ?", (task_id,)
            )
            task = await cursor.fetchone()
            if not task:
                raise ValueError("任务不存在")

            candidates = json.loads(task["cover_candidates"] or "[]")
            if not candidates:
                raise ValueError("没有可用的封面候选")
            if cover_index >= len(candidates):
                raise ValueError(f"封面索引超出范围: {cover_index} >= {len(candidates)}")

            cover_path = candidates[cover_index]
            await db.execute(
                "UPDATE tasks SET cover_path = ?, updated_at = datetime('now') WHERE id = ?",
                (cover_path, task_id),
            )
            await db.commit()
        finally:
            await db.close()

        # 推进到 Step 5
        await pipeline_service.advance_step(task_id, from_step=3, to_step=4)
        await pipeline_service.add_log(
            task_id, f"封面已确认: 候选 {chr(65 + cover_index)}", step=3
        )

        return cover_path


cover_service = CoverService()
