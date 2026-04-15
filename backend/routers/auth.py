"""OmniPublish V2.0 — 认证路由"""

import sqlite3
from fastapi import APIRouter, HTTPException, Depends
from models.user import LoginRequest, UserInfo, UserCreate, UserRole
from models.common import ApiResponse
from middleware.auth import (
    verify_password, hash_password, create_token,
    get_current_user, require_role,
)
from database import get_pool

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/login")
async def login(req: LoginRequest):
    """用户登录，返回 JWT token。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT id, username, password, display_name, dept, role FROM users WHERE username = $1 AND is_active = 1",
            req.username,
        )
        if not user:
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        if not verify_password(req.password, user["password"]):
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        token = create_token(
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
        )

        return ApiResponse.success(data={
            "token": token,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "display_name": user["display_name"],
                "dept": user["dept"],
                "role": user["role"],
            },
        })


@router.get("/me")
async def get_me(user: UserInfo = Depends(get_current_user)):
    """获取当前登录用户信息。"""
    return ApiResponse.success(data=user.model_dump())


@router.post("/users", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def create_user(req: UserCreate):
    """创建新用户（仅管理员）。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            hashed = hash_password(req.password)
            await conn.execute(
                "INSERT INTO users (username, password, display_name, dept, role) VALUES ($1, $2, $3, $4, $5)",
                req.username, hashed, req.display_name, req.dept, req.role.value,
            )
            return ApiResponse.success(message=f"用户 {req.username} 创建成功")
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail=f"用户名 {req.username} 已存在")


@router.get("/users", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def list_users():
    """获取用户列表（仅管理员）。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, username, display_name, dept, role, is_active, created_at FROM users ORDER BY id"
        )
        users = [dict(row) for row in rows]
        return ApiResponse.success(data=users)
