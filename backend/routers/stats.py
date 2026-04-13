"""OmniPublish V2.0 — 数据统计路由"""

import json
from fastapi import APIRouter, Depends, Query
from models.common import ApiResponse
from models.user import UserInfo, UserRole
from middleware.auth import get_current_user
from database import get_pool

router = APIRouter(prefix="/api/stats", tags=["数据统计"])


@router.get("/overview")
async def overview(
    period: str = Query("today", description="today/week/month"),
    user: UserInfo = Depends(get_current_user),
):
    """总览统计卡片。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        date_filter = _date_filter(period)
        user_filter, user_params = _user_filter(user)

        # 总发帖
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM tasks WHERE {date_filter} {user_filter}",
            *user_params,
        )

        # 已完成
        done = await conn.fetchval(
            f"SELECT COUNT(*) FROM tasks WHERE status = 'done' AND {date_filter} {user_filter}",
            *user_params,
        )

        # 失败
        failed = await conn.fetchval(
            f"SELECT COUNT(*) FROM tasks WHERE status IN ('failed','partial') AND {date_filter} {user_filter}",
            *user_params,
        )

        # 进行中
        running = await conn.fetchval(
            f"SELECT COUNT(*) FROM tasks WHERE status IN ('running','awaiting_confirm','slicing') AND {date_filter} {user_filter}",
            *user_params,
        )

        success_rate = round(done / total * 100, 1) if total > 0 else 0

        return ApiResponse.success(data={
            "total": total,
            "done": done,
            "failed": failed,
            "running": running,
            "success_rate": success_rate,
        })


@router.get("/platforms")
async def platform_stats(
    period: str = Query("today"),
    user: UserInfo = Depends(get_current_user),
):
    """各平台发帖统计。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        date_filter = _date_filter(period)
        user_filter, user_params = _user_filter(user)

        rows = await conn.fetch(
            f"""SELECT p.name, p.dept,
                COUNT(pt.id) as total,
                SUM(CASE WHEN pt.publish_status = 'published' THEN 1 ELSE 0 END) as success,
                SUM(CASE WHEN pt.publish_status = 'failed' THEN 1 ELSE 0 END) as failed
                FROM platform_tasks pt
                JOIN platforms p ON pt.platform_id = p.id
                JOIN tasks t ON pt.task_id = t.id
                WHERE {date_filter.replace('created_at', 't.created_at')} {user_filter.replace('created_by', 't.created_by')}
                GROUP BY p.id, p.name, p.dept
                ORDER BY total DESC""",
            *user_params,
        )
        result = [dict(r) for r in rows]
        return ApiResponse.success(data=result)


@router.get("/editors")
async def editor_stats(
    period: str = Query("today"),
    user: UserInfo = Depends(get_current_user),
):
    """各编辑发帖排名。"""
    if user.role == UserRole.EDITOR:
        return ApiResponse.error("编辑无权查看排名", code=403)

    pool = await get_pool()
    async with pool.acquire() as conn:
        date_filter = _date_filter(period)
        user_filter, user_params = _user_filter(user)

        rows = await conn.fetch(
            f"""SELECT u.display_name, u.dept, COUNT(t.id) as total,
                SUM(CASE WHEN t.status = 'done' THEN 1 ELSE 0 END) as done
                FROM tasks t
                JOIN users u ON t.created_by = u.id
                WHERE {date_filter} {user_filter}
                GROUP BY t.created_by, u.display_name, u.dept
                ORDER BY total DESC""",
            *user_params,
        )
        result = [dict(r) for r in rows]
        return ApiResponse.success(data=result)


@router.get("/pipeline-timing")
async def pipeline_timing(
    period: str = Query("today"),
    user: UserInfo = Depends(get_current_user),
):
    """流水线各步骤平均耗时。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        step_names = ["素材&平台", "文案生成", "图片重命名", "封面制作", "水印处理", "上传&发布"]
        date_filter = _date_filter(period)

        rows = await conn.fetch(
            f"""SELECT ts.step,
                AVG(
                    CASE WHEN ts.finished_at IS NOT NULL AND ts.started_at IS NOT NULL
                    THEN EXTRACT(EPOCH FROM (ts.finished_at - ts.started_at))
                    ELSE NULL END
                ) as avg_seconds
                FROM task_steps ts
                JOIN tasks t ON ts.task_id = t.id
                WHERE ts.status = 'done' AND {date_filter}
                GROUP BY ts.step
                ORDER BY ts.step"""
        )

        result = []
        for row in rows:
            step = row["step"]
            avg_sec = row["avg_seconds"] or 0
            result.append({
                "step": step,
                "name": step_names[step] if step < len(step_names) else f"Step {step}",
                "avg_seconds": round(float(avg_sec), 1),
                "avg_minutes": round(float(avg_sec) / 60, 1),
            })

        return ApiResponse.success(data=result)


def _date_filter(period: str) -> str:
    """生成日期过滤 SQL 片段。"""
    if period == "today":
        return "created_at::date = CURRENT_DATE"
    elif period == "week":
        return "created_at >= CURRENT_TIMESTAMP - INTERVAL '7 days'"
    elif period == "month":
        return "created_at >= CURRENT_TIMESTAMP - INTERVAL '30 days'"
    return "1=1"


def _user_filter(user: UserInfo) -> tuple:
    """生成用户权限过滤。"""
    if user.role == UserRole.EDITOR:
        return "AND created_by = $1", [user.id]
    elif user.role == UserRole.LEADER:
        # 组长看本组（通过 dept 前缀匹配，与 tasks.py 保持一致）
        return "AND created_by IN (SELECT id FROM users WHERE dept LIKE $1)", [f"{user.dept[:2]}%"]
    return "", []  # 管理员看全部


# ══════════════════════════════════════
# 数据库管理（仅管理员）
# ══════════════════════════════════════

@router.get("/db-stats")
async def db_stats(user: UserInfo = Depends(get_current_user)):
    """数据库统计信息（管理员可查看）。"""
    if user.role != UserRole.ADMIN:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="仅管理员可查看")

    from database import get_db_stats
    stats = await get_db_stats()
    return ApiResponse.success(data=stats)


@router.post("/db-cleanup")
async def db_cleanup(
    days: int = Query(30, description="保留最近 N 天的日志"),
    user: UserInfo = Depends(get_current_user),
):
    """手动清理过期日志（管理员操作）。"""
    if user.role != UserRole.ADMIN:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="仅管理员可操作")

    from database import cleanup_old_logs
    pool = await get_pool()
    async with pool.acquire() as conn:
        deleted = await cleanup_old_logs(conn, days)
        return ApiResponse.success(data={"deleted": deleted, "days_kept": days})
