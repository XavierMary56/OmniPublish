"""OmniPublish V2.0 — 流水线路由（核心）"""

import asyncio
import json
import os
import shutil
import uuid
from typing import List
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, UploadFile, File
from models.task import (
    CreateTaskRequest, GenerateCopyRequest, ConfirmCopyRequest,
    ConfirmRenameRequest, ConfirmCoverRequest, PublishRequest,
)
from models.common import ApiResponse
from models.user import UserInfo
from middleware.auth import get_current_user
from database import get_pool, get_next_task_no
from services.pipeline_service import pipeline_service
from services.copywrite_service import copywrite_service
from services.rename_service import rename_service
from services.cover_service import cover_service
from services.watermark_service import watermark_service
from services.publish_service import publish_service
from config import BACKEND_DIR

router = APIRouter(prefix="/api/pipeline", tags=["流水线"])

# 上传文件存储根目录
UPLOAD_ROOT = os.path.join(BACKEND_DIR, "uploads", "tasks")
os.makedirs(UPLOAD_ROOT, exist_ok=True)


# ══════════════════════════════════════════
# 文件上传接口
# ══════════════════════════════════════════

@router.post("/upload")
async def upload_files(
    files: List[UploadFile] = File(...),
    user: UserInfo = Depends(get_current_user),
):
    """上传素材文件，返回服务端文件夹路径和文件识别结果。"""
    if not files:
        raise HTTPException(status_code=400, detail="未选择任何文件")

    # 创建唯一目录
    folder_id = uuid.uuid4().hex[:12]
    folder_path = os.path.join(UPLOAD_ROOT, folder_id)
    os.makedirs(folder_path, exist_ok=True)

    saved_files = []
    total_size = 0
    for f in files:
        # 安全处理文件名（保留原名，去掉路径分隔符）
        raw_name = f.filename or "unknown"
        # 修复中文文件名编码问题
        safe_name = _fix_filename_encoding(raw_name)
        safe_name = os.path.basename(safe_name)
        # 过滤危险字符
        safe_name = safe_name.replace('..', '_').replace('/', '_').replace('\\', '_')
        dest_path = os.path.join(folder_path, safe_name)

        # 写入文件
        content = await f.read()
        total_size += len(content)
        with open(dest_path, "wb") as fp:
            fp.write(content)
        saved_files.append(safe_name)

    # 自动扫描识别
    manifest = _scan_folder(folder_path)

    return ApiResponse.success(data={
        "folder_path": folder_path,
        "folder_id": folder_id,
        "total_files": len(saved_files),
        "total_size_mb": round(total_size / 1024 / 1024, 2),
        "file_manifest": manifest,
    })


# ══════════════════════════════════════════
# 分片断点续传
# ══════════════════════════════════════════

@router.post("/upload/init")
async def init_chunked_upload(
    filename: str,
    total_size: int,
    total_chunks: int,
    folder_id: str = "",
    user: UserInfo = Depends(get_current_user),
):
    """初始化分片上传：返回 upload_id 和 folder_id。"""
    if not folder_id:
        folder_id = uuid.uuid4().hex[:12]
    folder_path = os.path.join(UPLOAD_ROOT, folder_id)
    os.makedirs(folder_path, exist_ok=True)

    # 修复中文文件名
    try:
        filename = filename.encode('latin-1').decode('utf-8')
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass

    upload_id = uuid.uuid4().hex[:16]
    chunks_dir = os.path.join(UPLOAD_ROOT, f".chunks_{upload_id}")
    os.makedirs(chunks_dir, exist_ok=True)

    # 记录上传元数据
    meta = {
        "upload_id": upload_id,
        "folder_id": folder_id,
        "folder_path": folder_path,
        "filename": filename,
        "total_size": total_size,
        "total_chunks": total_chunks,
        "uploaded_chunks": [],
    }
    with open(os.path.join(chunks_dir, "_meta.json"), "w", encoding="utf-8") as fp:
        json.dump(meta, fp, ensure_ascii=False)

    return ApiResponse.success(data={
        "upload_id": upload_id,
        "folder_id": folder_id,
        "uploaded_chunks": [],
    })


