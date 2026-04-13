#!/usr/bin/env python3
"""OmniPublish - 图片批量加水印 (YOLOv8 人脸感知定位)"""

import argparse, os, sys
from PIL import Image
import numpy as np

# ═══ YOLOv8 singleton ═══
_yolo_model = None
_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _get_model():
    global _yolo_model
    if _yolo_model is None:
        from ultralytics import YOLO
        # Prefer bundled model in skill root (avoids network download)
        bundled = os.path.join(_SKILL_DIR, "yolov8n.pt")
        bundled_face = os.path.join(_SKILL_DIR, "yolov8n-face.pt")
        try:
            _yolo_model = YOLO(bundled_face if os.path.isfile(bundled_face) else "yolov8n-face.pt")
        except Exception:
            _yolo_model = YOLO(bundled if os.path.isfile(bundled) else "yolov8n.pt")
    return _yolo_model

def detect_face_region(img_array):
    """Detect face bounding boxes using YOLOv8. Returns list of (x1,y1,x2,y2)."""
    try:
        model = _get_model()
        results = model(img_array, verbose=False, conf=0.4)
        faces = []
        for box in results[0].boxes:
            cls_id = int(box.cls[0]) if hasattr(box, 'cls') else -1
            # yolov8n-face has no cls filter; yolov8n needs person class (0)
            if _yolo_model and "face" not in str(getattr(_yolo_model, 'model_name', '')):
                if cls_id != 0:
                    continue
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            faces.append((int(x1), int(y1), int(x2), int(y2)))
        return faces
    except Exception:
            return []

def rects_overlap(r1, r2):
    """Check if two (x1,y1,x2,y2) rectangles overlap."""
    return not (r1[2] <= r2[0] or r2[2] <= r1[0] or r1[3] <= r2[1] or r2[3] <= r1[1])

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

    # Try preferred position first
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
            overlap = any(rects_overlap(wm_rect, f) for f in faces)
            if overlap:
                continue
        # No overlap or no faces
        result = img.copy()
        result.paste(wm, (x, y), wm if wm.mode == "RGBA" else None)
        return result, pos_name

    # Fallback: use original position anyway
    x, y = positions[position]
    result = img.copy()
    result.paste(wm, (x, y), wm if wm.mode == "RGBA" else None)
    return result, position

def calc_brightness(img):
    """Calculate average perceived brightness of an image (0-255)."""
    arr = np.array(img)
    if arr.ndim == 2:
        return float(np.mean(arr))
    # Weighted luminance: 0.299R + 0.587G + 0.114B
    r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
    return float(np.mean(0.299 * r + 0.587 * g + 0.114 * b))

def process_folder(folder, output, watermark_path, img_width=800, wm_width=264,
                   margin=10, position="bottom-right", recursive=False, opacity=100,
                   watermark_light_path=None):
    """Batch watermark all images in folder."""
    exts = {".jpg", ".jpeg", ".png", ".webp"}

    # Load watermark(s): main = dark (for bright images), optional light (for dark images)
    wm_orig = Image.open(watermark_path).convert("RGBA")
    wm_light_orig = None
    if watermark_light_path:
        wm_light_orig = Image.open(watermark_light_path).convert("RGBA")
    # Apply opacity
    if opacity < 100:
        alpha = wm_orig.split()[3]
        alpha = alpha.point(lambda p: int(p * opacity / 100))
        wm_orig.putalpha(alpha)
        if wm_light_orig:
            alpha_l = wm_light_orig.split()[3]
            alpha_l = alpha_l.point(lambda p: int(p * opacity / 100))
            wm_light_orig.putalpha(alpha_l)
    wm_ratio = wm_orig.height / wm_orig.width

    os.makedirs(output, exist_ok=True)
    output_abs = os.path.realpath(output)
    wm_abs = os.path.realpath(watermark_path)
    wm_light_abs = os.path.realpath(watermark_light_path) if watermark_light_path else None

    count = 0
    moved = 0

    def process_dir(src_dir, dst_dir):
        nonlocal count, moved
        os.makedirs(dst_dir, exist_ok=True)

        for fname in sorted(os.listdir(src_dir)):
            fpath = os.path.join(src_dir, fname)

            # Skip output directory to prevent infinite recursion
            if os.path.isdir(fpath):
                if os.path.realpath(fpath) == output_abs:
                    print(f"[SKIP]  Output directory: {fname}")
                    continue
                if recursive:
                    process_dir(fpath, os.path.join(dst_dir, fname))
                else:
                    print(f"[SKIP]  Subdirectory (non-recursive): {fname}")
                continue

            if os.path.splitext(fname)[1].lower() not in exts:
                continue
            # Skip the watermark file(s)
            real_fpath = os.path.realpath(fpath)
            if real_fpath == wm_abs or (wm_light_abs and real_fpath == wm_light_abs):
                print(f"[SKIP]  Watermark file: {fname}")
                continue
            if "_cover" in fname.lower():
                # Copy cover as-is
                img = Image.open(fpath)
                img.save(os.path.join(dst_dir, fname), quality=95)
                print(f"[SKIP]  Cover file copied: {fname}")
                continue

            img = Image.open(fpath).convert("RGB")

            # Resize image
            if img_width and img.width != img_width:
                ratio = img_width / img.width
                new_h = int(img.height * ratio)
                img = img.resize((img_width, new_h), Image.LANCZOS)

            # Scale watermark — use light watermark on dark images if available
            wm_h = int(wm_width * wm_ratio)
            if wm_light_orig and calc_brightness(img) <= 128:
                wm = wm_light_orig.resize((wm_width, wm_h), Image.LANCZOS)
                wm_label = "light"
            else:
                wm = wm_orig.resize((wm_width, wm_h), Image.LANCZOS)
                wm_label = "dark" if wm_light_orig else ""

            # Detect faces
            faces = detect_face_region(np.array(img))

            # Apply watermark
            result, pos_used = watermark_image(img, wm, position, margin, faces)
            result.save(os.path.join(dst_dir, fname), "JPEG", quality=95)

            if pos_used != position:
                moved += 1
                print(f"[WM]    {fname} → {pos_used} (face detected, moved){' ['+wm_label+']' if wm_label else ''}")
            else:
                print(f"[WM]    {fname} → {pos_used}{' ['+wm_label+']' if wm_label else ''}")
            count += 1

    process_dir(folder, output)
    print(f"\n[OK]    Watermarked: {count} images ({moved} repositioned due to face)")

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
