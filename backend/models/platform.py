"""OmniPublish V2.0 — 平台/业务线数据模型"""

from pydantic import BaseModel, Field
from typing import Optional, List


class PlatformCreate(BaseModel):
    """新增业务线。"""
    name: str = Field(..., min_length=1, max_length=50)
    dept: str = ""
    categories: List[str] = []
    img_wm_position: str = "bottom-right"
    img_wm_width: int = 264
    img_wm_opacity: int = 100
    vid_wm_mode: str = "corner-cycle"
    vid_wm_scale: int = 35
    api_base_url: str = ""
    project_code: str = ""
    layout_template: str = ""


class PlatformUpdate(BaseModel):
    """编辑业务线。"""
    name: Optional[str] = None
    dept: Optional[str] = None
    categories: Optional[List[str]] = None
    img_wm_position: Optional[str] = None
    img_wm_width: Optional[int] = None
    img_wm_opacity: Optional[int] = None
    vid_wm_mode: Optional[str] = None
    vid_wm_scale: Optional[int] = None
    api_base_url: Optional[str] = None
    project_code: Optional[str] = None
    layout_template: Optional[str] = None


class PlatformInfo(BaseModel):
    """平台信息响应。"""
    id: int
    name: str
    dept: str
    categories: list = []
    img_wm_file: str = ""
    img_wm_position: str = "bottom-right"
    img_wm_width: int = 264
    img_wm_opacity: int = 100
    vid_wm_file: str = ""
    vid_wm_mode: str = "corner-cycle"
    vid_wm_scale: int = 35
    api_base_url: str = ""
    project_code: str = ""
    layout_template: str = ""
    is_active: bool = True


class AccountInfo(BaseModel):
    """账号信息（脱敏）。"""
    platform_id: int
    platform_name: str
    api_base_url: str = ""  # 脱敏
    cms_username: str = ""  # 脱敏
    session_active: bool = False
    session_expires: str = ""
