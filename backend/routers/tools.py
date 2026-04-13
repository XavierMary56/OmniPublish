"""OmniPublish V2.0 — 工具箱路由"""

import os
import uuid
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from pydantic import BaseModel, Field
from typing import List, Optional
from models.common import ApiResponse
from models.user import UserInfo
from middleware.auth import get_current_user
from services.tools_service import tools_service
from config import BACKEND_DIR

router = APIRouter(prefix="/api/tools", tags=["工具箱"])

TOOL_UPLOAD_ROOT = os.path.join(BACKEND_DIR, "uploads", "tools")
os.makedirs(TOOL_UPLOAD_ROOT, exist_ok=True)


# ── 请求模型 ──

class VideoToolRequest(BaseModel):
    input_dir: str = Field(..., min_length=1)
    output_dir: str = ""
    orient: str = "auto"
    codec: str = "libx264"
    bitrate: str = "2M"

class TrimRequest(VideoToolRequest):
    start_sec: int = 0
    end_sec: int = 11
    mode: str = "copy"

class IntroOutroRequest(VideoToolRequest):
    intro: str = ""
    outro: str = ""

class ConcatRequest(BaseModel):
    input_dir: str = Field(..., min_length=1)
    output_path: str = ""
    method: str = "demuxer"
    scale: str = "first"

class CompressRequest(BaseModel):
    input_dir: str = Field(..., min_length=1)
    output_dir: str = ""
    target_size_mb: int = 100
    codec: str = "libx264"

class BlurPadRequest(VideoToolRequest):
    strength: str = "5:1"

class CoverRequest(BaseModel):
    input_dir: str = Field(..., min_length=1)
    layout: str = "triple"
    candidates: int = 3

class ConvertRequest(BaseModel):
    input_dir: str = Field(..., min_length=1)
    output_dir: str = ""
    target_format: str = "jpg"

class CopywriteRequest(BaseModel):
    protagonist: str = Field(..., min_length=1)
    event: str = Field(..., min_length=1)
    style: str = "反转打脸风"
    author: str = "编辑"
    body_len: int = 300


# ── 视频工具 ──

@router.post("/delogo")
async def delogo(req: VideoToolRequest, user: UserInfo = Depends(get_current_user)):
    """遮盖四角水印。"""
    job_id = await tools_service.delogo(req.input_dir, req.output_dir, req.orient, req.codec, req.bitrate)
    return ApiResponse.success(data={"job_id": job_id}, message="任务已启动")


@router.post("/crop")
async def crop(req: VideoToolRequest, user: UserInfo = Depends(get_current_user)):
    """裁掉四角水印。"""
    job_id = await tools_service.crop(req.input_dir, req.output_dir, req.orient, req.codec, req.bitrate)
    return ApiResponse.success(data={"job_id": job_id}, message="任务已启动")


@router.post("/blur-pad")
async def blur_pad(req: BlurPadRequest, user: UserInfo = Depends(get_current_user)):
    """虚化填充。"""
    job_id = await tools_service.blur_pad(req.input_dir, req.output_dir, req.orient, req.strength, req.codec, req.bitrate)
    return ApiResponse.success(data={"job_id": job_id}, message="任务已启动")


@router.post("/trim")
async def trim(req: TrimRequest, user: UserInfo = Depends(get_current_user)):
    """裁掉片头片尾。"""
    job_id = await tools_service.trim(req.input_dir, req.output_dir, req.start_sec, req.end_sec, req.mode, req.codec, req.bitrate)
    return ApiResponse.success(data={"job_id": job_id}, message="任务已启动")


@router.post("/intro-outro")
async def intro_outro(req: IntroOutroRequest, user: UserInfo = Depends(get_current_user)):
    """添加片头片尾。"""
    if not req.intro and not req.outro:
        raise HTTPException(status_code=400, detail="至少提供 intro 或 outro")
    job_id = await tools_service.add_intro_outro(req.input_dir, req.output_dir, req.intro, req.outro, req.codec, req.bitrate)
    return ApiResponse.success(data={"job_id": job_id}, message="任务已启动")


