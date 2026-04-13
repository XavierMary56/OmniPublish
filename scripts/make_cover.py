#!/usr/bin/env python3
"""OmniPublish - 封面制作 (YOLOv8 人脸检测 + 智能裁剪拼接)"""

import argparse, os, sys
import numpy as np
from PIL import Image

# ═══ YOLOv8 face detection ═══
_yolo_model = None
_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_yolo_model():
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

def detect_face(img_array):
    """Detect largest face, return dict with x,y,w,h,cx,cy or None."""
    try:
        model = get_yolo_model()
        results = model(img_array, verbose=False, conf=0.4)
        boxes = results[0].boxes
        if len(boxes) == 0:
            return None
        # Pick largest box by area
        best = None
        best_area = 0
        for box in boxes:
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            w, h = x2 - x1, y2 - y1
            area = w * h
            if area > best_area:
                best_area = area
                best = {"x": int(x1), "y": int(y1), "w": int(w), "h": int(h),
                        "cx": int((x1+x2)/2), "cy": int((y1+y2)/2),
                        "head_top": int(y1)}
        return best
    except Exception:
        return None

def smart_crop(img, target_w, target_h, head_margin_ratio=0.15):
    """Crop image to target size with face-aware positioning."""
    img_array = np.array(img)
    oh, ow = img_array.shape[:2]
    face = detect_face(img_array)

    # Scale to cover target
    scale = max(target_w / ow, target_h / oh)
    sw, sh = int(ow * scale), int(oh * scale)
    img_scaled = img.resize((sw, sh), Image.LANCZOS)

    head_target_y = int(target_h * head_margin_ratio)

    if face:
        fx = int(face["cx"] * scale)
        fy = int(face["head_top"] * scale)
        fh = int(face["h"] * scale)

        # Try extra scale to position head at target_y
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

        # Vertical: align head top to margin
        y1 = max(0, fy - head_target_y)
        y1 = min(y1, sh - target_h)

        # Horizontal: center on face, but respect edges
        x1 = max(0, fx - target_w // 2)
        x1 = min(x1, sw - target_w)

        return img_scaled.crop((x1, y1, x1 + target_w, y1 + target_h)), fh
    else:
        # No face: center crop
        x1 = (sw - target_w) // 2
        y1 = (sh - target_h) // 2
        return img_scaled.crop((x1, y1, x1 + target_w, y1 + target_h)), 0

def make_cover(folder, output, layout="triple", head_margin=0.15, quality=95):
    """Generate cover image from folder of images."""
    exts = {".jpg", ".jpeg", ".png", ".webp"}
    images = sorted([
        os.path.join(folder, f) for f in os.listdir(folder)
        if os.path.splitext(f)[1].lower() in exts
        and not f.startswith(".")
        and "_cover" not in f.lower()
    ])

    if not images:
        print("[ERROR] No images found in folder")
        return None

    layout_config = {
        "single": {"count": 1, "width": 640, "height": 640, "panels": [(640, 640)]},
        "double": {"count": 2, "width": 1280, "height": 640, "panels": [(640, 640), (640, 640)]},
        "triple": {"count": 3, "width": 1300, "height": 640, "panels": [(433, 640), (434, 640), (433, 640)]},
    }
    cfg = layout_config.get(layout, layout_config["triple"])
    count = min(cfg["count"], len(images))
    selected = images[:count]

    # If fewer images than needed, duplicate last
    while len(selected) < cfg["count"]:
        selected.append(selected[-1])

    print(f"[INFO]  Layout: {layout}, Images: {len(selected)}, Size: {cfg['width']}x{cfg['height']}")

    # Pass 1: initial crop + get head heights
    panels = []
    head_heights = []
    for i, img_path in enumerate(selected):
        pw, ph = cfg["panels"][i]
        img = Image.open(img_path).convert("RGB")
        cropped, hh = smart_crop(img, pw, ph, head_margin)
        panels.append((img_path, cropped))
        head_heights.append(hh)
        print(f"[INFO]  Panel {i+1}: {os.path.basename(img_path)} → {pw}x{ph}, head_h={hh}")

    # Pass 2: normalize head sizes if needed
    max_hh = max(head_heights) if head_heights else 0
    if max_hh > 0:
        for i, (img_path, _) in enumerate(panels):
            if head_heights[i] > 0 and head_heights[i] < max_hh * 0.95:
                pw, ph = cfg["panels"][i]
                img = Image.open(img_path).convert("RGB")
                # Re-crop with slightly more aggressive scaling
                adjusted_margin = head_margin * (head_heights[i] / max_hh)
                cropped, _ = smart_crop(img, pw, ph, adjusted_margin)
                panels[i] = (img_path, cropped)
                print(f"[INFO]  Panel {i+1}: re-processed for head size normalization")

    # Stitch
    cover = Image.new("RGB", (cfg["width"], cfg["height"]))
    x_offset = 0
    for _, panel_img in panels:
        cover.paste(panel_img, (x_offset, 0))
        x_offset += panel_img.width

    # Save
    os.makedirs(output, exist_ok=True)
    folder_name = os.path.basename(os.path.normpath(folder))
    out_path = os.path.join(output, f"{folder_name}_cover.jpg")
    cover.save(out_path, "JPEG", quality=quality)
    print(f"[OK]    Cover saved: {out_path}")
    return out_path

def main():
    parser = argparse.ArgumentParser(description="OmniPublish Cover Maker")
    parser.add_argument("--folder", required=True, help="Input image folder")
    parser.add_argument("--output", default=None, help="Output directory (default: same as folder)")
    parser.add_argument("--layout", default="triple", choices=["single", "double", "triple"])
    parser.add_argument("--head-margin", type=float, default=0.15, help="Head top margin ratio (0-1)")
    parser.add_argument("--quality", type=int, default=95, help="JPEG quality")
    args = parser.parse_args()

    output = args.output or args.folder
    make_cover(args.folder, output, args.layout, args.head_margin, args.quality)

if __name__ == "__main__":
    main()
