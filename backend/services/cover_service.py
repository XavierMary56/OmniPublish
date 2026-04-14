"""OmniPublish V2.0 — 封面制作服务"""

import asyncio
import json
import os
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
                                   head_margin: float = 0.15, size: str = "") -> list:
        """生成候选封面。"""
        await pipeline_service.update_step_status(task_id, step=3, status="running")
        await pipeline_service.add_log(
            task_id, f"开始生成封面候选: layout={layout}, candidates={candidates}, size={size or '默认'}", step=3
        )

        try:
            # 在线程池执行（Pillow + YOLO 是 CPU 密集型）
            from config import UPLOADS_DIR
            output_dir = str(UPLOADS_DIR / "covers" / str(task_id))
            os.makedirs(output_dir, exist_ok=True)

            # 统计可用图片数量，自动降级布局
            img_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
            available_imgs = [f for f in os.listdir(folder_path)
                              if os.path.splitext(f)[1].lower() in img_exts]
            img_count = len(available_imgs)

            layout_needs = {"triple": 3, "double": 2, "single": 1, "wide": 3, "portrait": 1}
            needed = layout_needs.get(layout, 3)

            if img_count < needed:
                # 自动降级：triple → double → single
                if img_count >= 2:
                    layout = "double"
                    await pipeline_service.add_log(
                        task_id, f"图片不足 {needed} 张，自动降级为双拼（可用 {img_count} 张）", step=3
                    )
                else:
                    layout = "single"
                    await pipeline_service.add_log(
                        task_id, f"图片不足，自动降级为单图模式（可用 {img_count} 张）", step=3
                    )

            cover_paths = await asyncio.to_thread(
                make_cover, folder_path, output_dir, layout, head_margin, 95, candidates, size
            )

            if not cover_paths:
                raise RuntimeError("未能生成任何封面候选")

            # 更新数据库
            from database import get_pool
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE tasks SET cover_candidates = $1, cover_layout = $2, updated_at = CURRENT_TIMESTAMP WHERE id = $3",
                    json.dumps(cover_paths, ensure_ascii=False), layout, task_id,
                )

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
        from database import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT cover_candidates FROM tasks WHERE id = $1", task_id,
            )
            if not row:
                raise ValueError("任务不存在")

            candidates = json.loads(row["cover_candidates"] or "[]")

            # 如果 cover_candidates 为空，尝试从素材目录自动扫描封面文件
            if not candidates:
                folder_row = await conn.fetchrow("SELECT folder_path FROM tasks WHERE id = $1", task_id)
                if folder_row and folder_row["folder_path"]:
                    folder = folder_row["folder_path"]
                    cover_files = sorted([
                        os.path.join(folder, f) for f in os.listdir(folder)
                        if "_cover_" in f.lower() or f.endswith(("_cover_A.jpg", "_cover_B.jpg", "_cover_C.jpg"))
                    ])
                    if cover_files:
                        candidates = cover_files
                        # 补存到数据库
                        await conn.execute(
                            "UPDATE tasks SET cover_candidates = $1 WHERE id = $2",
                            json.dumps(candidates, ensure_ascii=False), task_id,
                        )

            if not candidates:
                raise ValueError("没有可用的封面候选，请先点击「生成封面候选」")
            if cover_index < 0 or cover_index >= len(candidates):
                raise ValueError(f"封面索引超出范围: {cover_index}，有效范围 0-{len(candidates) - 1}")

            cover_path = candidates[cover_index]
            await conn.execute(
                "UPDATE tasks SET cover_path = $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2",
                cover_path, task_id,
            )

        # 推进到 Step 5
        await pipeline_service.advance_step(task_id, from_step=3, to_step=4)
        await pipeline_service.add_log(
            task_id, f"封面已确认: 候选 {chr(65 + cover_index)}", step=3
        )

        return cover_path


cover_service = CoverService()
