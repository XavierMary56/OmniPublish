"""OmniPublish V2.0 — 业务线管理路由"""

import json
import os
import shutil
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query
from models.platform import PlatformCreate, PlatformUpdate, PlatformInfo
from models.common import ApiResponse
from models.user import UserInfo, UserRole
from middleware.auth import get_current_user, require_role
from database import get_db
from config import UPLOADS_DIR

router = APIRouter(prefix="/api/platforms", tags=["业务线管理"])

WM_DIR = UPLOADS_DIR / "watermarks"


@router.get("")
async def list_platforms(
    dept: str = Query("", description="部组筛选"),
    user: UserInfo = Depends(get_current_user),
):
    """获取平台列表。"""
    db = await get_db()
    try:
        if dept:
            cursor = await db.execute(
                "SELECT * FROM platforms WHERE dept LIKE ? AND is_active = 1 ORDER BY dept, name",
                (f"{dept}%",),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM platforms WHERE is_active = 1 ORDER BY dept, name"
            )
        rows = await cursor.fetchall()

        platforms = []
        for row in rows:
            p = dict(row)
            p["categories"] = json.loads(p.get("categories") or "[]")
            platforms.append(p)

        return ApiResponse.success(data=platforms)
    finally:
        await db.close()


@router.post("", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def create_platform(req: PlatformCreate):
    """新增业务线（仅管理员）。"""
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO platforms (name, dept, categories, img_wm_position, img_wm_width,
               img_wm_opacity, vid_wm_mode, vid_wm_scale, api_base_url, project_code, layout_template)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (req.name, req.dept, json.dumps(req.categories),
             req.img_wm_position, req.img_wm_width, req.img_wm_opacity,
             req.vid_wm_mode, req.vid_wm_scale,
             req.api_base_url, req.project_code, req.layout_template),
        )
        await db.commit()
        return ApiResponse.success(message=f"业务线 {req.name} 创建成功")
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(status_code=409, detail=f"业务线 {req.name} 已存在")
        raise
    finally:
        await db.close()


@router.put("/{platform_id}", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def update_platform(platform_id: int, req: PlatformUpdate):
    """编辑业务线（仅管理员）。"""
    db = await get_db()
    try:
        updates = []
        params = []
        req_dict = req.model_dump(exclude_none=True)
        for key, value in req_dict.items():
            if key == "categories":
                updates.append("categories = ?")
                params.append(json.dumps(value))
            else:
                updates.append(f"{key} = ?")
                params.append(value)

        if not updates:
            return ApiResponse.error("没有需要更新的字段")

        updates.append("updated_at = datetime('now')")
        params.append(platform_id)

        await db.execute(
            f"UPDATE platforms SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        await db.commit()
        return ApiResponse.success(message="更新成功")
    finally:
        await db.close()


@router.delete("/{platform_id}", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def delete_platform(platform_id: int):
    """删除业务线（软删除，仅管理员）。"""
    db = await get_db()
    try:
        await db.execute(
            "UPDATE platforms SET is_active = 0, updated_at = datetime('now') WHERE id = ?",
            (platform_id,),
        )
        await db.commit()
        return ApiResponse.success(message="已删除")
    finally:
        await db.close()


@router.post("/{platform_id}/watermark/image", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def upload_image_watermark(platform_id: int, file: UploadFile = File(...)):
    """上传图片水印文件。"""
    if not file.filename.lower().endswith((".png", ".jpg", ".jpeg")):
        raise HTTPException(status_code=400, detail="仅支持 PNG/JPG 格式")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件不能超过 10MB")

    # 保存到 uploads/watermarks/{platform_id}_img.png
    ext = Path(file.filename).suffix.lower()
    save_name = f"{platform_id}_img{ext}"
    save_path = WM_DIR / save_name
    with open(save_path, "wb") as f:
        f.write(content)

    # 更新数据库
    db = await get_db()
    try:
        await db.execute(
            "UPDATE platforms SET img_wm_file = ?, updated_at = datetime('now') WHERE id = ?",
            (str(save_path), platform_id),
        )
        await db.commit()
        return ApiResponse.success(data={
            "file": save_name,
            "size": len(content),
            "path": str(save_path),
        })
    finally:
        await db.close()


@router.post("/{platform_id}/watermark/video", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def upload_video_watermark(platform_id: int, file: UploadFile = File(...)):
    """上传视频水印文件。"""
    if not file.filename.lower().endswith((".mov", ".png", ".mp4")):
        raise HTTPException(status_code=400, detail="仅支持 MOV/PNG/MP4 格式")

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件不能超过 50MB")

    ext = Path(file.filename).suffix.lower()
    save_name = f"{platform_id}_vid{ext}"
    save_path = WM_DIR / save_name
    with open(save_path, "wb") as f:
        f.write(content)

    db = await get_db()
    try:
        await db.execute(
            "UPDATE platforms SET vid_wm_file = ?, updated_at = datetime('now') WHERE id = ?",
            (str(save_path), platform_id),
        )
        await db.commit()
        return ApiResponse.success(data={
            "file": save_name,
            "size": len(content),
            "path": str(save_path),
        })
    finally:
        await db.close()


@router.post("/{platform_id}/categories/import", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def import_categories(platform_id: int, file: UploadFile = File(...)):
    """批量导入分类库（CSV/TXT，一行一个）。"""
    content = (await file.read()).decode("utf-8")
    categories = [line.strip() for line in content.replace(",", "\n").split("\n") if line.strip()]
    categories = list(dict.fromkeys(categories))  # 去重保序

    db = await get_db()
    try:
        await db.execute(
            "UPDATE platforms SET categories = ?, updated_at = datetime('now') WHERE id = ?",
            (json.dumps(categories), platform_id),
        )
        await db.commit()
        return ApiResponse.success(data={
            "imported": len(categories),
            "categories": categories,
        })
    finally:
        await db.close()