@router.post("/concat")
async def concat(req: ConcatRequest, user: UserInfo = Depends(get_current_user)):
    """多视频合成。"""
    job_id = await tools_service.concat(req.input_dir, req.output_path, req.method, req.scale)
    return ApiResponse.success(data={"job_id": job_id}, message="任务已启动")


@router.post("/compress")
async def compress(req: CompressRequest, user: UserInfo = Depends(get_current_user)):
    """视频压缩。"""
    job_id = await tools_service.compress(req.input_dir, req.output_dir, req.target_size_mb, req.codec)
    return ApiResponse.success(data={"job_id": job_id}, message="任务已启动")


# ── 图片工具 ──

@router.post("/smart-cover")
async def smart_cover(req: CoverRequest, user: UserInfo = Depends(get_current_user)):
    """智能封面。"""
    job_id = await tools_service.smart_cover(req.input_dir, req.layout, req.candidates)
    return ApiResponse.success(data={"job_id": job_id}, message="任务已启动")


@router.post("/convert-image")
async def convert_image(req: ConvertRequest, user: UserInfo = Depends(get_current_user)):
    """图片格式转换。"""
    job_id = await tools_service.convert_image(req.input_dir, req.output_dir, req.target_format)
    return ApiResponse.success(data={"job_id": job_id}, message="任务已启动")


# ── AI 工具 ──

@router.post("/copywrite")
async def copywrite(req: CopywriteRequest, user: UserInfo = Depends(get_current_user)):
    """独立文案生成。"""
    job_id = await tools_service.copywrite(req.protagonist, req.event, req.style, req.author, req.body_len)
    return ApiResponse.success(data={"job_id": job_id}, message="文案生成已启动")


# ══════════════════════════════════════════
# 统一文件上传+执行接口（前端使用此接口）
# ══════════════════════════════════════════

