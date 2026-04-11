"""OmniPublish V2.0 — 水印处理服务（Step 5）

并行为多个平台添加水印，通过 WebSocket 推送每个平台的独立进度。
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from services.pipeline_service import pipeline_service
from database import get_db

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from image_watermark import process_folder as watermark_images


class WatermarkService:
    """水印处理服务。"""

    async def get_watermark_plan(self, task_id: int) -> list:
        """获取各平台的水印方案。"""
        db = await get_db()
        try:
            cursor = await db.execute("SELECT target_platforms FROM tasks WHERE id = ?", (task_id,))
            task = await cursor.fetchone()
            if not task:
                return []

            platform_ids = json.loads(task["target_platforms"])
            if not platform_ids:
                return []

            placeholders = ",".join("?" * len(platform_ids))
            cursor = await db.execute(
                f"""SELECT id, name, dept, img_wm_file, img_wm_position, img_wm_width,
                    img_wm_opacity, vid_wm_file, vid_wm_mode, vid_wm_scale
                    FROM platforms WHERE id IN ({placeholders})""",
                platform_ids,
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            await db.close()

    async def process_all_platforms(self, task_id: int):
        """确认后并行处理所有平台的水印。"""
        await pipeline_service.update_step_status(task_id, step=4, status="running")
        await pipeline_service.add_log(task_id, "开始并行水印处理", step=4)

        plan = await self.get_watermark_plan(task_id)
        if not plan:
            await pipeline_service.update_step_status(
                task_id, step=4, status="failed", error="没有目标平台"
            )
            return

        # 获取任务文件夹
        db = await get_db()
        try:
            cursor = await db.execute("SELECT folder_path FROM tasks WHERE id = ?", (task_id,))
            task = await cursor.fetchone()
            folder_path = task["folder_path"]
        finally:
            await db.close()

        # 为每个平台创建异步任务
        tasks = []
        for platform in plan:
            t = asyncio.create_task(
                self._process_single_platform(task_id, folder_path, platform)
            )
            tasks.append(t)

        # 并行执行
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 统计结果
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        fail_count = sum(1 for r in results if isinstance(r, Exception))

        if fail_count == 0:
            await pipeline_service.advance_step(task_id, from_step=4, to_step=5)
            await pipeline_service.add_log(
                task_id, f"水印处理完成: {success_count} 个平台全部成功", step=4
            )
        elif success_count > 0:
            await pipeline_service.update_step_status(task_id, step=4, status="done")
            await pipeline_service.advance_step(task_id, from_step=4, to_step=5)
            await pipeline_service.add_log(
                task_id, f"水印处理部分完成: {success_count} 成功, {fail_count} 失败", step=4, level="warn"
            )
        else:
            await pipeline_service.update_step_status(
                task_id, step=4, status="failed", error=f"全部 {fail_count} 个平台水印处理失败"
            )

    async def _process_single_platform(self, task_id: int, folder_path: str, platform: dict):
        """处理单个平台的图片水印（在线程池执行）。"""
        platform_id = platform["id"]
        platform_name = platform["name"]

        await pipeline_service.update_platform_task(
            task_id, platform_id, wm_status="running", wm_progress=0
        )
        await pipeline_service.add_log(
            task_id, f"开始处理 {platform_name} 水印", step=4, platform_id=platform_id
        )

        try:
            # 输出目录：{素材文件夹}/wm_{平台名}/
            safe_name = platform_name.replace(" ", "_").replace("/", "_")
            output_dir = os.path.join(folder_path, f"wm_{safe_name}")

            wm_file = platform["img_wm_file"]
            if not wm_file or not os.path.exists(wm_file):
                # 无水印文件：跳过图片水印，直接标记完成
                await pipeline_service.update_platform_task(
                    task_id, platform_id,
                    wm_status="done", wm_progress=100,
                    wm_images_dir=folder_path,  # 使用原图
                )
                await pipeline_service.add_log(
                    task_id, f"{platform_name}: 无水印文件，跳过", step=4, platform_id=platform_id
                )
                return

            # 图片水印
            await asyncio.to_thread(
                watermark_images,
                folder=folder_path,
                output=output_dir,
                watermark_path=wm_file,
                img_width=platform.get("img_wm_width", 800),
                wm_width=platform.get("img_wm_width", 264),
                margin=10,
                position=platform.get("img_wm_position", "bottom-right"),
                recursive=False,
                opacity=platform.get("img_wm_opacity", 100),
            )

            await pipeline_service.update_platform_task(
                task_id, platform_id,
                wm_status="done", wm_progress=100,
                wm_images_dir=output_dir,
            )
            await pipeline_service.add_log(
                task_id, f"{platform_name}: 水印处理完成", step=4, platform_id=platform_id
            )

        except Exception as e:
            error_msg = str(e)
            await pipeline_service.update_platform_task(
                task_id, platform_id,
                wm_status="failed", wm_error=error_msg,
            )
            await pipeline_service.add_log(
                task_id, f"{platform_name}: 水印处理失败 - {error_msg}",
                step=4, platform_id=platform_id, level="error"
            )
            raise


watermark_service = WatermarkService()
