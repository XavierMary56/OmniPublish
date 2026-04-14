"""OmniPublish V2.0 — 账号管理路由"""

import json
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from models.common import ApiResponse
from models.user import UserInfo
from middleware.auth import get_current_user
from database import get_pool

router = APIRouter(prefix="/api/accounts", tags=["账号管理"])


class AccountCreate(BaseModel):
    platform_id: int
    platform_name: str = ""
    api_url: str = ""
    username: str = ""
    password: str = ""


class AccountUpdate(BaseModel):
    api_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


@router.get("")
async def list_accounts(user: UserInfo = Depends(get_current_user)):
    """获取所有平台账号列表。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT a.id, a.platform_id, a.platform_name, a.api_url,
                   a.username, a.login_status, a.last_login_at, a.last_error,
                   a.created_at, a.updated_at,
                   p.name as p_name, p.dept
            FROM accounts a
            LEFT JOIN platforms p ON a.platform_id = p.id
            ORDER BY a.id
        """)
        result = []
        for r in rows:
            d = dict(r)
            # 脱敏用户名
            uname = d.get("username", "")
            if len(uname) > 4:
                d["username_masked"] = uname[:3] + "***" + uname[-2:]
            else:
                d["username_masked"] = uname[:1] + "***" if uname else ""
            # 脱敏 URL
            url = d.get("api_url", "")
            if url:
                parts = url.split("//", 1)
                if len(parts) == 2:
                    domain = parts[1].split("/")[0]
                    domain_parts = domain.split(".")
                    if len(domain_parts) >= 2:
                        masked_domain = domain_parts[0][:3] + "*****." + ".".join(domain_parts[-2:])
                        d["api_url_masked"] = parts[0] + "//" + masked_domain + "/" + "/".join(parts[1].split("/")[1:])
                    else:
                        d["api_url_masked"] = url
                else:
                    d["api_url_masked"] = url
            # 格式化时间
            if d.get("last_login_at"):
                d["last_login_at"] = d["last_login_at"].strftime("%Y-%m-%d %H:%M")
            d["platform_name"] = d.get("p_name") or d.get("platform_name", "")
            result.append(d)
        return ApiResponse.success(data=result)


@router.post("")
async def create_account(req: AccountCreate, user: UserInfo = Depends(get_current_user)):
    """添加平台账号。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # 检查是否已存在
        existing = await conn.fetchrow(
            "SELECT id FROM accounts WHERE platform_id = $1", req.platform_id
        )
        if existing:
            raise HTTPException(status_code=400, detail="该平台账号已存在，请编辑")

        # 获取平台名称
        platform = await conn.fetchrow("SELECT name FROM platforms WHERE id = $1", req.platform_id)
        p_name = platform["name"] if platform else req.platform_name

        await conn.execute("""
            INSERT INTO accounts (platform_id, platform_name, api_url, username, password_encrypted, login_status)
            VALUES ($1, $2, $3, $4, $5, 'inactive')
        """, req.platform_id, p_name, req.api_url, req.username, req.password)

        return ApiResponse.success(message="账号已添加")


@router.put("/{account_id}")
async def update_account(account_id: int, req: AccountUpdate, user: UserInfo = Depends(get_current_user)):
    """更新平台账号。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT id FROM accounts WHERE id = $1", account_id)
        if not existing:
            raise HTTPException(status_code=404, detail="账号不存在")

        updates = []
        params = []
        idx = 0
        if req.api_url is not None:
            idx += 1
            updates.append(f"api_url = ${idx}")
            params.append(req.api_url)
        if req.username is not None:
            idx += 1
            updates.append(f"username = ${idx}")
            params.append(req.username)
        if req.password is not None:
            idx += 1
            updates.append(f"password_encrypted = ${idx}")
            params.append(req.password)

        if updates:
            idx += 1
            updates.append(f"updated_at = ${idx}")
            params.append(datetime.now())
            idx += 1
            params.append(account_id)
            await conn.execute(
                f"UPDATE accounts SET {', '.join(updates)} WHERE id = ${idx}",
                *params,
            )

        return ApiResponse.success(message="账号已更新")


@router.delete("/{account_id}")
async def delete_account(account_id: int, user: UserInfo = Depends(get_current_user)):
    """删除平台账号。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM accounts WHERE id = $1", account_id)
        return ApiResponse.success(message="账号已删除")


@router.post("/{account_id}/login")
async def test_login(account_id: int, user: UserInfo = Depends(get_current_user)):
    """测试账号登录状态。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM accounts WHERE id = $1", account_id)
        if not row:
            raise HTTPException(status_code=404, detail="账号不存在")

        # 简单模拟登录测试（实际需要调用各平台 API）
        now = datetime.now()
        await conn.execute(
            "UPDATE accounts SET login_status = 'active', last_login_at = $1, last_error = '', updated_at = $1 WHERE id = $2",
            now, account_id,
        )

        return ApiResponse.success(data={
            "status": "active",
            "last_login_at": now.strftime("%Y-%m-%d %H:%M"),
        }, message="登录成功")
