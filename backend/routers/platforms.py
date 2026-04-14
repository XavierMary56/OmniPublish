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
from database import get_pool
from config import UPLOADS_DIR

router = APIRouter(prefix="/api/platforms", tags=["业务线管理"])

WM_DIR = UPLOADS_DIR / "watermarks"
WM_DIR.mkdir(parents=True, exist_ok=True)


@router.get("")
async def list_platforms(
    dept: str = Query("", description="部组筛选"),
    user: UserInfo = Depends(get_current_user),
):
    """获取平台列表。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if dept:
            rows = await conn.fetch(
                "SELECT * FROM platforms WHERE dept LIKE $1 AND is_active = 1 ORDER BY dept, name",
                f"{dept}%",
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM platforms WHERE is_active = 1 ORDER BY dept, name"
            )

        platforms = []
        for row in rows:
            p = dict(row)
            p["categories"] = json.loads(p.get("categories") or "[]")
            platforms.append(p)

        return ApiResponse.success(data=platforms)


@router.post("", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def create_platform(req: PlatformCreate):
    """新增业务线（仅管理员）。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                """INSERT INTO platforms (name, dept, categories, img_wm_position, img_wm_width,
                   img_wm_opacity, vid_wm_mode, vid_wm_scale, api_base_url, project_code, layout_template)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)""",
                req.name, req.dept, json.dumps(req.categories),
                req.img_wm_position, req.img_wm_width, req.img_wm_opacity,
                req.vid_wm_mode, req.vid_wm_scale,
                req.api_base_url, req.project_code, req.layout_template,
            )
            return ApiResponse.success(message=f"业务线 {req.name} 创建成功")
        except Exception as e:
            if "unique" in str(e).lower() or "duplicate" in str(e).lower():
                raise HTTPException(status_code=409, detail=f"业务线 {req.name} 已存在")
            raise


@router.put("/{platform_id}", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def update_platform(platform_id: int, req: PlatformUpdate):
    """编辑业务线（仅管理员）。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        updates = []
        params = []
        param_idx = 0
        req_dict = req.model_dump(exclude_none=True)
        for key, value in req_dict.items():
            param_idx += 1
            if key == "categories":
                updates.append(f"categories = ${param_idx}")
                params.append(json.dumps(value))
            else:
                updates.append(f"{key} = ${param_idx}")
                params.append(value)

        if not updates:
            return ApiResponse.error("没有需要更新的字段")

        updates.append("updated_at = CURRENT_TIMESTAMP")
        param_idx += 1
        params.append(platform_id)

        await conn.execute(
            f"UPDATE platforms SET {', '.join(updates)} WHERE id = ${param_idx}",
            *params,
        )
        return ApiResponse.success(message="更新成功")


@router.delete("/{platform_id}", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def delete_platform(platform_id: int):
    """删除业务线（软删除，仅管理员）。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE platforms SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE id = $1",
            platform_id,
        )
        return ApiResponse.success(message="已删除")


@router.post("/{platform_id}/watermark/image", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def upload_image_watermark(platform_id: int, file: UploadFile = File(...)):
    """上传图片水印文件。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")
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
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE platforms SET img_wm_file = $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2",
            str(save_path), platform_id,
        )
        return ApiResponse.success(data={
            "file": save_name,
            "size": len(content),
            "path": str(save_path),
        })


@router.post("/{platform_id}/watermark/video", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def upload_video_watermark(platform_id: int, file: UploadFile = File(...)):
    """上传视频水印文件。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")
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

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE platforms SET vid_wm_file = $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2",
            str(save_path), platform_id,
        )
        return ApiResponse.success(data={
            "file": save_name,
            "size": len(content),
            "path": str(save_path),
        })


@router.post("/{platform_id}/categories/import", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def import_categories(platform_id: int, file: UploadFile = File(...)):
    """批量导入分类库（CSV/TXT，一行一个）。"""
    content = (await file.read()).decode("utf-8")
    categories = [line.strip() for line in content.replace(",", "\n").split("\n") if line.strip()]
    categories = list(dict.fromkeys(categories))  # 去重保序

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE platforms SET categories = $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2",
            json.dumps(categories), platform_id,
        )
        return ApiResponse.success(data={
            "imported": len(categories),
            "categories": categories,
        })


# ══════════════════════════════════════════
# 水印文件上传
# ══════════════════════════════════════════

@router.post("/upload-watermark")
async def upload_watermark(
    file: UploadFile = File(...),
    type: str = Query(default="img"),
    user: UserInfo = Depends(get_current_user),
):
    """上传水印文件（图片 PNG 或视频 MOV），返回存储路径。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名为空")

    ext = os.path.splitext(file.filename)[1].lower()
    allowed = {".png"} if type == "img" else {".png", ".mov"}
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}，允许: {', '.join(allowed)}")

    # 安全文件名
    safe_name = os.path.basename(file.filename)
    dest = WM_DIR / safe_name

    # 如果同名文件已存在，加序号
    counter = 1
    while dest.exists():
        name_only = os.path.splitext(safe_name)[0]
        dest = WM_DIR / f"{name_only}_{counter}{ext}"
        counter += 1

    # 写入文件
    content = await file.read()
    with open(dest, "wb") as fp:
        fp.write(content)

    # 获取文件信息
    file_size = len(content)
    rel_path = str(dest.relative_to(UPLOADS_DIR))

    result = {
        "path": str(dest),
        "rel_path": rel_path,
        "filename": dest.name,
        "size": file_size,
        "size_kb": round(file_size / 1024, 1),
    }

    # 图片水印返回预览 URL
    if type == "img" and ext == ".png":
        result["preview_url"] = f"/uploads/watermarks/{dest.name}"

        # 尝试获取图片尺寸
        try:
            from PIL import Image
            img = Image.open(dest)
            result["width"] = img.width
            result["height"] = img.height
            result["dimensions"] = f"{img.width}×{img.height}px"
        except Exception:
            pass

    return ApiResponse.success(data=result)
