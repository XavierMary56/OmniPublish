"""OmniPublish V2.0 — 数据统计路由"""

import json
from fastapi import APIRouter, Depends, Query
from models.common import ApiResponse
from models.user import UserInfo, UserRole
from middleware.auth import get_current_user
from database import get_db

router = APIRouter(prefix="/api/stats", tags=["数据统计"])


@router.get("/overview")
async def overview(
    period: str = Query("today", description="today/week/month"),
    user: UserInfo = Depends(get_current_user),
):
    """总览统计卡片。"""
    db = await get_db()
    try:
        date_filter = _date_filter(period)
        user_filter, user_params = _user_filter(user)

        # 总发帖
        cursor = await db.execute(
            f"SELECT COUNT(*) FROM tasks WHERE {date_filter} {user_filter}",
            user_params,
        )
        total = (await cursor.fetchone())[0]

        # 已完成
        cursor = await db.execute(
            f"SELECT COUNT(*) FROM tasks WHERE status = 'done' AND {date_filter} {user_filter}",
            user_params,
        )
        done = (await cursor.fetchone())[0]

        # 失败
        cursor = await db.execute(
            f"SELECT COUNT(*) FROM tasks WHERE status IN ('failed','partial') AND {date_filter} {user_filter}",
            user_params,
        )
        failed = (await cursor.fetchone())[0]

        # 进行中
        cursor = await db.execute(
            f"SELECT COUNT(*) FROM tasks WHERE status IN ('running','awaiting_confirm','slicing') AND {date_filter} {user_filter}",
            user_params,
        )
        running = (await cursor.fetchone())[0]

        success_rate = round(done / total * 100, 1) if total > 0 else 0

        return ApiResponse.success(data={
            "total": total,
            "done": done,
            "failed": failed,
            "running": running,
            "success_rate": success_rate,
        })
    finally:
        await db.close()


@router.get("/platforms")
async def platform_stats(
    period: str = Query("today"),
    user: UserInfo = Depends(get_current_user),
):
    """各平台发帖统计。"""
    db = await get_db()
    try:
        date_filter = _date_filter(period)
        user_filter, user_params = _user_filter(user)

        cursor = await db.execute(
            f"""SELECT p.name, p.dept,
                COUNT(pt.id) as total,
                SUM(CASE WHEN pt.publish_status = 'published' THEN 1 ELSE 0 END) as success,
                SUM(CASE WHEN pt.publish_status = 'failed' THEN 1 ELSE 0 END) as failed
                FROM platform_tasks pt
                JOIN platforms p ON pt.platform_id = p.id
                JOIN tasks t ON pt.task_id = t.id
                WHERE {date_filter.replace('created_at', 't.created_at')} {user_filter.replace('created_by', 't.created_by')}
                GROUP BY p.id
                ORDER BY total DESC""",
            user_params,
        )
        rows = [dict(r) for r in await cursor.fetchall()]
        return ApiResponse.success(data=rows)
    finally:
        await db.close()


@router.get("/editors")
async def editor_stats(
    period: str = Query("today"),
    user: UserInfo = Depends(get_current_user),
):
    """各编辑发帖排名。"""
    if user.role == UserRole.EDITOR:
        return ApiResponse.error("编辑无权查看排名", code=403)

    db = await get_db()
    try:
        date_filter = _date_filter(period)
        user_filter, user_params = _user_filter(user)

        cursor = await db.execute(
            f"""SELECT u.display_name, u.dept, COUNT(t.id) as total,
                SUM(CASE WHEN t.status = 'done' THEN 1 ELSE 0 END) as done
                FROM tasks t
                JOIN users u ON t.created_by = u.id
                WHERE {date_filter} {user_filter}
                GROUP BY t.created_by
                ORDER BY total DESC""",
            user_params,
        )
        rows = [dict(r) for r in await cursor.fetchall()]
        return ApiResponse.success(data=rows)
    finally:
        await db.close()


@router.get("/pipeline-timing")
async def pipeline_timing(
    period: str = Query("today"),
    user: UserInfo = Depends(get_current_user),
):
    """流水线各步骤平均耗时。"""
    db = await get_db()
    try:
        step_names = ["素材&平台", "文案生成", "图片重命名", "封面制作", "水印处理", "上传&发布"]
        date_filter = _date_filter(period)

        cursor = await db.execute(
            f"""SELECT ts.step,
                AVG(
                    CASE WHEN ts.finished_at IS NOT NULL AND ts.started_at IS NOT NULL
                    THEN (julianday(ts.finished_at) - julianday(ts.started_at)) * 86400
                    ELSE NULL END
                ) as avg_seconds
                FROM task_steps ts
                JOIN tasks t ON ts.task_id = t.id
                WHERE ts.status = 'done' AND {date_filter}
                GROUP BY ts.step
                ORDER BY ts.step"""
        )
        rows = await cursor.fetchall()

        result = []
        for row in rows:
            step = row["step"]
            avg_sec = row["avg_seconds"] or 0
            result.append({
                "step": step,
                "name": step_names[step] if step < len(step_names) else f"Step {step}",
                "avg_seconds": round(avg_sec, 1),
                "avg_minutes": round(avg_sec / 60, 1),
            })

        return ApiResponse.success(data=result)
    finally:
        await db.close()


def _date_filter(period: str) -> str:
    """生成日期过滤 SQL 片段。"""
    if period == "today":
        return "date(created_at) = date('now')"
    elif period == "week":
        return "created_at >= datetime('now', '-7 days')"
    elif period == "month":
        return "created_at >= datetime('now', '-30 days')"
    return "1=1"


def _user_filter(user: UserInfo) -> tuple:
    """生成用户权限过滤。"""
    if user.role == UserRole.EDITOR:
        return "AND created_by = ?", [user.id]
    elif user.role == UserRole.LEADER:
        return "", []  # 组长看全部（简化，后续可加部门过滤）
    return "", []  # 管理员看全部
