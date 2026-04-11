"""OmniPublish V2.0 — 任务看板路由"""

import json
from fastapi import APIRouter, HTTPException, Depends, Query
from models.common import ApiResponse, PaginatedResponse
from models.user import UserInfo, UserRole
from middleware.auth import get_current_user
from database import get_db

router = APIRouter(prefix="/api/tasks", tags=["任务看板"])


@router.get("")
async def list_tasks(
    status: str = Query("", description="状态筛选"),
    search: str = Query("", description="搜索关键词"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user: UserInfo = Depends(get_current_user),
):
    """获取任务列表（支持筛选、搜索、分页）。"""
    db = await get_db()
    try:
        conditions = ["1=1"]
        params = []

        # 权限过滤
        if user.role == UserRole.EDITOR:
            conditions.append("t.created_by = ?")
            params.append(user.id)
        elif user.role == UserRole.LEADER:
            # 组长看本组（通过 dept 前缀匹配）
            conditions.append("u.dept LIKE ?")
            params.append(f"{user.dept[:2]}%")  # "1部" 前缀

        # 状态筛选
        if status:
            conditions.append("t.status = ?")
            params.append(status)

        # 搜索
        if search:
            conditions.append("(t.task_no LIKE ? OR t.title LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])

        where = " AND ".join(conditions)

        # 总数
        count_sql = f"""
            SELECT COUNT(*) FROM tasks t
            LEFT JOIN users u ON t.created_by = u.id
            WHERE {where}
        """
        cursor = await db.execute(count_sql, params)
        total = (await cursor.fetchone())[0]

        # 分页查询
        offset = (page - 1) * limit
        query_sql = f"""
            SELECT t.*, u.display_name as editor_name
            FROM tasks t
            LEFT JOIN users u ON t.created_by = u.id
            WHERE {where}
            ORDER BY t.created_at DESC
            LIMIT ? OFFSET ?
        """
        cursor = await db.execute(query_sql, params + [limit, offset])
        rows = await cursor.fetchall()

        items = []
        for row in rows:
            item = dict(row)
            # 解析 JSON 字段
            for field in ["target_platforms", "file_manifest"]:
                if item.get(field):
                    try:
                        item[field] = json.loads(item[field])
                    except (json.JSONDecodeError, TypeError):
                        pass
            items.append(item)

        return ApiResponse.success(data={
            "items": items,
            "total": total,
            "page": page,
            "limit": limit,
        })
    finally:
        await db.close()


@router.get("/{task_id}/logs")
async def get_task_logs(
    task_id: int,
    limit: int = Query(50, ge=1, le=200),
    user: UserInfo = Depends(get_current_user),
):
    """获取任务操作日志。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT tl.*, p.name as platform_name
               FROM task_logs tl
               LEFT JOIN platforms p ON tl.platform_id = p.id
               WHERE tl.task_id = ?
               ORDER BY tl.created_at DESC
               LIMIT ?""",
            (task_id, limit),
        )
        logs = [dict(row) for row in await cursor.fetchall()]
        return ApiResponse.success(data=logs)
    finally:
        await db.close()
