"""OmniPublish V2.0 — JWT 认证中间件"""

import time
from typing import Optional

import jwt
from passlib.context import CryptContext
from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config import settings
from models.user import UserInfo, UserRole

# 密码哈希
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT 配置
JWT_SECRET = settings.server.auth_secret
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = settings.server.token_expire_hours

# Bearer token 提取
security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """哈希密码。"""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """验证密码。"""
    return pwd_context.verify(plain, hashed)


def create_token(user_id: int, username: str, role: str) -> str:
    """创建 JWT token。"""
    payload = {
        "user_id": user_id,
        "username": username,
        "role": role,
        "exp": time.time() + JWT_EXPIRE_HOURS * 3600,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """解码 JWT token。"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("exp", 0) < time.time():
            raise HTTPException(status_code=401, detail="Token 已过期")
        return payload
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效的 Token")


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> UserInfo:
    """从请求头提取并验证 JWT，返回当前用户信息。"""
    if not credentials:
        raise HTTPException(status_code=401, detail="未提供认证 Token")

    payload = decode_token(credentials.credentials)
    return UserInfo(
        id=payload["user_id"],
        username=payload["username"],
        display_name=payload.get("display_name", payload["username"]),
        dept=payload.get("dept", ""),
        role=UserRole(payload["role"]),
    )


def require_role(*roles: UserRole):
    """角色权限校验依赖。用法: Depends(require_role(UserRole.ADMIN))"""
    async def checker(user: UserInfo = Depends(get_current_user)) -> UserInfo:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail=f"权限不足，需要角色: {[r.value for r in roles]}")
        return user
    return checker