@router.post("/upload/chunk")
async def upload_chunk(
    upload_id: str,
    chunk_index: int,
    chunk: UploadFile = File(...),
    user: UserInfo = Depends(get_current_user),
):
    """上传单个分片。"""
    chunks_dir = os.path.join(UPLOAD_ROOT, f".chunks_{upload_id}")
    meta_path = os.path.join(chunks_dir, "_meta.json")
    if not os.path.exists(meta_path):
        raise HTTPException(status_code=404, detail=f"上传会话不存在: {upload_id}")

    # 保存分片
    chunk_path = os.path.join(chunks_dir, f"chunk_{chunk_index:05d}")
    content = await chunk.read()
    with open(chunk_path, "wb") as fp:
        fp.write(content)

    # 更新元数据
    with open(meta_path, "r", encoding="utf-8") as fp:
        meta = json.load(fp)
    if chunk_index not in meta["uploaded_chunks"]:
        meta["uploaded_chunks"].append(chunk_index)
        meta["uploaded_chunks"].sort()
    with open(meta_path, "w", encoding="utf-8") as fp:
        json.dump(meta, fp, ensure_ascii=False)

    return ApiResponse.success(data={
        "chunk_index": chunk_index,
        "uploaded": len(meta["uploaded_chunks"]),
        "total": meta["total_chunks"],
    })


@router.post("/upload/complete")
async def complete_chunked_upload(
    upload_id: str,
    user: UserInfo = Depends(get_current_user),
):
    """合并分片，完成上传。"""
    chunks_dir = os.path.join(UPLOAD_ROOT, f".chunks_{upload_id}")
    meta_path = os.path.join(chunks_dir, "_meta.json")
    if not os.path.exists(meta_path):
        raise HTTPException(status_code=404, detail=f"上传会话不存在: {upload_id}")

    with open(meta_path, "r", encoding="utf-8") as fp:
        meta = json.load(fp)

    # 检查是否所有分片都已上传
    if len(meta["uploaded_chunks"]) < meta["total_chunks"]:
        missing = [i for i in range(meta["total_chunks"]) if i not in meta["uploaded_chunks"]]
        raise HTTPException(status_code=400, detail=f"缺少分片: {missing[:10]}")

    # 合并分片到目标文件
    safe_name = os.path.basename(meta["filename"])
    dest_path = os.path.join(meta["folder_path"], safe_name)
    with open(dest_path, "wb") as out_fp:
        for i in range(meta["total_chunks"]):
            chunk_path = os.path.join(chunks_dir, f"chunk_{i:05d}")
            with open(chunk_path, "rb") as cp:
                out_fp.write(cp.read())

    # 清理分片目录
    shutil.rmtree(chunks_dir, ignore_errors=True)

    # 扫描文件夹
    manifest = _scan_folder(meta["folder_path"])

    return ApiResponse.success(data={
        "folder_path": meta["folder_path"],
        "folder_id": meta["folder_id"],
        "filename": safe_name,
        "file_manifest": manifest,
    })


@router.get("/upload/status/{upload_id}")
async def get_upload_status(
    upload_id: str,
    user: UserInfo = Depends(get_current_user),
):
    """查询分片上传进度（断点续传时恢复已上传的分片列表）。"""
    chunks_dir = os.path.join(UPLOAD_ROOT, f".chunks_{upload_id}")
    meta_path = os.path.join(chunks_dir, "_meta.json")
    if not os.path.exists(meta_path):
        raise HTTPException(status_code=404, detail="上传会话不存在")

    with open(meta_path, "r", encoding="utf-8") as fp:
        meta = json.load(fp)

    return ApiResponse.success(data={
        "upload_id": upload_id,
        "folder_id": meta["folder_id"],
        "filename": meta["filename"],
        "total_chunks": meta["total_chunks"],
        "uploaded_chunks": meta["uploaded_chunks"],
        "progress": round(len(meta["uploaded_chunks"]) / meta["total_chunks"] * 100, 1) if meta["total_chunks"] > 0 else 0,
    })


# ══════════════════════════════════════════
# Step 1: 创建任务
# ══════════════════════════════════════════

