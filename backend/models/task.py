"""OmniPublish V2.0 — 任务相关数据模型"""

from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class TaskStatus(str, Enum):
    DRAFT = "draft"
    RUNNING = "running"
    AWAITING_CONFIRM = "awaiting_confirm"
    SLICING = "slicing"
    DONE = "done"
    PARTIAL = "partial"
    FAILED = "failed"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_CONFIRM = "awaiting_confirm"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class PlatformTaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    UPLOADING = "uploading"
    TRANSCODING = "transcoding"
    READY = "ready"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    DONE = "done"
    FAILED = "failed"


# ── 请求模型 ──

class CreateTaskRequest(BaseModel):
    """Step 1 提交：创建任务。"""
    folder_path: str = Field(..., min_length=1)
    target_platforms: List[int] = Field(..., min_items=1)


class ConfirmCopyRequest(BaseModel):
    """Step 2 确认：文案确认。"""
    title: str = Field(..., min_length=1)
    keywords: str = ""
    body: str = ""
    author: str = ""
    categories: List[str] = []


class GenerateCopyRequest(BaseModel):
    """Step 2 触发：AI 文案生成。"""
    protagonist: str = Field(..., min_length=1)
    event: str = Field(..., min_length=1)
    photos: str = ""
    video_desc: str = ""
    style: str = "反转打脸风"
    author: str = "编辑"
    categories: List[str] = []
    title_min: int = 25
    title_max: int = 30
    kw_count: int = 10
    body_len: int = 300
    paragraphs: int = 3


class ConfirmRenameRequest(BaseModel):
    """Step 3 确认：重命名。"""
    prefix: str = Field(..., min_length=1)
    start: int = 1
    digits: int = 2
    separator: str = "_"


class ConfirmCoverRequest(BaseModel):
    """Step 4 确认：封面选择。"""
    cover_index: int = 0  # 候选封面索引


class WmPlatformOverride(BaseModel):
    """Step 5：单个平台水印自定义参数。"""
    platform_id: int
    img_wm_position: Optional[str] = None   # bottom-right / bottom-left / top-right / top-left / center
    img_wm_width: Optional[int] = None       # 水印宽度(px)
    vid_wm_mode: Optional[str] = None        # corner-cycle / fixed / dual-diagonal
    vid_wm_scale: Optional[float] = None     # 视频水印缩放比例(%)


class ConfirmWatermarkRequest(BaseModel):
    """Step 5 确认：可选携带各平台自定义参数。"""
    overrides: List[WmPlatformOverride] = []


class PublishRequest(BaseModel):
    """Step 6：触发发布。"""
    platform_ids: List[int] = []  # 空列表 = 发布全部已就绪


# ── 响应模型 ──

class TaskBrief(BaseModel):
    """任务列表简要信息。"""
    id: int
    task_no: str
    title: str
    folder_path: str
    current_step: int
    status: str
    target_platforms: list
    created_by: int
    created_at: str


class StepState(BaseModel):
    """步骤状态。"""
    step: int
    status: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    data: dict = {}
    error: Optional[str] = None


class PlatformTaskState(BaseModel):
    """平台子任务状态。"""
    platform_id: int
    platform_name: str = ""
    wm_status: str = "pending"
    wm_progress: float = 0
    upload_status: str = "pending"
    upload_progress: float = 0
    transcode_status: str = "pending"
    transcode_progress: float = 0
    publish_status: str = "pending"
    publish_error: Optional[str] = None


class TaskDetail(BaseModel):
    """任务完整详情。"""
    id: int
    task_no: str
    title: str
    folder_path: str
    current_step: int
    status: str
    target_platforms: list
    file_manifest: dict
    # Step 2
    protagonist: str = ""
    confirmed_title: str = ""
    confirmed_keywords: str = ""
    confirmed_body: str = ""
    # Step 3
    rename_prefix: str = ""
    # Step 4
    cover_path: str = ""
    cover_candidates: list = []
    # 步骤和子任务
    steps: List[StepState] = []
    platform_tasks: List[PlatformTaskState] = []
    # 时间
    created_at: str = ""
    updated_at: str = ""
    finished_at: Optional[str] = None
