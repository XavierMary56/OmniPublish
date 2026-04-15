"""OmniPublish V2.0 — 上传发布服务（Step 5-6）

完整发布流程（参照单机版 publish_folder）：
1. 登录 CMS 平台（RemotePublishClient）
2. 上传封面图片 → CDN URL
3. 逐张上传正文图片 → CDN URL 列表
4. 上传视频到 R2 → mp4_url + 注册 upload_mv
5. 轮询 mv_list 等待切片完成 → m3u8 URL
6. build_markdown 组装帖子正文
7. publish_post 创建草稿
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime

from services.pipeline_service import pipeline_service
from database import get_pool

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from publish_api import RemotePublishClient, parse_txt_file, build_markdown


class PublishService:
    """上传发布服务。"""

    # 切片轮询配置
    SLICE_POLL_INTERVAL = 10  # 秒
    SLICE_MAX_WAIT = 600      # 最多等 10 分钟

    def __init__(self):
        # 缓存各平台的 API client（复用登录态） — 实例级别而非类级别
        self._clients: dict = {}

    def _get_client(self, platform: dict) -> RemotePublishClient:
        """获取或创建平台 API client。"""
        # 预检查：crypto 密钥是否已配置
        from publish_api import APPKEY, KEY, IV
        if not APPKEY or len(KEY) < 16 or len(IV) < 16:
            raise ValueError(
                f"CMS 加密密钥未配置！请在 config.json 的 crypto 节中配置 appkey、aes_key(≥16字符)、aes_iv(≥16字符)。"
                f"当前: appkey={'已设置' if APPKEY else '空'}, aes_key={len(KEY)}字节, aes_iv={len(IV)}字节"
            )

        pid = platform.get("id") or platform.get("platform_id")
        if pid not in self._clients:
            base_url = platform.get("api_base_url", "")
            if not base_url:
                raise ValueError(f"平台 {platform.get('name', '?')} 未配置 API 地址")
            client = RemotePublishClient(base_url=base_url)
            client.project_code = platform.get("project_code", "")
            self._clients[pid] = client
        return self._clients[pid]

    async def _ensure_login(self, client: RemotePublishClient, platform: dict):
        """确保 client 已登录。优先从 accounts 表获取凭据，兼容 platform 直接传入的凭据。"""
        if client.token:
            return

        # 优先从 platform dict 中获取（JOIN 查询时已带上）
        username = platform.get("acc_username", "") or platform.get("cms_username", "")
        password = platform.get("acc_password", "") or platform.get("cms_password", "")

        # 如果没有，从 accounts 表查询
        if not username or not password:
            pid = platform.get("id") or platform.get("platform_id")
            pool = await get_pool()
            async with pool.acquire() as conn:
                acc = await conn.fetchrow(
                    "SELECT username, password_encrypted FROM accounts WHERE platform_id = $1",
                    pid,
                )
                if acc:
                    username = acc["username"] or ""
                    password = acc["password_encrypted"] or ""

        if not username or not password:
            raise ValueError(f"平台 {platform.get('name', '?')} 未配置登录凭据，请在「账号管理」中添加")

        # 在线程池中执行同步的登录操作
        await asyncio.to_thread(client.get_projects)
        await asyncio.to_thread(client.select_project)
        await asyncio.to_thread(client.login, username, password)

    async def publish_platforms(self, task_id: int, platform_ids: list = None):
        """发布指定平台（或全部已就绪）。"""
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
            if not row:
                raise ValueError("任务不存在")

            task_dict = dict(row)

            if platform_ids:
                placeholders = ",".join(f"${i+2}" for i in range(len(platform_ids)))
                pt_rows_raw = await conn.fetch(
                    f"""SELECT pt.*, p.name, p.api_base_url, p.project_code,
                        p.layout_template,
                        p.categories as platform_cats,
                        a.username as acc_username, a.password_encrypted as acc_password
                        FROM platform_tasks pt
                        JOIN platforms p ON pt.platform_id = p.id
                        LEFT JOIN accounts a ON a.platform_id = p.id
                        WHERE pt.task_id = $1 AND pt.platform_id IN ({placeholders})""",
                    task_id, *platform_ids,
                )
            else:
                pt_rows_raw = await conn.fetch(
                    """SELECT pt.*, p.name, p.api_base_url, p.project_code,
                       p.layout_template,
                       p.categories as platform_cats,
                       a.username as acc_username, a.password_encrypted as acc_password
                       FROM platform_tasks pt
                       JOIN platforms p ON pt.platform_id = p.id
                       LEFT JOIN accounts a ON a.platform_id = p.id
                       WHERE pt.task_id = $1
                       AND (pt.wm_status IN ('done', 'skipped', 'pending'))
                       AND pt.publish_status IN ('pending', 'failed')""",
                    task_id,
                )

            pt_rows = [dict(r) for r in pt_rows_raw]

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
        """发布到单个平台 — 完整流程。

        流程：登录 → 上传封面 → 上传图片 → 上传视频 → 等切片 → 组装正文 → 发帖
        """
        platform_id = pt["platform_id"]
        platform_name = pt["name"]
        folder_path = task.get("folder_path", "")

        await pipeline_service.update_platform_task(
            task_id, platform_id, publish_status="publishing", upload_progress=0
        )
        await pipeline_service.add_log(
            task_id, f"{platform_name}: 开始发布流程", step=5, platform_id=platform_id
        )

        try:
            # ── 0. 准备数据 ──
            title = task.get("confirmed_title", "")
            keywords = task.get("confirmed_keywords", "")
            body_text = task.get("confirmed_body", "")
            author = task.get("author", "")
            task_cats = json.loads(task.get("categories", "[]") or "[]")
            platform_cats = json.loads(pt.get("platform_cats", "[]") or "[]")
            filtered_cats = [c for c in task_cats if c in platform_cats] if platform_cats else task_cats
            category_str = filtered_cats[0] if filtered_cats else ""
            layout_template = pt.get("layout_template", "")

            # 确定素材目录（水印处理后的目录优先）
            wm_folder = pt.get("wm_images_dir", "")
            src_folder = wm_folder if wm_folder and os.path.isdir(wm_folder) else folder_path

            if not src_folder or not os.path.isdir(src_folder):
                raise ValueError(f"素材目录不存在: {src_folder}")

            # ── 1. 登录 ──
            await pipeline_service.add_log(
                task_id, f"{platform_name}: 登录中...", step=5, platform_id=platform_id
            )
            client = self._get_client(pt)
            await self._ensure_login(client, pt)
            await pipeline_service.update_platform_task(
                task_id, platform_id, upload_progress=5
            )

            # ── 2. 扫描素材 ──
            # 图片从水印目录（src_folder）取，视频和 TXT 从原始目录（folder_path）取
            # 水印服务只处理图片，视频仍在原始目录中
            img_exts = {".jpg", ".jpeg", ".png", ".webp"}
            vid_exts = {".mp4", ".mov", ".avi", ".mkv"}
            all_files = sorted(os.listdir(src_folder))
            image_files = [f for f in all_files
                           if os.path.splitext(f)[1].lower() in img_exts
                           and "_cover" not in f.lower()]
            cover_files = [f for f in all_files
                           if "_cover" in f.lower()
                           and os.path.splitext(f)[1].lower() in img_exts]

            # 视频和 TXT 始终从原始素材目录扫描（水印目录不包含视频）
            wm_vid_path = pt.get("wm_video_path", "")
            if wm_vid_path and os.path.isfile(wm_vid_path):
                # 有水印后的视频文件，直接使用
                video_files = [os.path.basename(wm_vid_path)]
                video_base_dir = os.path.dirname(wm_vid_path)
            else:
                orig_files = sorted(os.listdir(folder_path))
                video_files = [f for f in orig_files
                               if os.path.splitext(f)[1].lower() in vid_exts]
                video_base_dir = folder_path

            orig_files_for_txt = sorted(os.listdir(folder_path)) if src_folder != folder_path else all_files
            txt_files = [f for f in orig_files_for_txt if f.endswith(".txt")]

            # 如果有 TXT 但任务没有标题，从 TXT 解析
            if txt_files and not title:
                meta = await asyncio.to_thread(
                    parse_txt_file, os.path.join(folder_path, txt_files[0])
                )
                title = meta.get("title", title)
                keywords = meta.get("keywords", keywords)
                category_str = meta.get("category", category_str)
                author = meta.get("author", author)

            # ── 3. 上传封面 ──
            cover_url = ""
            if cover_files:
                await pipeline_service.add_log(
                    task_id, f"{platform_name}: 上传封面...", step=5, platform_id=platform_id
                )
                cover_path = os.path.join(src_folder, cover_files[0])
                cover_url = await asyncio.to_thread(client.upload_image, cover_path) or ""
            await pipeline_service.update_platform_task(
                task_id, platform_id, upload_progress=15
            )

            # ── 4. 上传正文图片 ──
            image_urls = []
            total_images = len(image_files)
            if total_images > 0:
                await pipeline_service.add_log(
                    task_id, f"{platform_name}: 上传 {total_images} 张图片...",
                    step=5, platform_id=platform_id
                )
                for i, fname in enumerate(image_files):
                    img_path = os.path.join(src_folder, fname)
                    url = await asyncio.to_thread(client.upload_image, img_path)
                    if url:
                        image_urls.append(url)
                    # 进度：15% ~ 40%
                    progress = 15 + int((i + 1) / total_images * 25)
                    await pipeline_service.update_platform_task(
                        task_id, platform_id, upload_progress=progress
                    )

            # ── 5. 上传视频到 R2 ──
            video_entries = []
            if video_files:
                await pipeline_service.add_log(
                    task_id, f"{platform_name}: 上传 {len(video_files)} 个视频...",
                    step=5, platform_id=platform_id
                )
                video_results = []
                for i, vf in enumerate(video_files):
                    video_path = os.path.join(video_base_dir, vf)
                    display_name = f"{title}_{i+1}" if len(video_files) > 1 else title
                    result = await asyncio.to_thread(
                        client.upload_video, video_path, cover_url, display_name
                    )
                    video_results.append(result)
                    # 进度：40% ~ 70%
                    progress = 40 + int((i + 1) / len(video_files) * 30)
                    await pipeline_service.update_platform_task(
                        task_id, platform_id, upload_progress=progress
                    )

                # 保存视频上传结果（断点续传用）
                results_file = os.path.join(src_folder, ".video_upload_results.json")
                with open(results_file, "w", encoding="utf-8") as f:
                    json.dump({"videos": video_results, "cover_url": cover_url},
                              f, ensure_ascii=False)

                # ── 6. 等待视频切片完成 ──
                await pipeline_service.add_log(
                    task_id, f"{platform_name}: 等待视频切片完成...",
                    step=5, platform_id=platform_id
                )
                await pipeline_service.update_platform_task(
                    task_id, platform_id, upload_progress=75
                )

                start_time = time.time()
                while time.time() - start_time < self.SLICE_MAX_WAIT:
                    all_ready = True
                    for vr in video_results:
                        mp4_url = vr.get("mp4_url", "")
                        if not mp4_url:
                            continue
                        matched = await asyncio.to_thread(
                            client.find_video_by_mp4, mp4_url
                        )
                        if matched:
                            # 已找到并且切片完成
                            if not any(ve.get("mp4_url") == mp4_url for ve in video_entries):
                                video_entries.append({
                                    "video_url": matched.get("video_url", ""),
                                    "cover": matched.get("cover", "") or cover_url,
                                    "id": matched.get("id"),
                                    "mp4_url": mp4_url,
                                })
                        else:
                            all_ready = False

                    if all_ready and len(video_entries) >= len(video_results):
                        break

                    elapsed = int(time.time() - start_time)
                    await pipeline_service.add_log(
                        task_id, f"{platform_name}: 切片等待中... ({elapsed}s)",
                        step=5, platform_id=platform_id
                    )
                    await asyncio.sleep(self.SLICE_POLL_INTERVAL)

                if len(video_entries) < len(video_results):
                    await pipeline_service.add_log(
                        task_id, f"{platform_name}: 警告 - {len(video_results) - len(video_entries)} 个视频切片未完成，继续发布已就绪的视频",
                        step=5, platform_id=platform_id, level="warn"
                    )

            await pipeline_service.update_platform_task(
                task_id, platform_id, upload_progress=85
            )

            # ── 7. 解析分类 ID ──
            cat_id = ""
            if category_str:
                cat_id = await asyncio.to_thread(
                    client.resolve_category_id, category_str
                )

            # ── 8. 组装帖子正文 ──
            # build_markdown 期望 sections = [{"h": "标题", "p": "段落"}]
            sections = []
            if body_text:
                # 按段落拆分，支持 ## 标题
                current_h = ""
                current_p = []
                for line in body_text.split("\n"):
                    stripped = line.strip()
                    if stripped.startswith("## "):
                        if current_p or current_h:
                            sections.append({"h": current_h, "p": "\n".join(current_p)})
                        current_h = stripped[3:].strip()
                        current_p = []
                    elif stripped:
                        current_p.append(stripped)
                if current_p or current_h:
                    sections.append({"h": current_h, "p": "\n".join(current_p)})

            meta = {
                "title": title,
                "author": author,
                "category": category_str,
                "keywords": keywords,
                "sections": sections,
            }
            body = await asyncio.to_thread(
                build_markdown, meta, image_urls, video_entries, layout_template or None
            )

            await pipeline_service.update_platform_task(
                task_id, platform_id, upload_progress=90
            )

            # ── 9. 发布帖子（存草稿） ──
            await pipeline_service.add_log(
                task_id, f"{platform_name}: 发布帖子（草稿）...",
                step=5, platform_id=platform_id
            )
            result = await asyncio.to_thread(
                client.publish_post,
                title=title,
                body=body,
                cover_url=cover_url,
                category_id=cat_id,
                tags=keywords,
                keyword=keywords,
                is_draft=3,
            )

            if result is not None:
                await pipeline_service.update_platform_task(
                    task_id, platform_id,
                    publish_status="published",
                    upload_progress=100,
                    publish_result=json.dumps({
                        "status": "draft",
                        "title": title,
                        "cover_url": cover_url,
                        "images_count": len(image_urls),
                        "videos_count": len(video_entries),
                        "category": category_str,
                        "post_data": result if isinstance(result, dict) else str(result),
                    }, ensure_ascii=False),
                )
                await pipeline_service.add_log(
                    task_id, f"{platform_name}: ✅ 发布成功（草稿） — {len(image_urls)}图 {len(video_entries)}视频",
                    step=5, platform_id=platform_id
                )
            else:
                raise RuntimeError("publish_post 返回 None，发布可能失败")

        except Exception as e:
            error_msg = str(e)
            await pipeline_service.update_platform_task(
                task_id, platform_id,
                publish_status="failed", publish_error=error_msg,
            )
            await pipeline_service.add_log(
                task_id, f"{platform_name}: ❌ 发布失败 - {error_msg}",
                step=5, platform_id=platform_id, level="error"
            )
            raise

    async def retry_platform(self, task_id: int, platform_id: int):
        """重试失败的平台。"""
        # 清除旧的 client 缓存（可能 token 过期）
        if platform_id in self._clients:
            del self._clients[platform_id]

        await pipeline_service.update_platform_task(
            task_id, platform_id,
            publish_status="pending", publish_error=None, upload_progress=0,
        )
        await self.publish_platforms(task_id, [platform_id])

    async def upload_video_only(self, task_id: int, platform_id: int):
        """仅上传视频（不发帖），用于预上传等待切片。"""
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
            pt_row = await conn.fetchrow(
                """SELECT pt.*, p.name, p.api_base_url, p.project_code,
                   a.username as acc_username, a.password_encrypted as acc_password
                   FROM platform_tasks pt
                   JOIN platforms p ON pt.platform_id = p.id
                   LEFT JOIN accounts a ON a.platform_id = p.id
                   WHERE pt.task_id = $1 AND pt.platform_id = $2""",
                task_id, platform_id,
            )

        if not row or not pt_row:
            raise ValueError("任务或平台不存在")

        task_dict = dict(row)
        pt = dict(pt_row)
        folder_path = task_dict.get("folder_path", "")

        client = self._get_client(pt)
        await self._ensure_login(client, pt)

        vid_exts = {".mp4", ".mov", ".avi", ".mkv"}
        video_files = [f for f in sorted(os.listdir(folder_path))
                       if os.path.splitext(f)[1].lower() in vid_exts]

        results = []
        for vf in video_files:
            video_path = os.path.join(folder_path, vf)
            title = task_dict.get("confirmed_title", vf)
            result = await asyncio.to_thread(
                client.upload_video, video_path, "", title
            )
            results.append(result)

        return results


publish_service = PublishService()
