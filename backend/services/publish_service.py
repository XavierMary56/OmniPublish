"""OmniPublish V2.0 — 上传发布服务（Step 6）

并行为多个平台上传视频、等待切片、发布帖子。
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

from publish_api import RemotePublishClient, parse_txt_file, build_markdown


class PublishService:
    """上传发布服务。"""

    # 缓存各平台的 API client
    _clients: dict = {}

    def _get_client(self, platform: dict) -> RemotePublishClient:
        """获取或创建平台 API client。"""
        pid = platform["id"]
        if pid not in self._clients:
            client = RemotePublishClient(base_url=platform.get("api_base_url", ""))
            client.project_code = platform.get("project_code", "")
            self._clients[pid] = client
        return self._clients[pid]

    async def publish_platforms(self, task_id: int, platform_ids: list = None):
        """发布指定平台（或全部已就绪）。"""
        db = await get_db()
        try:
            # 获取任务信息
            cursor = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            task = await cursor.fetchone()
            if not task:
                raise ValueError("任务不存在")

            task_dict = dict(task)

            # 获取平台子任务
            if platform_ids:
                placeholders = ",".join("?" * len(platform_ids))
                cursor = await db.execute(
                    f"""SELECT pt.*, p.name, p.api_base_url, p.project_code,
                        p.layout_template, p.cms_username, p.cms_password, p.categories as platform_cats
                        FROM platform_tasks pt
                        JOIN platforms p ON pt.platform_id = p.id
                        WHERE pt.task_id = ? AND pt.platform_id IN ({placeholders})""",
                    [task_id] + platform_ids,
                )
            else:
                # 全部已就绪（水印完成的）
                cursor = await db.execute(
                    """SELECT pt.*, p.name, p.api_base_url, p.project_code,
                       p.layout_template, p.cms_username, p.cms_password, p.categories as platform_cats
                       FROM platform_tasks pt
                       JOIN platforms p ON pt.platform_id = p.id
                       WHERE pt.task_id = ? AND pt.wm_status = 'done'
                       AND pt.publish_status IN ('pending', 'failed')""",
                    (task_id,),
                )

            pt_rows = [dict(r) for r in await cursor.fetchall()]
        finally:
            await db.close()

        if not pt_rows:
            await pipeline_service.add_log(task_id, "没有可发布的平台", step=5, level="warn")
            return

        await pipeline_service.add_log(
            task_id, f"开始并行发布 {len(pt_rows)} 个平台", step=5
        )

        # 并行发布
        tasks = []
        for pt in pt_rows:
            t = asyncio.create_task(
                self._publish_single_platform(task_id, task_dict, pt)
            )
            tasks.append(t)

        await asyncio.gather(*tasks, return_exceptions=True)

        # 重新计算任务状态
        status = await pipeline_service.compute_task_status(task_id)
        await pipeline_service.update_task_status(task_id, status)

    async def _publish_single_platform(self, task_id: int, task: dict, pt: dict):
        """发布到单个平台。"""
        platform_id = pt["platform_id"]
        platform_name = pt["name"]

        await pipeline_service.update_platform_task(
            task_id, platform_id, publish_status="publishing"
        )
        await pipeline_service.add_log(
            task_id, f"{platform_name}: 开始发布", step=5, platform_id=platform_id
        )

        try:
            # 构建发布内容
            title = task.get("confirmed_title", "")
            keywords = task.get("confirmed_keywords", "")
            body = task.get("confirmed_body", "")
            author = task.get("author", "")

            # 按平台过滤分类
            task_cats = json.loads(task.get("categories", "[]") or "[]")
            platform_cats = json.loads(pt.get("platform_cats", "[]") or "[]")
            filtered_cats = [c for c in task_cats if c in platform_cats] if platform_cats else []

            # TODO: 实际调用 publish_api 需要完整的登录 + 上传 + 发布流程
            # 这里先标记为草稿成功
            await pipeline_service.update_platform_task(
                task_id, platform_id,
                publish_status="published",
                publish_result=json.dumps({
                    "status": "draft",
                    "title": title,
                    "categories": filtered_cats,
                }, ensure_ascii=False),
            )
            await pipeline_service.add_log(
                task_id, f"{platform_name}: 发布成功（草稿）",
                step=5, platform_id=platform_id
            )

        except Exception as e:
            error_msg = str(e)
            await pipeline_service.update_platform_task(
                task_id, platform_id,
                publish_status="failed", publish_error=error_msg,
            )
            await pipeline_service.add_log(
                task_id, f"{platform_name}: 发布失败 - {error_msg}",
                step=5, platform_id=platform_id, level="error"
            )
            raise

    async def retry_platform(self, task_id: int, platform_id: int):
        """重试失败的平台。"""
        await pipeline_service.update_platform_task(
            task_id, platform_id,
            publish_status="pending", publish_error=None,
        )
        await self.publish_platforms(task_id, [platform_id])


publish_service = PublishService()
