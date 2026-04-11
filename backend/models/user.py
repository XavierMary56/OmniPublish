"""OmniPublish V2.0 — 用户相关数据模型"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class UserRole(str, Enum):
    EDITOR = "editor"
    LEADER = "leader"
    ADMIN = "admin"


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=4, max_length=100)


class LoginResponse(BaseModel):
    code: int = 0
    data: dict = {}
    message: str = ""


class UserInfo(BaseModel):
    id: int
    username: str
    display_name: str
    dept: str
    role: UserRole


class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)
    display_name: str = Field(..., min_length=1, max_length=50)
    dept: str = ""
    role: UserRole = UserRole.EDITOR


class TokenPayload(BaseModel):
    user_id: int
    username: str
    role: str
    exp: float
