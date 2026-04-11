"""OmniPublish V2.0 — 认证路由"""

from fastapi import APIRouter, HTTPException, Depends
from models.user import LoginRequest, UserInfo, UserCreate, UserRole
from models.common import ApiResponse
from middleware.auth import (
    verify_password, hash_password, create_token,
    get_current_user, require_role,
)
from database import get_db

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/login")
async def login(req: LoginRequest):
    """用户登录，返回 JWT token。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, username, password, display_name, dept, role FROM users WHERE username = ? AND is_active = 1",
            (req.username,),
        )
        user = await cursor.fetchone()
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
    finally:
        await db.close()


@router.get("/me")
async def get_me(user: UserInfo = Depends(get_current_user)):
    """获取当前登录用户信息。"""
    return ApiResponse.success(data=user.model_dump())


@router.post("/users", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def create_user(req: UserCreate):
    """创建新用户（仅管理员）。"""
    db = await get_db()
    try:
        hashed = hash_password(req.password)
        await db.execute(
            "INSERT INTO users (username, password, display_name, dept, role) VALUES (?, ?, ?, ?, ?)",
            (req.username, hashed, req.display_name, req.dept, req.role.value),
        )
        await db.commit()
        return ApiResponse.success(message=f"用户 {req.username} 创建成功")
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(status_code=409, detail=f"用户名 {req.username} 已存在")
        raise
    finally:
        await db.close()


@router.get("/users", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def list_users():
    """获取用户列表（仅管理员）。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, username, display_name, dept, role, is_active, created_at FROM users ORDER BY id"
        )
        rows = await cursor.fetchall()
        users = [dict(row) for row in rows]
        return ApiResponse.success(data=users)
    finally:
        await db.close()