@router.post("")
async def create_task(req: CreateTaskRequest, user: UserInfo = Depends(get_current_user)):
    """Step 1 提交：创建发帖任务。"""
    if not os.path.isdir(req.folder_path):
        raise HTTPException(status_code=400, detail=f"文件夹不存在: {req.folder_path}")

    manifest = _scan_folder(req.folder_path)
    if not manifest["images"] and not manifest["videos"]:
        raise HTTPException(status_code=400, detail="文件夹中未找到图片或视频文件")

    task_no = await get_next_task_no()

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            task_id = await conn.fetchval(
                """INSERT INTO tasks (task_no, folder_path, created_by, target_platforms, file_manifest, status, current_step)
                   VALUES ($1, $2, $3, $4, $5, 'running', 1) RETURNING id""",
                task_no, req.folder_path, user.id,
                json.dumps(req.target_platforms), json.dumps(manifest),
            )

            for step in range(6):
                status = "done" if step == 0 else ("awaiting_confirm" if step == 1 else "pending")
                await conn.execute(
                    "INSERT INTO task_steps (task_id, step, status) VALUES ($1, $2, $3)",
                    task_id, step, status,
                )
            for pid in req.target_platforms:
                await conn.execute(
                    "INSERT INTO platform_tasks (task_id, platform_id) VALUES ($1, $2)",
                    task_id, pid,
                )

    await pipeline_service.add_log(task_id, f"任务创建: {len(req.target_platforms)} 个平台", step=0)

    return ApiResponse.success(data={
        "task_id": task_id,
        "task_no": task_no,
        "file_manifest": manifest,
    })


@router.post("/{task_id}/scan-folder")
async def scan_folder(task_id: int, user: UserInfo = Depends(get_current_user)):
    """扫描素材文件夹。"""
    task = await pipeline_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return ApiResponse.success(data=_scan_folder(task["folder_path"]))


@router.get("/{task_id}")
async def get_task(task_id: int, user: UserInfo = Depends(get_current_user)):
    """获取任务完整详情。"""
    task = await pipeline_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if user.role == "editor" and task["created_by"] != user.id:
        raise HTTPException(status_code=403, detail="无权查看此任务")

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM task_steps WHERE task_id = $1 ORDER BY step", task_id,
        )
        task["steps"] = [dict(r) for r in rows]

        rows = await conn.fetch(
            """SELECT pt.*, p.name as platform_name FROM platform_tasks pt
               JOIN platforms p ON pt.platform_id = p.id WHERE pt.task_id = $1""",
            task_id,
        )
        task["platform_tasks"] = [dict(r) for r in rows]

    return ApiResponse.success(data=task)


# ══════════════════════════════════════════
# Step 2: 文案生成
# ══════════════════════════════════════════

@router.get("/{task_id}/step/2/categories")
async def get_dynamic_categories(task_id: int, user: UserInfo = Depends(get_current_user)):
    """根据已选平台动态加载分类库并集。"""
    task = await pipeline_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    platform_ids = task.get("target_platforms", [])
    if not platform_ids:
        return ApiResponse.success(data={"categories": []})

    pool = await get_pool()
    async with pool.acquire() as conn:
        placeholders = ",".join(f"${i+1}" for i in range(len(platform_ids)))
        rows = await conn.fetch(
            f"SELECT id, name, categories FROM platforms WHERE id IN ({placeholders})",
            *platform_ids,
        )
        all_cats = set()
        count_with = 0
        for row in rows:
            cats = json.loads(row["categories"] or "[]")
            if cats:
                count_with += 1
                all_cats.update(cats)

        return ApiResponse.success(data={
            "categories": sorted(all_cats),
            "platforms_with_categories": count_with,
            "total_platforms": len(platform_ids),
        })


