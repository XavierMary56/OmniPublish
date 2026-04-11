#!/usr/bin/env python3
"""OmniPublish - 图片/视频批量重命名

改进点:
- 新增回滚机制：第二阶段失败时恢复原文件名
- 新增视频文件支持（可选）
- 新增 --include-video 参数
- _cover 文件跳过逻辑有文档说明
"""

import argparse, json, os, sys


# 支持的图片格式
IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff"}
# 支持的视频格式
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv", ".webm", ".ts", ".m4v"}


def rename_files(folder, prefix="image", start=1, digits=2, separator="_",
                 dry_run=False, include_video=False):
    """Batch rename files in folder with sequential numbering.

    包含回滚机制：如果重命名过程中发生错误，会尝试恢复所有已重命名的文件。
    """
    allowed_exts = IMG_EXTS.copy()
    if include_video:
        allowed_exts |= VIDEO_EXTS

    files = sorted([
        f for f in os.listdir(folder)
        if os.path.splitext(f)[1].lower() in allowed_exts
        and not f.startswith(".")
        and "_cover" not in f.lower()  # 跳过封面文件（make_cover.py 生成的）
    ])

    if not files:
        print("[ERROR] No matching files found in folder")
        return False

    renames = []
    for i, fname in enumerate(files):
        ext = os.path.splitext(fname)[1]
        num = str(start + i).zfill(digits)
        new_name = f"{prefix}{separator}{num}{ext}"
        renames.append((fname, new_name))

    # 冲突检查
    existing = set(os.listdir(folder))
    new_names = {r[1] for r in renames}
    old_names = {r[0] for r in renames}
    conflicts = (new_names & existing) - old_names
    if conflicts:
        print(f"[WARN]  Naming conflicts detected: {conflicts}")
        print("[WARN]  Using temp names to avoid conflicts")

    if dry_run:
        print(f"[DRY]   Preview ({len(renames)} files):")
        for old, new in renames:
            print(f"        {old} → {new}")
        # 输出映射关系供前端预览
        print(f"\n@@RENAME_PREVIEW@@{json.dumps(renames, ensure_ascii=False)}")
        return True

    # ── 第一阶段：全部重命名为临时文件名 ──
    temp_renames = []
    try:
        for old, new in renames:
            temp = f"__omnipub_temp_{old}"
            src = os.path.join(folder, old)
            tmp = os.path.join(folder, temp)
            os.rename(src, tmp)
            temp_renames.append((old, temp, new))
    except Exception as e:
        print(f"[ERROR] 第一阶段重命名失败: {e}")
        # 回滚已完成的临时重命名
        _rollback_phase1(folder, temp_renames)
        return False

    # ── 第二阶段：临时文件名 → 最终文件名 ──
    completed = []
    try:
        for old, temp, new in temp_renames:
            src = os.path.join(folder, temp)
            dst = os.path.join(folder, new)
            os.rename(src, dst)
            completed.append((old, temp, new))
    except Exception as e:
        print(f"[ERROR] 第二阶段重命名失败: {e}")
        # 回滚：已完成的 new → old，未完成的 temp → old
        _rollback_phase2(folder, completed, temp_renames)
        return False

    # 输出结果
    for old, new in renames:
        print(f"[RENAME] {old} → {new}")
    print(f"\n[OK]    Renamed: {len(renames)} files")

    # 输出映射关系（供回滚使用）
    mapping = {new: old for old, new in renames}
    mapping_path = os.path.join(folder, "__omnipub_rename_map.json")
    with open(mapping_path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    print(f"[INFO]  Mapping saved: {mapping_path} (用于回滚)")

    return True


def _rollback_phase1(folder, temp_renames):
    """回滚第一阶段：temp → old"""
    print("[INFO]  Rolling back phase 1...")
    for old, temp, new in temp_renames:
        try:
            src = os.path.join(folder, temp)
            dst = os.path.join(folder, old)
            if os.path.exists(src):
                os.rename(src, dst)
                print(f"[ROLL]  {temp} → {old}")
        except Exception as e2:
            print(f"[ERROR] Rollback failed for {temp}: {e2}")
    print("[INFO]  Rollback complete (phase 1)")


def _rollback_phase2(folder, completed, temp_renames):
    """回滚第二阶段：已完成的 new → old，未完成的 temp → old"""
    print("[INFO]  Rolling back phase 2...")
    completed_set = {c[2] for c in completed}  # new names that were completed

    for old, temp, new in temp_renames:
        try:
            if new in completed_set:
                # 已完成：new → old
                src = os.path.join(folder, new)
                dst = os.path.join(folder, old)
                if os.path.exists(src):
                    os.rename(src, dst)
                    print(f"[ROLL]  {new} → {old}")
            else:
                # 未完成：temp → old
                src = os.path.join(folder, temp)
                dst = os.path.join(folder, old)
                if os.path.exists(src):
                    os.rename(src, dst)
                    print(f"[ROLL]  {temp} → {old}")
        except Exception as e2:
            print(f"[ERROR] Rollback failed: {e2}")
    print("[INFO]  Rollback complete (phase 2)")


def undo_rename(folder):
    """从映射文件回滚上次重命名。"""
    mapping_path = os.path.join(folder, "__omnipub_rename_map.json")
    if not os.path.exists(mapping_path):
        print("[ERROR] No rename mapping found. Cannot undo.")
        return False

    with open(mapping_path, "r", encoding="utf-8") as f:
        mapping = json.load(f)

    count = 0
    for new_name, old_name in mapping.items():
        src = os.path.join(folder, new_name)
        dst = os.path.join(folder, old_name)
        if os.path.exists(src):
            os.rename(src, dst)
            print(f"[UNDO]  {new_name} → {old_name}")
            count += 1

    os.remove(mapping_path)
    print(f"\n[OK]    Undone: {count} files")
    return True


def main():
    parser = argparse.ArgumentParser(description="OmniPublish File Renamer")
    parser.add_argument("--folder", required=True, help="File folder path")
    parser.add_argument("--prefix", default="image", help="Filename prefix")
    parser.add_argument("--start", type=int, default=1, help="Start number")
    parser.add_argument("--digits", type=int, default=2, help="Number padding digits")
    parser.add_argument("--separator", default="_", help="Separator between prefix and number")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, don't rename")
    parser.add_argument("--include-video", action="store_true", help="Include video files in renaming")
    parser.add_argument("--undo", action="store_true", help="Undo last rename using saved mapping")
    args = parser.parse_args()

    if not os.path.isdir(args.folder):
        print(f"[ERROR] Not a directory: {args.folder}")
        sys.exit(1)

    if args.undo:
        undo_rename(args.folder)
    else:
        rename_files(args.folder, args.prefix, args.start, args.digits,
                     args.separator, args.dry_run, args.include_video)

if __name__ == "__main__":
    main()
