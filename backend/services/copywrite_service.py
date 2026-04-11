"""OmniPublish V2.0 — 文案生成服务

直接 import copywrite_gen.py 的核心函数，不走 subprocess。
"""

import asyncio
import sys
import os
from pathlib import Path
from typing import Optional

from config import settings, PROMPTS_DIR
from services.pipeline_service import pipeline_service

# 将 scripts 目录加入 Python 路径
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from copywrite_gen import build_system_prompt, build_user_prompt, call_api, parse_result


class CopywriteService:
    """AI 文案生成服务。"""

    async def generate(self, task_id: int, params: dict) -> dict:
        """异步生成文案。

        Args:
            task_id: 任务 ID
            params: {protagonist, event, photos, video_desc, style, author,
                     categories, title_min, title_max, kw_count, body_len, paragraphs}

        Returns:
            {title, keywords, body, author, category}
        """
        await pipeline_service.update_step_status(task_id, step=1, status="running")
        await pipeline_service.add_log(task_id, f"开始 AI 文案生成 (文风: {params.get('style', '默认')})", step=1)

        try:
            # 组装 prompt
            style = params.get("style", "反转打脸风")
            prompts_dir = str(PROMPTS_DIR)
            system_prompt = build_system_prompt(prompts_dir, style)

            # 构建一个类似 argparse.Namespace 的对象给 build_user_prompt
            class _Args:
                pass
            args = _Args()
            args.protagonist = params.get("protagonist", "")
            args.event = params.get("event", "")
            args.photos = params.get("photos", "")
            args.video_desc = params.get("video_desc", "")
            args.title_min = params.get("title_min", 25)
            args.title_max = params.get("title_max", 30)
            args.kw_count = params.get("kw_count", 10)
            args.body_len = params.get("body_len", 300)
            args.paragraphs = params.get("paragraphs", 3)
            args.author = params.get("author", "编辑")
            args.category = ",".join(params.get("categories", []))

            user_prompt = build_user_prompt(args)

            api_base = settings.api_base
            api_key = settings.api_key
            model = settings.cw_model

            if not api_key:
                raise ValueError("未配置 API Key，无法生成文案。请在 config.json 中设置 api_key")

            # 在线程池中执行（urllib 是同步的）
            full_text = await asyncio.to_thread(
                call_api, system_prompt, user_prompt, api_base, api_key, model
            )

            # 解析结果
            result = parse_result(full_text, args.author, args.category)

            # 更新步骤状态
            await pipeline_service.update_step_status(
                task_id, step=1, status="awaiting_confirm", data=result
            )
            await pipeline_service.add_log(
                task_id, f"文案生成完成: {result.get('title', '')[:30]}...", step=1
            )

            return result

        except Exception as e:
            error_msg = str(e)
            await pipeline_service.update_step_status(
                task_id, step=1, status="failed", error=error_msg
            )
            await pipeline_service.add_log(task_id, f"文案生成失败: {error_msg}", step=1, level="error")
            raise


# 全局单例
copywrite_service = CopywriteService()
