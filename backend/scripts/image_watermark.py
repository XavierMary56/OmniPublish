#!/usr/bin/env python3
"""OmniPublish - 图片批量加水印 (YOLOv8 人脸感知定位)

改进点:
- 使用公共 face_detect 模块（修复 YOLO fallback bug）
- 递归改为迭代（os.walk）
- 输出格式保留原始格式（PNG/JPEG）
- 异常处理更细粒度
"""

import argparse, os, sys
from PIL import Image
import numpy as np

# 使用公共人脸检测模块
from face_detect import detect_faces, rects_overlap


def watermark_image(img, wm, position="bottom-right", margin=10, faces=None):
    """Apply watermark to image with face-aware positioning."""
    iw, ih = img.size
    ww, wh = wm.size

    positions = {
        "bottom-right": (iw - ww - margin, ih - wh - margin),
        "bottom-left":  (margin, ih - wh - margin),
        "top-right":    (iw - ww - margin, margin),
        "top-left":     (margin, margin),
        "center-left":  (margin, (ih - wh) // 2),
        "center-right": (iw - ww - margin, (ih - wh) // 2),
    }

    # 尝试优先位置，如果被人脸遮挡则尝试对角位置
    pos_order = [position]
    opposites = {
        "bottom-right": "bottom-left",
        "bottom-left": "bottom-right",
        "top-right": "top-left",
        "top-left": "top-right",
        "center-left": "center-right",
        "center-right": "center-left",
    }
    pos_order.append(opposites.get(position, "bottom-left"))

    for pos_name in pos_order:
        x, y = positions[pos_name]
        wm_rect = (x, y, x + ww, y + wh)

        if faces:
            face_rects = [(f["x1"], f["y1"], f["x2"], f["y2"]) for f in faces]
            overlap = any(rects_overlap(wm_rect, fr) for fr in face_rects)
            if overlap:
                continue
        # 无重叠或无人脸
        result = img.copy()
        result.paste(wm, (x, y), wm if wm.mode == "RGBA" else None)
        return result, pos_name

    # Fallback: 全部位置都被人脸遮挡，使用原始位置
    x, y = positions[position]
    result = img.copy()
    result.paste(wm, (x, y), wm if wm.mode == "RGBA" else None)
    return result, position


def calc_brightness(img):
    """计算图片的平均感知亮度 (0-255)。"""
    arr = np.array(img)
    if arr.ndim == 2:
        return float(np.mean(arr))
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    return float(np.mean(0.299 * r + 0.587 * g + 0.114 * b))


def process_folder(folder, output, watermark_path, img_width=800, wm_width=264,
                   margin=10, position="bottom-right", recursive=False, opacity=100,
                   watermark_light_path=None):
    """Batch watermark all images in folder (迭代方式，不使用递归)。"""
    exts = {".jpg", ".jpeg", ".png", ".webp"}

    # 加载水印
    wm_orig = Image.open(watermark_path).convert("RGBA")
    wm_light_orig = None
    if watermark_light_path and os.path.exists(watermark_light_path):
        wm_light_orig = Image.open(watermark_light_path).convert("RGBA")

    # 应用透明度
    if opacity < 100:
        for wm_img in [wm_orig, wm_light_orig]:
            if wm_img is None:
                continue
            alpha = wm_img.split()[3]
            alpha = alpha.point(lambda p: int(p * opacity / 100))
            wm_img.putalpha(alpha)

    wm_ratio = wm_orig.height / wm_orig.width

    os.makedirs(output, exist_ok=True)
    output_abs = os.path.realpath(output)
    wm_abs = os.path.realpath(watermark_path)
    wm_light_abs = os.path.realpath(watermark_light_path) if watermark_light_path else None

    count = 0
    moved = 0
    errors = 0

    # 迭代方式遍历目录（不使用递归函数）
    if recursive:
        walk_iter = os.walk(folder)
    else:
        # 只遍历顶层目录
        walk_iter = [(folder, [], [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))])]

    for src_dir, sub_dirs, file_names in walk_iter:
        # 跳过输出目录
        if os.path.realpath(src_dir) == output_abs:
            continue

        # 计算相对路径，确定输出子目录
        rel_path = os.path.relpath(src_dir, folder)
        if rel_path == ".":
            dst_dir = output
        else:
            dst_dir = os.path.join(output, rel_path)
        os.makedirs(dst_dir, exist_ok=True)

        for fname in sorted(file_names):
            fpath = os.path.join(src_dir, fname)

            if os.path.splitext(fname)[1].lower() not in exts:
                continue

            # 跳过水印文件本身
            real_fpath = os.path.realpath(fpath)
            if real_fpath == wm_abs or (wm_light_abs and real_fpath == wm_light_abs):
                print(f"[SKIP]  Watermark file: {fname}")
                continue

            # 封面文件直接复制
            if "_cover" in fname.lower():
                img = Image.open(fpath)
                img.save(os.path.join(dst_dir, fname), quality=95)
                print(f"[SKIP]  Cover file copied: {fname}")
                continue

            try:
                img = Image.open(fpath)
                original_format = img.format or "JPEG"
                has_alpha = img.mode in ("RGBA", "LA", "PA")

                # 转换为 RGB 处理（保留原始格式信息）
                img_rgb = img.convert("RGB")

                # 调整图片尺寸
                if img_width and img_rgb.width != img_width:
                    ratio = img_width / img_rgb.width
                    new_h = int(img_rgb.height * ratio)
                    img_rgb = img_rgb.resize((img_width, new_h), Image.LANCZOS)

                # 缩放水印
                wm_h = int(wm_width * wm_ratio)
                if wm_light_orig and calc_brightness(img_rgb) <= 128:
                    wm = wm_light_orig.resize((wm_width, wm_h), Image.LANCZOS)
                    wm_label = "light"
                else:
                    wm = wm_orig.resize((wm_width, wm_h), Image.LANCZOS)
                    wm_label = "dark" if wm_light_orig else ""

                # 人脸检测
                faces = detect_faces(np.array(img_rgb))

                # 添加水印
                result, pos_used = watermark_image(img_rgb, wm, position, margin, faces)

                # 根据原始格式保存
                out_path = os.path.join(dst_dir, fname)
                if original_format == "PNG" or has_alpha:
                    result.save(out_path, "PNG")
                else:
                    result.save(out_path, "JPEG", quality=95)

                if pos_used != position:
                    moved += 1
                    print(f"[WM]    {fname} → {pos_used} (face detected, moved){' [' + wm_label + ']' if wm_label else ''}")
                else:
                    print(f"[WM]    {fname} → {pos_used}{' [' + wm_label + ']' if wm_label else ''}")
                count += 1

            except Exception as e:
                print(f"[ERROR] {fname}: {e}")
                errors += 1

    print(f"\n[OK]    Watermarked: {count} images ({moved} repositioned due to face)")
    if errors > 0:
        print(f"[WARN]  {errors} files failed")


