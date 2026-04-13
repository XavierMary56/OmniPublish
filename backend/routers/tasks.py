"""OmniPublish V2.0 — 任务看板路由"""

import json
from fastapi import APIRouter, HTTPException, Depends, Query
from models.common import ApiResponse, PaginatedResponse
from models.user import UserInfo, UserRole
from middleware.auth import get_current_user
from database import get_pool

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
    pool = await get_pool()
    async with pool.acquire() as conn:
        conditions = ["1=1"]
        params = []
        param_idx = 0

        # 权限过滤
        if user.role == UserRole.EDITOR:
            param_idx += 1
            conditions.append(f"t.created_by = ${param_idx}")
            params.append(user.id)
        elif user.role == UserRole.LEADER:
            # 组长看本组（通过 dept 前缀匹配）
            param_idx += 1
            conditions.append(f"u.dept LIKE ${param_idx}")
            params.append(f"{user.dept[:2]}%")  # "1部" 前缀

        # 状态筛选
        if status:
            param_idx += 1
            conditions.append(f"t.status = ${param_idx}")
            params.append(status)

        # 搜索
        if search:
            param_idx += 1
            search_param1 = param_idx
            param_idx += 1
            search_param2 = param_idx
            conditions.append(f"(t.task_no LIKE ${search_param1} OR t.title LIKE ${search_param2})")
            params.extend([f"%{search}%", f"%{search}%"])

        where = " AND ".join(conditions)

        # 总数
        count_sql = f"""
            SELECT COUNT(*) FROM tasks t
            LEFT JOIN users u ON t.created_by = u.id
            WHERE {where}
        """
        total = await conn.fetchval(count_sql, *params)

        # 分页查询
        offset = (page - 1) * limit
        param_idx += 1
        limit_param = param_idx
        param_idx += 1
        offset_param = param_idx
        query_sql = f"""
            SELECT t.*, u.display_name as editor_name
            FROM tasks t
            LEFT JOIN users u ON t.created_by = u.id
            WHERE {where}
            ORDER BY t.created_at DESC
            LIMIT ${limit_param} OFFSET ${offset_param}
        """
        rows = await conn.fetch(query_sql, *params, limit, offset)

        items = []
        for row in rows:
            item = dict(row)
            item['created_by'] = item.get('editor_name') or item.get('created_by', '')
            # 解析 JSON 字段
            for field in ["target_platforms", "file_manifest"]:
                if item.get(field):
                    try:
                        item[field] = json.loads(item[field])
                    except (json.JSONDecodeError, TypeError):
                        pass

            # 加载步骤状态
            step_rows = await conn.fetch(
                "SELECT step, status FROM task_steps WHERE task_id = $1 ORDER BY step",
                item["id"],
            )
            item["steps"] = [dict(s) for s in step_rows]

            # 加载平台子任务
            pt_rows = await conn.fetch(
                """SELECT pt.platform_id, p.name as platform_name,
                          pt.wm_status, pt.upload_status, pt.publish_status, pt.publish_error
                   FROM platform_tasks pt
                   JOIN platforms p ON pt.platform_id = p.id
                   WHERE pt.task_id = $1""",
                item["id"],
            )
            item["platform_tasks"] = [dict(pt) for pt in pt_rows]

            items.append(item)

        return ApiResponse.success(data={
            "items": items,
            "total": total,
            "page": page,
            "limit": limit,
        })


@router.get("/{task_id}/logs")
async def get_task_logs(
    task_id: int,
    limit: int = Query(50, ge=1, le=200),
    user: UserInfo = Depends(get_current_user),
):
    """获取任务操作日志。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT tl.*, p.name as platform_name
               FROM task_logs tl
               LEFT JOIN platforms p ON tl.platform_id = p.id
               WHERE tl.task_id = $1
               ORDER BY tl.created_at DESC
               LIMIT $2""",
            task_id, limit,
        )
        logs = [dict(row) for row in rows]
        return ApiResponse.success(data=logs)
