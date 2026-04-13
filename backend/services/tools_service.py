"""OmniPublish V2.0 — 工具箱服务

10 个独立工具，不走流水线，直接 import 脚本模块执行。
每个工具调用返回 job_id，前端通过轮询获取状态。
"""

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


class ToolJob:
    """工具执行任务。"""
    __slots__ = ("id", "tool", "status", "progress", "result", "error", "created_at", "finished_at", "params")

    def __init__(self, tool: str, params: dict):
        self.id = uuid.uuid4().hex[:12]
        self.tool = tool
        self.params = params
        self.status = "pending"    # pending / running / done / failed
        self.progress = 0
        self.result = {}
        self.error = None
        self.created_at = time.time()
        self.finished_at = None

    def to_dict(self) -> dict:
        return {
            "id": self.id, "tool": self.tool, "status": self.status,
            "progress": self.progress, "result": self.result,
            "error": self.error, "created_at": self.created_at,
            "finished_at": self.finished_at,
        }


class ToolsService:
    """工具箱服务管理器。"""

    def __init__(self):
        self._jobs: dict[str, ToolJob] = {}
        # 只保留最近 100 个 job，避免内存膨胀
        self._max_jobs = 100

    def get_job(self, job_id: str) -> Optional[ToolJob]:
        return self._jobs.get(job_id)

    def _register(self, tool: str, params: dict) -> ToolJob:
        job = ToolJob(tool, params)
        self._jobs[job.id] = job
        # 清理旧 job
        if len(self._jobs) > self._max_jobs:
            oldest = sorted(self._jobs.values(), key=lambda j: j.created_at)
            for j in oldest[:len(self._jobs) - self._max_jobs]:
                del self._jobs[j.id]
        return job

    # ════════════════════════════════════════
    # 视频工具
    # ════════════════════════════════════════

    async def delogo(self, input_dir: str, output_dir: str = "", orient: str = "auto",
                     codec: str = "libx264", bitrate: str = "2M", coords: dict = None) -> str:
        """遮盖四角水印。"""
        extra = {}
        if coords:
            extra = {k: v for k, v in coords.items() if v}
        job = self._register("delogo", {**locals(), **extra})
        asyncio.create_task(self._run_video_cmd(job, "delogo", input_dir, output_dir, orient=orient, codec=codec, bitrate=bitrate, **extra))
        return job.id

    async def crop(self, input_dir: str, output_dir: str = "", orient: str = "auto",
                   codec: str = "libx264", bitrate: str = "2M") -> str:
        """裁掉四角水印。"""
        job = self._register("crop", locals())
        asyncio.create_task(self._run_video_cmd(job, "crop", input_dir, output_dir, orient=orient, codec=codec, bitrate=bitrate))
        return job.id

    async def blur_pad(self, input_dir: str, output_dir: str = "", orient: str = "auto",
                       strength: str = "5:1", codec: str = "libx264", bitrate: str = "2M") -> str:
        """虚化填充。"""
        job = self._register("blur_pad", locals())
        asyncio.create_task(self._run_video_cmd(job, "blur-pad", input_dir, output_dir, orient=orient, codec=codec, bitrate=bitrate, strength=strength))
        return job.id

    async def trim(self, input_dir: str, output_dir: str = "", start_sec: int = 0,
                   end_sec: int = 11, mode: str = "copy", codec: str = "libx264", bitrate: str = "2M") -> str:
        """裁掉片头片尾。"""
        job = self._register("trim", locals())
        asyncio.create_task(self._run_video_cmd(job, "trim", input_dir, output_dir,
                                                 codec=codec, bitrate=bitrate, start=start_sec, end=end_sec, mode=mode))
        return job.id

    async def add_intro_outro(self, input_dir: str, output_dir: str = "",
                               intro: str = "", outro: str = "",
                               codec: str = "libx264", bitrate: str = "2M") -> str:
        """加片头片尾。"""
        job = self._register("intro_outro", locals())
        asyncio.create_task(self._run_video_cmd(job, "add-intro-outro", input_dir, output_dir,
                                                 codec=codec, bitrate=bitrate, intro=intro, outro=outro))
        return job.id

    async def concat(self, input_dir: str, output_path: str = "",
                     method: str = "demuxer", scale: str = "first") -> str:
        """多视频合成。"""
        job = self._register("concat", locals())
        asyncio.create_task(self._run_video_cmd(job, "concat", input_dir, output_path,
                                                 method=method, scale=scale))
        return job.id

    async def compress(self, input_dir: str, output_dir: str = "",
                       target_size_mb: int = 100, codec: str = "libx264") -> str:
        """视频压缩。"""
        job = self._register("compress", locals())

        async def _run():
            job.status = "running"
            try:
                from video_process import find_videos, compress_to_size
                videos = find_videos(input_dir)
                if not videos:
                    raise FileNotFoundError(f"目录下无视频文件: {input_dir}")
                total = len(videos)
                for i, f in enumerate(videos):
                    await asyncio.to_thread(compress_to_size, f, target_size_mb, codec)
                    job.progress = int((i + 1) / total * 100)
                job.status = "done"
                job.result = {"count": total}
            except Exception as e:
                job.status = "failed"
                job.error = str(e)
            job.finished_at = time.time()

        asyncio.create_task(_run())
        return job.id

    # ════════════════════════════════════════
    # 图片工具
    # ════════════════════════════════════════

    async def vid_watermark(self, input_dir: str, output_dir: str = "",
                            watermark_path: str = "", orient: str = "auto",
                            codec: str = "libx264", bitrate: str = "2M",
                            scale: float = 0.35) -> str:
        """视频加水印（MOV 动态四角轮转）。"""
        job = self._register("vid_watermark", locals())

        async def _run():
            job.status = "running"
            try:
                import argparse
                from video_process import cmd_watermark, find_videos

                videos = find_videos(input_dir)
                if not videos:
                    raise FileNotFoundError(f"目录下无视频文件: {input_dir}")

                out = output_dir or os.path.join(input_dir, "已处理")
                ns = argparse.Namespace(
                    input=input_dir, output=out,
                    watermark=watermark_path,
                    orient=orient, codec=codec, bitrate=bitrate,
                    fps=30, scale=scale,
                    compress=False, target_size=None,
                )
                await asyncio.to_thread(cmd_watermark, ns)
                job.status = "done"
                job.progress = 100
                job.result = {"count": len(videos), "output_dir": out}
            except Exception as e:
                job.status = "failed"
                job.error = str(e)
            job.finished_at = time.time()

        asyncio.create_task(_run())
        return job.id

    async def img_watermark(self, input_dir: str, output_dir: str = "",
                            watermark_path: str = "", position: str = "bottom-right",
                            wm_width: int = 264) -> str:
        """图片批量加水印。"""
        job = self._register("img_watermark", locals())

        async def _run():
            job.status = "running"
            try:
                import glob
                from PIL import Image
                img_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
                images = [f for f in sorted(os.listdir(input_dir))
                          if os.path.splitext(f)[1].lower() in img_exts]
                if not images:
                    raise FileNotFoundError(f"目录下无图片文件: {input_dir}")
                if not watermark_path or not os.path.exists(watermark_path):
                    raise FileNotFoundError(f"水印文件不存在: {watermark_path}")

                out = output_dir or os.path.join(input_dir, "watermarked")
                os.makedirs(out, exist_ok=True)
                wm = Image.open(watermark_path).convert("RGBA")
                # 缩放水印
                ratio = wm_width / wm.width
                wm = wm.resize((wm_width, int(wm.height * ratio)), Image.LANCZOS)

                total = len(images)
                for i, fname in enumerate(images):
                    img = Image.open(os.path.join(input_dir, fname)).convert("RGBA")
                    # 计算位置
                    margin = 10
                    if position == "bottom-right":
                        pos = (img.width - wm.width - margin, img.height - wm.height - margin)
                    elif position == "bottom-left":
                        pos = (margin, img.height - wm.height - margin)
                    elif position == "top-right":
                        pos = (img.width - wm.width - margin, margin)
                    else:
                        pos = (margin, margin)
                    img.paste(wm, pos, wm)
                    img.convert("RGB").save(os.path.join(out, fname), quality=95)
                    job.progress = int((i + 1) / total * 100)

                job.status = "done"
                job.result = {"count": total, "output_dir": out}
            except Exception as e:
                job.status = "failed"
                job.error = str(e)
            job.finished_at = time.time()

        asyncio.create_task(_run())
        return job.id

    async def smart_cover(self, input_dir: str, layout: str = "triple", candidates: int = 3) -> str:
        """智能封面。"""
        job = self._register("smart_cover", locals())

        async def _run():
            job.status = "running"
            try:
                from make_cover import make_cover
                paths = await asyncio.to_thread(make_cover, input_dir, input_dir, layout, 0.15, 95, candidates)
                job.status = "done"
                job.progress = 100
                job.result = {"covers": paths or [], "count": len(paths or [])}
            except Exception as e:
                job.status = "failed"
                job.error = str(e)
            job.finished_at = time.time()

        asyncio.create_task(_run())
        return job.id

    async def convert_image(self, input_dir: str, output_dir: str = "", target_format: str = "jpg") -> str:
        """图片格式转换。"""
        job = self._register("convert_image", locals())

        async def _run():
            job.status = "running"
            try:
                from PIL import Image
                exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}
                out = output_dir or os.path.join(input_dir, "converted")
                os.makedirs(out, exist_ok=True)

                files = [f for f in os.listdir(input_dir)
                         if os.path.splitext(f)[1].lower() in exts
                         and os.path.isfile(os.path.join(input_dir, f))]
                if not files:
                    raise FileNotFoundError("目录下无图片文件")

                fmt_map = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}
                save_fmt = fmt_map.get(target_format.lower(), "JPEG")
                ext = f".{target_format.lower()}"

                for i, fname in enumerate(sorted(files)):
                    img = Image.open(os.path.join(input_dir, fname)).convert("RGB")
                    new_name = os.path.splitext(fname)[0] + ext
                    img.save(os.path.join(out, new_name), save_fmt, quality=95)
                    job.progress = int((i + 1) / len(files) * 100)

                job.status = "done"
                job.result = {"count": len(files), "format": target_format, "output": out}
            except Exception as e:
                job.status = "failed"
                job.error = str(e)
            job.finished_at = time.time()

        asyncio.create_task(_run())
        return job.id

    # ════════════════════════════════════════
    # AI 工具
    # ════════════════════════════════════════

    async def copywrite(self, protagonist: str, event: str, style: str = "反转打脸风",
                         author: str = "编辑", body_len: int = 300) -> str:
        """独立文案生成。"""
        job = self._register("copywrite", locals())

        async def _run():
            job.status = "running"
            try:
                from copywrite_gen import build_system_prompt, build_user_prompt, call_api, parse_result
                from config import settings, PROMPTS_DIR

                system_prompt = build_system_prompt(str(PROMPTS_DIR), style)

                class _A:
                    pass
                args = _A()
                args.protagonist = protagonist
                args.event = event
                args.photos = ""
                args.video_desc = ""
                args.title_min = 25
                args.title_max = 30
                args.kw_count = 10
                args.body_len = body_len
                args.paragraphs = 3
                args.author = author
                args.category = ""

                user_prompt = build_user_prompt(args)
                text = await asyncio.to_thread(
                    call_api, system_prompt, user_prompt,
                    settings.api_base, settings.api_key, settings.cw_model
                )
                result = parse_result(text, author, "")
                job.status = "done"
                job.progress = 100
                job.result = result
            except Exception as e:
                job.status = "failed"
                job.error = str(e)
            job.finished_at = time.time()

        asyncio.create_task(_run())
        return job.id

    # ════════════════════════════════════════
    # 通用视频命令执行器
    # ════════════════════════════════════════

    async def _run_video_cmd(self, job: ToolJob, command: str, input_dir: str,
                              output: str = "", **extra):
        """通用 video_process 子命令执行。"""
        job.status = "running"
        try:
            import argparse
            from video_process import (
                cmd_delogo, cmd_crop, cmd_blur_pad, cmd_trim,
                cmd_add_intro_outro, cmd_concat, cmd_watermark,
                detect_default_codec, find_videos,
            )

            codec = extra.pop("codec", None) or detect_default_codec()
            bitrate = extra.pop("bitrate", "2M")
            orient = extra.pop("orient", "auto")

            videos = find_videos(input_dir)
            if not videos and command != "concat":
                raise FileNotFoundError(f"目录下无视频文件: {input_dir}")

            out = output or os.path.join(input_dir, "已处理")

            # 构建 argparse.Namespace
            ns = argparse.Namespace(
                input=input_dir, output=out, codec=codec, bitrate=bitrate,
                fps=30, orient=orient, **extra,
            )

            dispatch = {
                "delogo": cmd_delogo, "crop": cmd_crop, "blur-pad": cmd_blur_pad,
                "trim": cmd_trim, "add-intro-outro": cmd_add_intro_outro,
                "concat": cmd_concat, "watermark": cmd_watermark,
            }
            fn = dispatch.get(command)
            if not fn:
                raise ValueError(f"未知命令: {command}")

            await asyncio.to_thread(fn, ns)
            job.status = "done"
            job.progress = 100
            job.result = {"command": command, "output": out, "count": len(videos)}

        except Exception as e:
            job.status = "failed"
            job.error = str(e)
        job.finished_at = time.time()


# 全局单例
tools_service = ToolsService()
