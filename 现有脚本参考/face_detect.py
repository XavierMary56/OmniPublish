#!/usr/bin/env python3
"""OmniPublish - YOLOv8 人脸检测公共模块

供 image_watermark.py 和 make_cover.py 共用，避免重复代码。

用法:
    from face_detect import detect_faces, detect_largest_face
"""

import os
import sys

_yolo_model = None
_model_type = None  # "face" or "general"


def _get_model():
    """懒加载 YOLOv8 模型（单例）。优先 face 模型，fallback 到通用模型。"""
    global _yolo_model, _model_type
    if _yolo_model is not None:
        return _yolo_model, _model_type

    try:
        from ultralytics import YOLO
    except ImportError:
        print("[WARN] ultralytics 未安装，人脸检测不可用 (pip install ultralytics)")
        return None, None

    # 优先尝试 face 专用模型
    face_model_path = os.environ.get("YOLO_FACE_MODEL", "yolov8n-face.pt")
    try:
        _yolo_model = YOLO(face_model_path)
        _model_type = "face"
        print(f"[INFO]  YOLO 模型已加载: {face_model_path} (face)")
    except Exception:
        # fallback 到通用模型
        general_model_path = os.environ.get("YOLO_GENERAL_MODEL", "yolov8n.pt")
        try:
            _yolo_model = YOLO(general_model_path)
            _model_type = "general"
            print(f"[INFO]  YOLO 模型已加载: {general_model_path} (general, filter cls=0)")
        except Exception as e:
            print(f"[WARN] YOLO 模型加载失败: {e}，人脸检测不可用")
            return None, None

    return _yolo_model, _model_type


def detect_faces(img_array, conf=0.4):
    """检测图片中的人脸区域。

    Args:
        img_array: numpy array (H, W, C)
        conf: 置信度阈值

    Returns:
        list of dict: [{x1, y1, x2, y2, w, h, cx, cy, head_top, area}]
    """
    model, model_type = _get_model()
    if model is None:
        return []

    try:
        results = model(img_array, verbose=False, conf=conf)
        faces = []
        for box in results[0].boxes:
            # 通用模型只取 person 类 (cls=0)
            if model_type == "general":
                cls_id = int(box.cls[0]) if hasattr(box, 'cls') else -1
                if cls_id != 0:
                    continue

            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
            w, h = x2 - x1, y2 - y1
            faces.append({
                "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                "w": w, "h": h,
                "cx": (x1 + x2) // 2, "cy": (y1 + y2) // 2,
                "head_top": y1,
                "area": w * h,
            })
        return faces
    except Exception as e:
        print(f"[WARN] 人脸检测异常: {e}")
        return []


def detect_largest_face(img_array, conf=0.4):
    """检测最大的人脸。返回 dict 或 None。"""
    faces = detect_faces(img_array, conf)
    if not faces:
        return None
    return max(faces, key=lambda f: f["area"])


def rects_overlap(r1, r2):
    """检查两个 (x1, y1, x2, y2) 矩形是否重叠。

    r1, r2: tuple/dict，支持 (x1,y1,x2,y2) 或 {x1,y1,x2,y2}
    """
    if isinstance(r1, dict):
        r1 = (r1["x1"], r1["y1"], r1["x2"], r1["y2"])
    if isinstance(r2, dict):
        r2 = (r2["x1"], r2["y1"], r2["x2"], r2["y2"])
    return not (r1[2] <= r2[0] or r2[2] <= r1[0] or r1[3] <= r2[1] or r2[3] <= r1[1])