@router.post("/{task_id}/step/2/generate")
async def generate_copy(task_id: int, req: GenerateCopyRequest,
                        bg: BackgroundTasks, user: UserInfo = Depends(get_current_user)):
    """触发 AI 文案生成（后台异步执行）。"""
    task = await pipeline_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 保存输入参数到任务
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE tasks SET protagonist = $1, event_desc = $2, style = $3,
               author = $4, categories = $5, updated_at = CURRENT_TIMESTAMP WHERE id = $6""",
            req.protagonist, req.event, req.style, req.author,
            json.dumps(req.categories), task_id,
        )

    # 后台异步生成
    bg.add_task(copywrite_service.generate, task_id, req.model_dump())

    return ApiResponse.success(message="文案生成已启动，请通过 WebSocket 监听进度")


@router.put("/{task_id}/step/2/confirm")
async def confirm_copy(task_id: int, req: ConfirmCopyRequest, user: UserInfo = Depends(get_current_user)):
    """确认文案，推进到 Step 3。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE tasks SET confirmed_title = $1, confirmed_keywords = $2, confirmed_body = $3,
               author = $4, categories = $5, rename_prefix = $6, updated_at = CURRENT_TIMESTAMP WHERE id = $7""",
            req.title, req.keywords, req.body, req.author,
            json.dumps(req.categories), req.title[:20], task_id,
        )

    await pipeline_service.advance_step(task_id, from_step=1, to_step=2)
    await pipeline_service.add_log(task_id, f"文案已确认: {req.title[:30]}", step=1)

    return ApiResponse.success(message="文案已确认，进入 Step 3 图片重命名")


# ══════════════════════════════════════════
# Step 3: 图片重命名
# ══════════════════════════════════════════

@router.get("/{task_id}/step/3/preview")
async def preview_rename(task_id: int, prefix: str = "", start: int = 1,
                         separator: str = "_", user: UserInfo = Depends(get_current_user)):
    """预览重命名结果。"""
    task = await pipeline_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    actual_prefix = prefix or task.get("rename_prefix", "image")
    preview = await rename_service.preview(task["folder_path"], actual_prefix, start, 2, separator)
    return ApiResponse.success(data=preview)


@router.put("/{task_id}/step/3/confirm")
async def confirm_rename(task_id: int, req: ConfirmRenameRequest,
                         bg: BackgroundTasks, user: UserInfo = Depends(get_current_user)):
    """确认并执行重命名。"""
    task = await pipeline_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    bg.add_task(rename_service.execute, task_id, task["folder_path"],
                req.prefix, req.start, req.digits, req.separator)

    return ApiResponse.success(message="重命名执行中，完成后自动进入 Step 4")


# ══════════════════════════════════════════
# Step 4: 封面制作
# ══════════════════════════════════════════

@router.post("/{task_id}/step/4/generate")
async def generate_cover(task_id: int, layout: str = "triple", candidates: int = 3,
                         bg: BackgroundTasks = None, user: UserInfo = Depends(get_current_user)):
    """生成候选封面。"""
    task = await pipeline_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    bg.add_task(cover_service.generate_candidates, task_id, task["folder_path"], layout, candidates)
    return ApiResponse.success(message="封面生成已启动")


@router.put("/{task_id}/step/4/confirm")
async def confirm_cover(task_id: int, req: ConfirmCoverRequest, user: UserInfo = Depends(get_current_user)):
    """确认选中的封面。"""
    cover_path = await cover_service.confirm_cover(task_id, req.cover_index)
    return ApiResponse.success(data={"cover_path": cover_path}, message="封面已确认，进入 Step 5 水印处理")


# ══════════════════════════════════════════
# Step 5: 水印处理
# ══════════════════════════════════════════

@router.get("/{task_id}/step/5/plan")
async def get_watermark_plan(task_id: int, user: UserInfo = Depends(get_current_user)):
    """获取各平台水印方案。"""
    plan = await watermark_service.get_watermark_plan(task_id)
    return ApiResponse.success(data=plan)


@router.put("/{task_id}/step/5/confirm")
async def confirm_watermark(task_id: int, bg: BackgroundTasks, user: UserInfo = Depends(get_current_user)):
    """确认水印方案，开始并行处理。"""
    bg.add_task(watermark_service.process_all_platforms, task_id)
    return ApiResponse.success(message="水印处理已启动，各平台并行处理中")


@router.get("/{task_id}/step/5/progress")
async def get_watermark_progress(task_id: int, user: UserInfo = Depends(get_current_user)):
    """获取各平台水印处理进度。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT pt.platform_id, p.name, pt.wm_status, pt.wm_progress, pt.wm_error
               FROM platform_tasks pt
               JOIN platforms p ON pt.platform_id = p.id
               WHERE pt.task_id = $1""",
            task_id,
        )
        progress = [dict(r) for r in rows]
        return ApiResponse.success(data=progress)


# ══════════════════════════════════════════
# Step 6: 上传 & 发布
# ══════════════════════════════════════════

@router.get("/{task_id}/step/6/status")
async def get_publish_status(task_id: int, user: UserInfo = Depends(get_current_user)):
    """获取各平台上传/切片/发布状态。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT pt.*, p.name as platform_name
               FROM platform_tasks pt
               JOIN platforms p ON pt.platform_id = p.id
               WHERE pt.task_id = $1""",
            task_id,
        )
        statuses = [dict(r) for r in rows]
        return ApiResponse.success(data=statuses)


@router.post("/{task_id}/step/6/publish")
async def publish(task_id: int, req: PublishRequest, bg: BackgroundTasks,
                  user: UserInfo = Depends(get_current_user)):
    """发布指定平台（或全部已就绪）。"""
    bg.add_task(publish_service.publish_platforms, task_id, req.platform_ids or None)
    return ApiResponse.success(message="发布任务已启动")


@router.post("/{task_id}/step/6/retry")
async def retry_publish(task_id: int, platform_id: int, bg: BackgroundTasks,
                        user: UserInfo = Depends(get_current_user)):
    """重试失败的平台。"""
    bg.add_task(publish_service.retry_platform, task_id, platform_id)
    return ApiResponse.success(message=f"平台 {platform_id} 重试已启动")


@router.put("/{task_id}/cancel")
async def cancel_task(task_id: int, user: UserInfo = Depends(get_current_user)):
    """取消任务。"""
    await pipeline_service.update_task_status(task_id, "cancelled")
    await pipeline_service.add_log(task_id, "任务已取消")
    return ApiResponse.success(message="任务已取消")


# ── 工具函数 ──

def _fix_filename_encoding(name: str) -> str:
    """修复 multipart 上传中的中文文件名编码。
    浏览器可能以多种方式传输中文文件名：
    1. 直接 UTF-8（现代浏览器，filename*=utf-8''xxx）
    2. Latin-1 编码的 UTF-8 字节（旧的 filename="xxx" 头）
    3. RFC 5987 格式
    """
    if not name:
        return "unknown"
    # 如果已经是合法的中文/ASCII，直接返回
    try:
        name.encode('ascii')
        return name  # 纯 ASCII
    except UnicodeEncodeError:
        pass
    # 检查是否已经是正确的 UTF-8 中文
    for ch in name:
        if '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf':
            return name  # 已经是正确中文
    # 获取原始字节（Latin-1 是 1:1 字节映射）
    try:
        raw_bytes = name.encode('latin-1')
    except UnicodeEncodeError:
        return name
    # 优先尝试 UTF-8
    try:
        return raw_bytes.decode('utf-8')
    except UnicodeDecodeError:
        pass
    # Windows 中文系统：尝试 GBK / GB18030
    try:
        return raw_bytes.decode('gbk')
    except UnicodeDecodeError:
        pass
    try:
        return raw_bytes.decode('gb18030')
    except UnicodeDecodeError:
        pass
    # cp1252（西欧）
    try:
        return raw_bytes.decode('cp1252')
    except UnicodeDecodeError:
        pass
    return name


def _scan_folder(folder_path: str) -> dict:
    """扫描文件夹，返回文件清单。"""
    img_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
    vid_exts = {".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv", ".webm"}
    txt_exts = {".txt", ".doc", ".docx"}
    manifest = {"images": [], "videos": [], "txts": []}
    if not os.path.isdir(folder_path):
        return manifest
    for fname in sorted(os.listdir(folder_path)):
        fpath = os.path.join(folder_path, fname)
        if not os.path.isfile(fpath):
            continue
        ext = os.path.splitext(fname)[1].lower()
        if ext in img_exts:
            manifest["images"].append(fname)
        elif ext in vid_exts:
            manifest["videos"].append(fname)
        elif ext in txt_exts:
            manifest["txts"].append(fname)
    return manifest
