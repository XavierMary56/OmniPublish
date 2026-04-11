"""OmniPublish V2.0 — 通用响应模型"""

from pydantic import BaseModel
from typing import Any, Optional


class ApiResponse(BaseModel):
    """统一 API 响应格式。"""
    code: int = 0
    data: Any = None
    message: str = ""

    @classmethod
    def success(cls, data: Any = None, message: str = "ok"):
        return cls(code=0, data=data, message=message)

    @classmethod
    def error(cls, message: str, code: int = 400):
        return cls(code=code, data=None, message=message)


class PaginatedResponse(BaseModel):
    """分页响应。"""
    items: list = []
    total: int = 0
    page: int = 1
    limit: int = 20
