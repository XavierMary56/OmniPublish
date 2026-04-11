#!/usr/bin/env python3
"""OmniPublish - 封面制作 (YOLOv8 人脸检测 + 智能裁剪拼接)

改进点:
- 使用公共 face_detect 模块
- 支持多候选封面生成（--candidates N）
- 新增更多尺寸（800×450, 900×1200 竖版）
- 智能选图：按人脸清晰度排序
"""

import argparse, itertools, os, sys
import numpy as np
from PIL import Image

from face_detect import detect_largest_face


def smart_crop(img, target_w, target_h, head_margin_ratio=0.15):
    """Crop image to target size with face-aware positioning."""
    img_array = np.array(img)
    oh, ow = img_array.shape[:2]
    face = detect_largest_face(img_array)

    # Scale to cover target
    scale = max(target_w / ow, target_h / oh)
    sw, sh = int(ow * scale), int(oh * scale)
    img_scaled = img.resize((sw, sh), Image.LANCZOS)

    head_target_y = int(target_h * head_margin_ratio)

    if face:
        fx = int(face["cx"] * scale)
        fy = int(face["head_top"] * scale)
        fh = int(face["h"] * scale)

        if fy > head_target_y:
            needed_space_below = target_h - head_target_y
            actual_space_below = sh - fy
            if actual_space_below > 0:
                extra = needed_space_below / actual_space_below
                if extra > 1.0:
                    new_scale = scale * extra
                    sw2, sh2 = int(ow * new_scale), int(oh * new_scale)
                    if sw2 >= target_w and sh2 >= target_h:
                        img_scaled = img.resize((sw2, sh2), Image.LANCZOS)
                        sw, sh = sw2, sh2
                        fx = int(face["cx"] * new_scale)
                        fy = int(face["head_top"] * new_scale)
                        fh = int(face["h"] * new_scale)
                        scale = new_scale

        y1 = max(0, fy - head_target_y)
        y1 = min(y1, sh - target_h)
        x1 = max(0, fx - target_w // 2)
        x1 = min(x1, sw - target_w)

        return img_scaled.crop((x1, y1, x1 + target_w, y1 + target_h)), fh
    else:
        x1 = (sw - target_w) // 2
        y1 = (sh - target_h) // 2
        return img_scaled.crop((x1, y1, x1 + target_w, y1 + target_h)), 0


def score_image(img_path):
    """评估图片质量分数（用于智能选图排序）。"""
    try:
        img = Image.open(img_path)
        arr = np.array(img.convert("L"))
        # Laplacian variance 作为清晰度指标
        lap = np.abs(np.diff(arr, axis=0)).mean() + np.abs(np.diff(arr, axis=1)).mean()
        # 尺寸加分
        size_score = min(img.width * img.height / (1920 * 1080), 1.0)
        # 人脸加分
        face = detect_largest_face(np.array(img.convert("RGB")))
        face_score = 0.3 if face else 0.0
        return lap * 0.5 + size_score * 0.3 + face_score * 0.2
    except Exception:
        return 0.0


# 布局配置 — 扩展更多尺寸
LAYOUT_CONFIG = {
    "single":   {"count": 1, "width": 640,  "height": 640,  "panels": [(640, 640)]},
    "double":   {"count": 2, "width": 1280, "height": 640,  "panels": [(640, 640), (640, 640)]},
    "triple":   {"count": 3, "width": 1300, "height": 640,  "panels": [(433, 640), (434, 640), (433, 640)]},
    "wide":     {"count": 1, "width": 800,  "height": 450,  "panels": [(800, 450)]},
    "portrait": {"count": 1, "width": 900,  "height": 1200, "panels": [(900, 1200)]},
}


def make_single_cover(images, layout, head_margin, quality, output, suffix=""):
    """生成单张封面。"""
    cfg = LAYOUT_CONFIG.get(layout, LAYOUT_CONFIG["triple"])
    count = min(cfg["count"], len(images))
    selected = list(images[:count])

    # 不够则复制最后一张
    while len(selected) < cfg["count"]:
        selected.append(selected[-1])

    # Pass 1: 初始裁剪 + 获取头部高度
    panels = []
    head_heights = []
    for i, img_path in enumerate(selected):
        pw, ph = cfg["panels"][i]
        img = Image.open(img_path).convert("RGB")
        cropped, hh = smart_crop(img, pw, ph, head_margin)
        panels.append((img_path, cropped))
        head_heights.append(hh)

    # Pass 2: 头部大小归一化
    max_hh = max(head_heights) if head_heights else 0
    if max_hh > 0:
        for i, (img_path, _) in enumerate(panels):
            if 0 < head_heights[i] < max_hh * 0.95:
                pw, ph = cfg["panels"][i]
                img = Image.open(img_path).convert("RGB")
                adjusted_margin = head_margin * (head_heights[i] / max_hh)
                cropped, _ = smart_crop(img, pw, ph, adjusted_margin)
                panels[i] = (img_path, cropped)

    # 拼接
    cover = Image.new("RGB", (cfg["width"], cfg["height"]))
    x_offset = 0
    for _, panel_img in panels:
        cover.paste(panel_img, (x_offset, 0))
        x_offset += panel_img.width

    # 保存
    os.makedirs(output, exist_ok=True)
    folder_name = os.path.basename(os.path.normpath(os.path.dirname(images[0])))
    out_name = f"{folder_name}_cover{suffix}.jpg"
    out_path = os.path.join(output, out_name)
    cover.save(out_path, "JPEG", quality=quality)
    return out_path


def make_cover(folder, output, layout="triple", head_margin=0.15, quality=95,
               candidates=1):
    """Generate cover image(s) from folder of images.

    Args:
        candidates: 生成候选封面数量（不同图片组合）
    """
    exts = {".jpg", ".jpeg", ".png", ".webp"}
    images = sorted([
        os.path.join(folder, f) for f in os.listdir(folder)
        if os.path.splitext(f)[1].lower() in exts
        and not f.startswith(".")
        and "_cover" not in f.lower()
    ])

    if not images:
        print("[ERROR] No images found in folder")
        return []

    cfg = LAYOUT_CONFIG.get(layout, LAYOUT_CONFIG["triple"])
    count_needed = cfg["count"]

    print(f"[INFO]  Layout: {layout}, Available: {len(images)}, Size: {cfg['width']}x{cfg['height']}")
    print(f"[INFO]  Generating {candidates} candidate(s)...")

    # 按图片质量评分排序
    if len(images) > count_needed and candidates > 1:
        scored = [(img, score_image(img)) for img in images]
        scored.sort(key=lambda x: x[1], reverse=True)
        images_sorted = [s[0] for s in scored]
    else:
        images_sorted = images

    results = []

    if candidates == 1:
        # 单候选：取前 N 张最佳图
        path = make_single_cover(images_sorted, layout, head_margin, quality, output)
        print(f"[OK]    Cover saved: {path}")
        results.append(path)
    else:
        # 多候选：不同图片组合
        combos = list(itertools.combinations(images_sorted[:min(len(images_sorted), 8)], count_needed))
        # 取前 candidates 个不重复组合
        for idx, combo in enumerate(combos[:candidates]):
            suffix = f"_{chr(65 + idx)}"  # _A, _B, _C
            path = make_single_cover(combo, layout, head_margin, quality, output, suffix)
            print(f"[OK]    Candidate {chr(65 + idx)}: {path}")
            results.append(path)

    print(f"\n[OK]    Generated {len(results)} cover candidate(s)")
    return results


def main():
    parser = argparse.ArgumentParser(description="OmniPublish Cover Maker")
    parser.add_argument("--folder", required=True, help="Input image folder")
    parser.add_argument("--output", default=None, help="Output directory (default: same as folder)")
    parser.add_argument("--layout", default="triple",
                        choices=list(LAYOUT_CONFIG.keys()),
                        help="Cover layout: single/double/triple/wide/portrait")
    parser.add_argument("--head-margin", type=float, default=0.15, help="Head top margin ratio (0-1)")
    parser.add_argument("--quality", type=int, default=95, help="JPEG quality")
    parser.add_argument("--candidates", type=int, default=3,
                        help="Number of candidate covers to generate (default: 3)")
    args = parser.parse_args()

    output = args.output or args.folder
    make_cover(args.folder, output, args.layout, args.head_margin, args.quality,
               args.candidates)

if __name__ == "__main__":
    main()