def main():
    parser = argparse.ArgumentParser(description="OmniPublish Image Watermarker")
    parser.add_argument("--folder", required=True, help="Input image folder")
    parser.add_argument("--output", default=None, help="Output directory")
    parser.add_argument("--watermark", required=True, help="Watermark PNG path (dark, default)")
    parser.add_argument("--watermark-light", default=None, help="Light watermark PNG (used on dark images)")
    parser.add_argument("--img-width", type=int, default=800, help="Target image width (0=no resize)")
    parser.add_argument("--wm-width", type=int, default=264, help="Watermark width in pixels")
    parser.add_argument("--margin", type=int, default=10, help="Edge margin in pixels")
    parser.add_argument("--position", default="bottom-right",
                        choices=["bottom-right", "bottom-left", "top-right", "top-left",
                                 "center-left", "center-right"])
    parser.add_argument("--recursive", action="store_true", help="Process subdirectories")
    parser.add_argument("--opacity", type=int, default=100, help="Watermark opacity 10-100 (100=opaque)")
    args = parser.parse_args()

    output = args.output or os.path.join(args.folder, "已处理")
    process_folder(args.folder, output, args.watermark, args.img_width,
                   args.wm_width, args.margin, args.position, args.recursive,
                   max(10, min(100, args.opacity)), args.watermark_light)

if __name__ == "__main__":
    main()
