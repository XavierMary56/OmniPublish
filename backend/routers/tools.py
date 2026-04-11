"""OmniPublish V2.0 — 工具箱路由"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
from models.common import ApiResponse
from models.user import UserInfo
from middleware.auth import get_current_user
from services.tools_service import tools_service

router = APIRouter(prefix="/api/tools", tags=["工具箱"])


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


# ── 状态查询 ──

@router.get("/{job_id}/status")
async def job_status(job_id: str, user: UserInfo = Depends(get_current_user)):
    """查询工具执行状态。"""
    job = tools_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return ApiResponse.success(data=job.to_dict())