@router.post("/run")
async def run_tool_with_upload(
    tool_key: str = Form(...),
    files: List[UploadFile] = File(default=[]),
    watermark: List[UploadFile] = File(default=[]),
    intro_file: List[UploadFile] = File(default=[]),
    outro_file: List[UploadFile] = File(default=[]),
    orient: str = Form(default="auto"),
    codec: str = Form(default="libx264"),
    bitrate: str = Form(default="2M"),
    strength: str = Form(default="5:1"),
    start_sec: int = Form(default=0),
    end_sec: int = Form(default=11),
    mode: str = Form(default="remove"),
    method: str = Form(default="filter"),
    scale: str = Form(default="auto"),
    target_size_mb: int = Form(default=100),
    layout: str = Form(default="triple"),
    headroom: int = Form(default=15),
    candidates: int = Form(default=3),
    position: str = Form(default="bottom-right"),
    wm_width: int = Form(default=264),
    target_format: str = Form(default="jpg"),
    quality: int = Form(default=90),
    protagonist: str = Form(default=""),
    event: str = Form(default=""),
    style: str = Form(default="反转打脸风"),
    body_len: int = Form(default=300),
    tl: str = Form(default="1:1:304:160"),
    tr: str = Form(default="415:1:304:160"),
    bl: str = Form(default="1:1119:304:160"),
    br: str = Form(default="415:1119:304:160"),
    user: UserInfo = Depends(get_current_user),
):
    """统一工具执行入口：上传文件 → 保存到临时目录 → 执行对应工具。"""

    # 1. 保存上传文件到临时目录
    folder_id = uuid.uuid4().hex[:12]
    input_dir = os.path.join(TOOL_UPLOAD_ROOT, folder_id, "input")
    output_dir = os.path.join(TOOL_UPLOAD_ROOT, folder_id, "output")
    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    saved_count = 0
    for f in files:
        if not f.filename:
            continue
        safe_name = os.path.basename(f.filename)
        dest = os.path.join(input_dir, safe_name)
        content = await f.read()
        with open(dest, "wb") as fp:
            fp.write(content)
        saved_count += 1

    # 保存额外文件（水印、片头、片尾）
    extras_dir = os.path.join(TOOL_UPLOAD_ROOT, folder_id, "extras")
    os.makedirs(extras_dir, exist_ok=True)

    wm_path = ""
    if watermark:
        for wf in watermark:
            if wf.filename:
                wm_path = os.path.join(extras_dir, os.path.basename(wf.filename))
                content = await wf.read()
                with open(wm_path, "wb") as fp:
                    fp.write(content)
                break

    intro_path = ""
    if intro_file:
        for inf in intro_file:
            if inf.filename:
                intro_path = os.path.join(extras_dir, "intro_" + os.path.basename(inf.filename))
                content = await inf.read()
                with open(intro_path, "wb") as fp:
                    fp.write(content)
                break

    outro_path = ""
    if outro_file:
        for ouf in outro_file:
            if ouf.filename:
                outro_path = os.path.join(extras_dir, "outro_" + os.path.basename(ouf.filename))
                content = await ouf.read()
                with open(outro_path, "wb") as fp:
                    fp.write(content)
                break

    # 2. 根据 tool_key 调用对应服务
    job_id = None

    if tool_key == "delogo":
        job_id = await tools_service.delogo(input_dir, output_dir, orient, codec, bitrate,
                                            coords={"tl": tl, "tr": tr, "bl": bl, "br": br})
    elif tool_key == "crop":
        job_id = await tools_service.crop(input_dir, output_dir, orient, codec, bitrate)
    elif tool_key == "blur-pad":
        job_id = await tools_service.blur_pad(input_dir, output_dir, orient, strength, codec, bitrate)
    elif tool_key == "trim":
        if mode == "remove":
            job_id = await tools_service.trim(input_dir, output_dir, start_sec, end_sec, "copy", codec, bitrate)
        else:
            if not intro_path and not outro_path:
                raise HTTPException(status_code=400, detail="添加模式需提供片头或片尾视频")
            job_id = await tools_service.add_intro_outro(input_dir, output_dir, intro_path, outro_path, codec, bitrate)
    elif tool_key == "concat":
        job_id = await tools_service.concat(input_dir, os.path.join(output_dir, "merged.mp4"), method, scale)
    elif tool_key == "compress":
        job_id = await tools_service.compress(input_dir, output_dir, target_size_mb, codec)
    elif tool_key == "smart-cover":
        job_id = await tools_service.smart_cover(input_dir, layout, candidates)
    elif tool_key == "vid-watermark":
        if not wm_path:
            raise HTTPException(status_code=400, detail="请上传水印文件（PNG 或 MOV）")
        job_id = await tools_service.vid_watermark(input_dir, output_dir, wm_path, orient, codec, bitrate)
    elif tool_key == "img-watermark":
        if not wm_path:
            raise HTTPException(status_code=400, detail="请上传水印图片")
        job_id = await tools_service.img_watermark(input_dir, output_dir, wm_path, position, wm_width)
    elif tool_key == "convert-image":
        job_id = await tools_service.convert_image(input_dir, output_dir, target_format)
    elif tool_key == "copywrite":
        if not protagonist or not event:
            raise HTTPException(status_code=400, detail="主角和事件不能为空")
        job_id = await tools_service.copywrite(protagonist, event, style, "编辑", body_len)
    else:
        raise HTTPException(status_code=400, detail=f"未知工具: {tool_key}")

    return ApiResponse.success(data={
        "job_id": job_id,
        "input_dir": input_dir,
        "output_dir": output_dir,
        "files_count": saved_count,
    }, message="任务已启动")


# ── 状态查询 ──

@router.get("/job/{job_id}")
async def job_status(job_id: str, user: UserInfo = Depends(get_current_user)):
    """查询工具执行状态。"""
    job = tools_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return ApiResponse.success(data=job.to_dict())
