#!/usr/bin/env python3
"""OmniPublish - 视频批量处理统一脚本 (Python rewrite)

Usage: python video_process.py <command> [options]
Commands: watermark, delogo, crop, blur-pad, trim, add-intro-outro, concat
"""

import argparse
import os
import platform
import re
import subprocess
import sys
import tempfile
from pathlib import Path


# ═══ Constants ═══
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv", ".webm", ".ts", ".m4v"}


# ═══ Codec auto-detection (延迟加载，避免 import 时阻塞) ═══
_default_codec_cache = None

def detect_default_codec():
    global _default_codec_cache
    if _default_codec_cache is not None:
        return _default_codec_cache
    system = platform.system()
    if system == "Darwin":
        candidates = ["h264_videotoolbox", "libx264"]
    elif system == "Windows":
        candidates = ["h264_nvenc", "h264_amf", "h264_qsv", "libx264"]
    else:
        candidates = ["h264_vaapi", "h264_nvenc", "libx264"]
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=5,
        )
        for c in candidates:
            if c in r.stdout:
                _default_codec_cache = c
                return c
    except Exception:
        pass
    _default_codec_cache = "libx264"
    return _default_codec_cache


# 延迟属性，首次使用时才检测
class _LazyCodec:
    def __str__(self):
        return detect_default_codec()
    def __repr__(self):
        return detect_default_codec()

DEFAULT_CODEC = "libx264"  # 默认值，argparse default 会用到


# ═══ Helpers ═══
def die(msg):
    print(f"[ERROR] {msg}", file=sys.stderr)
    sys.exit(1)


def info(msg):
    print(f"[INFO]  {msg}", flush=True)


def ok(msg):
    print(f"[OK]    {msg}", flush=True)


def find_videos(directory):
    """Return sorted list of Path objects with video extensions."""
    d = Path(directory)
    if not d.is_dir():
        return []
    results = []
    for p in d.iterdir():
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
            results.append(p)
    results.sort(key=lambda x: x.name)
    return results


def detect_orient(filepath):
    """Use ffprobe to detect orientation. Returns 'landscape' or 'portrait'."""
    try:
        w = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width", "-of", "csv=p=0", str(filepath)],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        h = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=height", "-of", "csv=p=0", str(filepath)],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        w, h = int(w), int(h)
        return "landscape" if w > h else "portrait"
    except Exception:
        return "portrait"


def get_duration(filepath):
    """Use ffprobe to get duration in integer seconds."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(filepath)],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        return int(float(out))
    except Exception:
        return 0


def get_dimensions(filepath):
    """Return (width, height) tuple from ffprobe, or (0, 0) on failure."""
    try:
        w = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width", "-of", "csv=p=0", str(filepath)],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        h = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=height", "-of", "csv=p=0", str(filepath)],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        return int(w), int(h)
    except Exception:
        return 0, 0


def calc_smart_target(files):
    """Return (tw, th) tuple. Smart 720p target based on input orientations."""
    widths = []
    heights = []
    has_portrait = False
    has_landscape = False

    for f in files:
        w, h = get_dimensions(f)
        if w == 0 or h == 0:
            continue
        widths.append(w)
        heights.append(h)
        if h >= w:
            has_portrait = True
        else:
            has_landscape = True

    n = len(widths)
    if n == 0:
        return 720, 1280

    base_w, base_h = widths[0], heights[0]

    if has_portrait and has_landscape:
        # Mixed: pick largest portrait as base
        best_area = 0
        for i in range(n):
            w, h = widths[i], heights[i]
            if h >= w:
                area = w * h
                if area > best_area:
                    base_w, base_h = w, h
                    best_area = area
        info(f"Mixed orientations \u2192 portrait base ({base_w}x{base_h})")
    else:
        # All same orientation: pick largest by area
        best_area = 0
        for i in range(n):
            w, h = widths[i], heights[i]
            area = w * h
            if area > best_area:
                base_w, base_h = w, h
                best_area = area
        info(f"Same orientation \u2192 largest base ({base_w}x{base_h})")

    # Scale to 720p level
    if base_h >= base_w:
        # Portrait: width=720, height proportional
        tw = 720
        th = 720 * base_h // base_w
    else:
        # Landscape: height=720, width proportional
        th = 720
        tw = 720 * base_w // base_h

    # Even dimensions (x264 requirement)
    tw = tw - tw % 2
    th = th - th % 2
    info(f"Smart target: {tw}x{th}")
    return tw, th


def ensure_outdir(d):
    if d:
        Path(d).mkdir(parents=True, exist_ok=True)


def run_ffmpeg(args, show_progress=False, timeout=600):
    """Run ffmpeg with list args, stream output line by line to stdout.

    show_progress=True 时解析 ffmpeg 进度行输出百分比。
    timeout: max seconds for the process (default 600).
    """
    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    import re as _re
    try:
        for line in proc.stdout:
            if show_progress:
                # 解析 ffmpeg 进度: time=00:01:23.45
                m = _re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)
                if m:
                    h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
                    elapsed = h * 3600 + mi * 60 + s
                    print(f"\r[PROGRESS] {elapsed:.1f}s processed", end="", flush=True)
                    continue
            print(line, end="", flush=True)
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        raise subprocess.TimeoutExpired(args[0], timeout)
    if show_progress:
        print()  # 换行
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, args[0])


def ffmpeg_safe_path(path):
    """Convert path to string with forward slashes and escape single quotes for concat list."""
    s = str(path).replace("\\", "/")
    # Escape single quotes for ffmpeg concat file format
    s = s.replace("'", "'\\''")
    return s


def compress_to_size(filepath, target_mb, codec):
    """Compress video to target size in MB by calculating required bitrate."""
    filepath = Path(filepath)
    dur = get_duration(filepath)
    if dur == 0:
        info(f"Skip compress (can't read duration): {filepath.name}")
        return

    cur_size_kb = filepath.stat().st_size // 1024
    target_kb = target_mb * 1024

    if cur_size_kb <= target_kb:
        info(f"Already under {target_mb}MB: {filepath.name} ({cur_size_kb // 1024}MB)")
        return

    # Target bitrate = target_size_bits / duration (leave 128kbps for audio)
    target_vbr = (target_kb * 8 // dur) - 128
    if target_vbr < 100:
        target_vbr = 100

    info(f"Compressing {filepath.name}: {cur_size_kb}KB \u2192 ~{target_kb}KB ({target_vbr}k video bitrate)")

    tmpf = filepath.with_name(filepath.stem + "_compressed.mp4")
    run_ffmpeg([
        "ffmpeg", "-y", "-i", str(filepath),
        "-c:v", codec, "-b:v", f"{target_vbr}k",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(tmpf), "-loglevel", "warning",
    ])

    if tmpf.exists():
        tmpf.replace(filepath)
        new_size_kb = filepath.stat().st_size // 1024
        ok(f"Compressed: {filepath.name} \u2192 {new_size_kb // 1024}MB")


# ═══ WATERMARK ═══
def _process_single_watermark(f, output, args, wm_file, wm_dur):
    """处理单个视频的水印添加（从 cmd_watermark 抽取，供迭代调用）。"""
    name = f.name
    base = f.stem
    outf = Path(output) / f"{base}.mp4"

    orient = detect_orient(f)
    scale_ratio = args.scale_landscape if orient == "landscape" else args.scale_portrait

    info(f"Processing: {name} (mode={args.wm_mode}, orient={orient}, scale={scale_ratio}%)")

    resolution = args.resolution
    if resolution == "original":
        scale_filter = "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    else:
        scale_filter = f"scale=w='if(gt(iw,ih),-2,{resolution})':h='if(gt(iw,ih),{resolution},-2)'"

    wm_scale = f"iw*{scale_ratio}/100"

    if args.wm_mode == "corner-cycle":
        cycle = wm_dur * 4
        d1, d2, d3 = wm_dur, wm_dur * 2, wm_dur * 3
        overlay_x = f"'if(lt(mod(t,{cycle}),{d1}),0,if(lt(mod(t,{cycle}),{d2}),W-w,if(lt(mod(t,{cycle}),{d3}),0,W-w)))'"
        overlay_y = f"'if(lt(mod(t,{cycle}),{d1}),0,if(lt(mod(t,{cycle}),{d2}),H-h,if(lt(mod(t,{cycle}),{d3}),H-h,0)))'"
        run_ffmpeg([
            "ffmpeg", "-y", "-i", str(f), "-stream_loop", "-1", "-i", str(wm_file),
            "-filter_complex",
            f"[0:v]{scale_filter},setsar=1[main];[1:v]scale={wm_scale}:-1[wm];"
            f"[main][wm]overlay=x={overlay_x}:y={overlay_y}:shortest=1,format=yuv420p",
            "-c:v", args.codec, "-b:v", args.bitrate, "-r", str(args.fps),
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(outf), "-loglevel", "warning", "-progress", "pipe:1",
        ], show_progress=True)
    elif args.wm_mode == "fixed":
        pos = args.fixed_pos
        pos_map = {"top-left": ("10", "10"), "top-right": ("W-w-10", "10"),
                   "bottom-left": ("10", "H-h-10"), "bottom-right": ("W-w-10", "H-h-10")}
        ox, oy = pos_map.get(pos, ("W-w-10", "H-h-10"))
        run_ffmpeg([
            "ffmpeg", "-y", "-i", str(f), "-stream_loop", "-1", "-i", str(wm_file),
            "-filter_complex",
            f"[0:v]{scale_filter},setsar=1[main];[1:v]scale={wm_scale}:-1[wm];"
            f"[main][wm]overlay=x={ox}:y={oy}:shortest=1,format=yuv420p",
            "-c:v", args.codec, "-b:v", args.bitrate, "-r", str(args.fps),
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(outf), "-loglevel", "warning", "-progress", "pipe:1",
        ], show_progress=True)
    elif args.wm_mode == "diagonal":
        if not args.wmfile2:
            die("Diagonal mode requires --wmfile2")
        wm_file2 = Path(args.wmfile2)
        if not wm_file2.is_file():
            die(f"Second watermark not found: {args.wmfile2}")
        half_cycle = wm_dur
        full_cycle = wm_dur * 2
        run_ffmpeg([
            "ffmpeg", "-y", "-i", str(f),
            "-stream_loop", "-1", "-i", str(wm_file),
            "-stream_loop", "-1", "-i", str(wm_file2),
            "-filter_complex",
            f"[0:v]{scale_filter},setsar=1[main];"
            f"[1:v]scale={wm_scale}:-1[wm1];[2:v]scale={wm_scale}:-1[wm2];"
            f"[main][wm1]overlay=x='if(lt(mod(t,{full_cycle}),{half_cycle}),0,W-w)':y=0:shortest=1[tmp];"
            f"[tmp][wm2]overlay=x='if(lt(mod(t,{full_cycle}),{half_cycle}),W-w,0)':y=H-h:shortest=1,format=yuv420p",
            "-c:v", args.codec, "-b:v", args.bitrate, "-r", str(args.fps),
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(outf), "-loglevel", "warning", "-progress", "pipe:1",
        ], show_progress=True)
    else:
        die(f"Unknown watermark mode: {args.wm_mode}")

    ok(f"{name} \u2192 {outf.name}")

    if args.compress and args.target_size > 0:
        compress_to_size(outf, args.target_size, args.codec)


def cmd_watermark(args):
    if not args.watermark:
        die("Missing --watermark")
    wm_file = Path(args.watermark)
    if not wm_file.is_file():
        die(f"Watermark file not found: {args.watermark}")

    input_dir = Path(args.input)

    # Subfolder mode: 迭代处理每个子目录（不使用递归）
    if args.subfolders:
        sub_dirs = sorted([sub for sub in input_dir.iterdir() if sub.is_dir()])
        sub_count = 0
        for sub in sub_dirs:
            info(f"\u2550\u2550\u2550 \u5904\u7406\u5b50\u6587\u4ef6\u5939: {sub.name} \u2550\u2550\u2550")
            sub_output = str(sub / "\u5df2\u5904\u7406")
            ensure_outdir(sub_output)
            wm_dur_sub = get_duration(wm_file)
            if wm_dur_sub == 0:
                wm_dur_sub = 15
            sub_videos = find_videos(str(sub))
            for f in sub_videos:
                _process_single_watermark(f, sub_output, args, wm_file, wm_dur_sub)
            sub_count += 1
        ok(f"Subfolder mode complete: {sub_count} subdirectories processed")
        return

    output = args.output or str(input_dir / "\u5df2\u5904\u7406")
    ensure_outdir(output)

    wm_dur = get_duration(wm_file)
    if wm_dur == 0:
        wm_dur = 15

    count = 0
    for f in find_videos(args.input):
        _process_single_watermark(f, output, args, wm_file, wm_dur)
        count += 1

    ok(f"Watermark complete: {count} videos (mode={args.wm_mode})")


# ═══ DELOGO (动态坐标，按实际分辨率比例计算) ═══
def _calc_delogo_regions(vw, vh, orient):
    """按实际分辨率动态计算四角 delogo 区域。

    基准：720x1280 竖屏时四角区域为 304x160，按比例缩放到实际分辨率。
    支持自定义坐标覆盖（通过 --dl-tl 等参数）。
    """
    if orient == "portrait":
        # 基准 720x1280
        rw, rh = vw / 720, vh / 1280
        w, h = int(304 * rw), int(160 * rh)
        return [
            (1, 1, w, h),                    # top-left
            (vw - w - 1, 1, w, h),            # top-right
            (1, vh - h - 1, w, h),            # bottom-left
            (vw - w - 1, vh - h - 1, w, h),   # bottom-right
        ]
    else:
        # 基准 1280x720
        rw, rh = vw / 1280, vh / 720
        w, h = int(305 * rw), int(160 * rh)
        return [
            (1, 1, w, h),
            (vw - w - 1, 1, w, h),
            (1, vh - h - 1, w, h),
            (vw - w - 1, vh - h - 1, w, h),
        ]


def _parse_custom_delogo(coord_str):
    """解析自定义 delogo 坐标，格式: x,y,w,h"""
    if not coord_str:
        return None
    parts = coord_str.split(",")
    if len(parts) == 4:
        return tuple(int(p.strip()) for p in parts)
    return None


def cmd_delogo(args):
    output = args.output or str(Path(args.input) / "\u5df2\u5904\u7406")
    ensure_outdir(output)

    # 解析自定义坐标
    custom_coords = {
        "tl": _parse_custom_delogo(getattr(args, 'dl_tl', '')),
        "tr": _parse_custom_delogo(getattr(args, 'dl_tr', '')),
        "bl": _parse_custom_delogo(getattr(args, 'dl_bl', '')),
        "br": _parse_custom_delogo(getattr(args, 'dl_br', '')),
    }

    count = 0
    for f in find_videos(args.input):
        name = f.name
        base = f.stem
        outf = Path(output) / f"{base}.mp4"
        o = args.orient
        if o == "auto":
            o = detect_orient(f)

        vw, vh = get_dimensions(f)
        if vw == 0 or vh == 0:
            info(f"Skip (can't read dimensions): {name}")
            continue

        info(f"Delogo ({o}, {vw}x{vh}): {name}")

        # 动态计算或使用自定义坐标
        regions = _calc_delogo_regions(vw, vh, o)
        corners = ["tl", "tr", "bl", "br"]
        for i, corner in enumerate(corners):
            if custom_coords[corner]:
                regions[i] = custom_coords[corner]

        delogo_str = ",".join(
            f"delogo=x={x}:y={y}:w={w}:h={h}" for x, y, w, h in regions
        )

        run_ffmpeg([
            "ffmpeg", "-y", "-i", str(f),
            "-vf", delogo_str,
            "-c:v", args.codec, "-b:v", args.bitrate, "-c:a", "copy",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(outf), "-loglevel", "warning",
        ])

        ok(f"{name} \u2192 {outf.name}")
        count += 1

    ok(f"Delogo complete: {count} videos")


# ═══ CROP ═══
def cmd_crop(args):
    output = args.output or str(Path(args.input) / "\u5df2\u5904\u7406")
    ensure_outdir(output)

    count = 0
    for f in find_videos(args.input):
        name = f.name
        base = f.stem
        outf = Path(output) / f"{base}.mp4"
        o = args.orient
        if o == "auto":
            o = detect_orient(f)

        if o == "portrait":
            crop_filter = "crop=iw:'floor(iw*4/3/2)*2'"
        else:
            crop_filter = "crop='floor(ih*670/720/2)*2':'floor(ih/2)*2'"

        info(f"Crop ({o}): {name}")

        run_ffmpeg([
            "ffmpeg", "-y", "-i", str(f),
            "-vf", crop_filter,
            "-c:v", args.codec, "-b:v", args.bitrate, "-c:a", "copy",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(outf), "-loglevel", "warning",
        ])

        ok(f"{name} \u2192 {outf.name}")
        count += 1

    ok(f"Crop complete: {count} videos")


def _validate_filter_param(value: str, name: str) -> str:
    """Validate ffmpeg filter parameters to prevent injection."""
    # Only allow digits, slashes, colons, dots, minus signs (for numeric expressions)
    if not re.match(r'^[\d/:.\-]+$', value):
        die(f"Invalid {name} parameter: {value} (only digits, /, :, ., - allowed)")
    return value


# ═══ BLUR-PAD ═══
def cmd_blur_pad(args):
    output = args.output or str(Path(args.input) / "\u5df2\u5904\u7406")
    ensure_outdir(output)

    count = 0
    for f in find_videos(args.input):
        name = f.name
        base = f.stem
        outf = Path(output) / f"{base}.mp4"
        o = args.orient
        if o == "auto":
            o = detect_orient(f)

        if o == "landscape":
            tw, th = 1280, 720
        else:
            tw, th = 720, 1280

        info(f"Blur-pad ({o} \u2192 {tw}x{th}): {name}")

        bg_scale = _validate_filter_param(args.bg_scale, "bg_scale")
        strength = _validate_filter_param(args.strength, "strength")

        run_ffmpeg([
            "ffmpeg", "-y", "-i", str(f),
            "-filter_complex",
            f"[0:v]scale={tw}/{bg_scale}:{th}/{bg_scale},boxblur={strength},scale={tw}:{th}[bg];"
            f"[0:v]scale='if(gt(a,{tw}/{th}),{tw},-2)':'if(gt(a,{tw}/{th}),-2,{th})'[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2",
            "-c:v", args.codec, "-b:v", args.bitrate, "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(outf), "-loglevel", "warning",
        ])

        ok(f"{name} \u2192 {outf.name}")
        count += 1

    ok(f"Blur-pad complete: {count} videos")


# ═══ TRIM ═══
def cmd_trim(args):
    output = args.output or str(Path(args.input) / "\u5df2\u5904\u7406")
    ensure_outdir(output)

    count = 0
    for f in find_videos(args.input):
        name = f.name
        base = f.stem
        ext = f.suffix  # includes the dot
        dur = get_duration(f)

        if dur == 0:
            info(f"Skip (can't read duration): {name}")
            continue

        new_dur = dur - args.start - args.end
        if new_dur < args.min_length:
            info(f"Skip (too short after trim: {new_dur}s < {args.min_length}s): {name}")
            continue

        info(f"Trim: {name} ({dur}s \u2192 {new_dur}s, cut head={args.start}s tail={args.end}s)")

        if args.mode == "copy":
            # Preserve original extension in copy mode
            outf = Path(output) / f"{base}{ext}"
            run_ffmpeg([
                "ffmpeg", "-y", "-ss", str(args.start), "-i", str(f),
                "-t", str(new_dur),
                "-c", "copy", "-movflags", "+faststart",
                str(outf), "-loglevel", "warning",
            ])
        else:
            outf = Path(output) / f"{base}{ext}"
            run_ffmpeg([
                "ffmpeg", "-y", "-ss", str(args.start), "-i", str(f),
                "-t", str(new_dur),
                "-c:v", args.codec, "-b:v", args.bitrate,
                "-c:a", "aac", "-b:a", "128k",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                str(outf), "-loglevel", "warning",
            ])

        ok(f"{name} \u2192 {outf.name}")
        count += 1

    ok(f"Trim complete: {count} videos")


# ═══ ADD INTRO/OUTRO ═══
def cmd_add_intro_outro(args):
    if not args.intro and not args.outro:
        die("Need at least --intro or --outro")
    if args.intro and not Path(args.intro).is_file():
        die(f"Intro file not found: {args.intro}")
    if args.outro and not Path(args.outro).is_file():
        die(f"Outro file not found: {args.outro}")

    output = args.output or str(Path(args.input) / "\u5df2\u5904\u7406")
    ensure_outdir(output)

    tmp_dir = tempfile.mkdtemp(prefix="intro_outro_")

    try:
        count = 0
        for f in find_videos(args.input):
            name = f.name
            base = f.stem
            outf = Path(output) / f"{base}.mp4"

            info(f"Add intro/outro: {name}")

            # Collect all files to determine smart target
            all_files = [f]
            if args.intro:
                all_files.append(Path(args.intro))
            if args.outro:
                all_files.append(Path(args.outro))

            tw, th = calc_smart_target(all_files)
            scale_vf = (
                f"scale={tw}:{th}:force_original_aspect_ratio=decrease,"
                f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2,setsar=1"
            )

            # Encode all to same format (libx264 CRF, matching merge_videos.py)
            intro_enc = ""
            outro_enc = ""

            if args.intro:
                intro_enc = os.path.join(tmp_dir, "intro_enc.mp4")
                run_ffmpeg([
                    "ffmpeg", "-y", "-i", args.intro,
                    "-vf", scale_vf,
                    "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-c:a", "aac",
                    "-movflags", "+faststart",
                    intro_enc, "-loglevel", "warning",
                ])

            if args.outro:
                outro_enc = os.path.join(tmp_dir, "outro_enc.mp4")
                run_ffmpeg([
                    "ffmpeg", "-y", "-i", args.outro,
                    "-vf", scale_vf,
                    "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-c:a", "aac",
                    "-movflags", "+faststart",
                    outro_enc, "-loglevel", "warning",
                ])

            main_enc = os.path.join(tmp_dir, "main_enc.mp4")
            run_ffmpeg([
                "ffmpeg", "-y", "-i", str(f),
                "-vf", scale_vf,
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac",
                "-movflags", "+faststart",
                main_enc, "-loglevel", "warning",
            ])

            # Build concat list (use ffmpeg_safe_path for Windows compat)
            list_file = os.path.join(tmp_dir, "concat.txt")
            with open(list_file, "w", encoding="utf-8") as lf:
                if intro_enc:
                    lf.write(f"file '{ffmpeg_safe_path(intro_enc)}'\n")
                lf.write(f"file '{ffmpeg_safe_path(main_enc)}'\n")
                if outro_enc:
                    lf.write(f"file '{ffmpeg_safe_path(outro_enc)}'\n")

            run_ffmpeg([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", list_file,
                "-c", "copy", "-movflags", "+faststart",
                str(outf), "-loglevel", "warning",
            ])

            ok(f"{name} \u2192 {outf.name}")
            count += 1

        ok(f"Add intro/outro complete: {count} videos")

    finally:
        # Cleanup temp directory
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══ CONCAT ═══
def cmd_concat(args):
    default_output = str(Path(args.input) / "\u5df2\u5904\u7406" / "merged.mp4")
    output = args.output or default_output
    outdir = str(Path(output).parent)
    ensure_outdir(outdir)

    # Collect video files
    vfiles = find_videos(args.input)
    count = len(vfiles)
    if count == 0:
        die(f"No videos found in {args.input}")

    info(f"Concat: {count} videos \u2192 {output} (method={args.method}, scale={args.scale})")

    if args.method == "demuxer" and args.scale == "first":
        # Fast demuxer concat (only works well for same-format videos)
        tmp_fd, list_file = tempfile.mkstemp(prefix="concat_", suffix=".txt")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as lf:
                for f in vfiles:
                    safe = ffmpeg_safe_path(f.resolve())
                    lf.write(f"file '{safe}'\n")
            run_ffmpeg([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", list_file,
                "-c", "copy", "-movflags", "+faststart",
                output, "-loglevel", "warning",
            ])
        finally:
            os.unlink(list_file)
    else:
        # Smart resolution: detect orientations and pick best 720p base
        scale = args.scale
        if scale == "720p":
            tw, th = 1280, 720
        elif scale == "1080p":
            tw, th = 1920, 1080
        else:
            tw, th = calc_smart_target(vfiles)

        info(f"Target resolution: {tw}x{th}")

        # Build filter_complex string (exactly matching merge_videos.py)
        # IMPORTANT: only process video in filter, reference audio streams directly
        cmd_args = ["ffmpeg", "-y"]
        filter_parts = []
        stream_list = ""

        for n, f in enumerate(vfiles):
            cmd_args.extend(["-i", str(f)])
            filter_parts.append(
                f"[{n}:v]scale={tw}:{th}:force_original_aspect_ratio=decrease,"
                f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2,setsar=1[v{n}]"
            )
            stream_list += f"[v{n}][{n}:a]"

        filter_str = "; ".join(filter_parts)
        filter_str += f"; {stream_list}concat=n={count}:v=1:a=1[outv][outa]"

        cmd_args.extend([
            "-filter_complex", filter_str,
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac",
            "-movflags", "+faststart",
            output, "-loglevel", "warning",
        ])

        run_ffmpeg(cmd_args)

    ok(f"Concat complete: {count} videos \u2192 {output}")


# ═══ Argument parser ═══
def build_parser():
    parser = argparse.ArgumentParser(
        prog="video_process.py",
        description="OmniPublish Video Processor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Commands:\n"
            "  watermark        MOV \u56db\u89d2\u8f6e\u8f6c\u6c34\u5370\n"
            "  delogo           \u906e\u76d6\u56db\u89d2\u6c34\u5370 (delogo filter)\n"
            "  crop             \u88c1\u6389\u56db\u89d2\u6c34\u5370\n"
            "  blur-pad         \u865a\u5316\u586b\u5145\u5230\u6807\u51c6\u5c3a\u5bf8\n"
            "  trim             \u53bb\u7247\u5934\u7247\u5c3e\n"
            "  add-intro-outro  \u52a0\u7247\u5934\u7247\u5c3e\uff08720p \u62fc\u63a5\uff09\n"
            "  concat           \u591a\u89c6\u9891\u5408\u6210\n"
            "\n"
            "Common options:\n"
            "  --input DIR      \u8f93\u5165\u6587\u4ef6\u5939 (required)\n"
            "  --output DIR     \u8f93\u51fa\u6587\u4ef6\u5939 (default: input/\u5df2\u5904\u7406)\n"
            "  --codec CODEC    \u7f16\u7801\u5668 (default: h264_videotoolbox / libx264)\n"
            "  --bitrate RATE   \u7801\u7387 (default: 2M)\n"
            "  --orient MODE    \u65b9\u5411: auto/portrait/landscape (default: auto)\n"
        ),
    )
    subparsers = parser.add_subparsers(dest="command")

    # --- Common arguments function ---
    def add_common(sp):
        sp.add_argument("--input", required=True, help="\u8f93\u5165\u6587\u4ef6\u5939")
        sp.add_argument("--output", default="", help="\u8f93\u51fa\u6587\u4ef6\u5939 (default: input/\u5df2\u5904\u7406)")
        sp.add_argument("--codec", default=DEFAULT_CODEC, help=f"\u7f16\u7801\u5668 (default: {DEFAULT_CODEC})")
        sp.add_argument("--bitrate", default="2M", help="\u7801\u7387 (default: 2M)")
        sp.add_argument("--fps", type=int, default=30, help="FPS (default: 30)")
        sp.add_argument("--orient", default="auto", choices=["auto", "portrait", "landscape"],
                        help="\u65b9\u5411 (default: auto)")

    # watermark
    sp = subparsers.add_parser("watermark", help="MOV \u56db\u89d2\u8f6e\u8f6c\u6c34\u5370")
    add_common(sp)
    sp.add_argument("--watermark", default="", help="\u6c34\u5370\u6587\u4ef6")
    sp.add_argument("--scale-ratio", type=int, default=15, help="\u6c34\u5370\u7f29\u653e\u6bd4\u4f8b (default: 15)")
    sp.add_argument("--wm-mode", default="corner-cycle",
                    choices=["corner-cycle", "fixed", "diagonal"],
                    help="\u6c34\u5370\u6a21\u5f0f (default: corner-cycle)")
    sp.add_argument("--fixed-pos", default="bottom-right",
                    choices=["top-left", "top-right", "bottom-left", "bottom-right"],
                    help="Fixed mode position (default: bottom-right)")
    sp.add_argument("--wmfile2", default="", help="\u7b2c\u4e8c\u4e2a\u6c34\u5370 (diagonal mode)")
    sp.add_argument("--scale-landscape", type=int, default=35,
                    help="\u6a2a\u5c4f\u6c34\u5370\u7f29\u653e%% (default: 35)")
    sp.add_argument("--scale-portrait", type=int, default=35,
                    help="\u7ad6\u5c4f\u6c34\u5370\u7f29\u653e%% (default: 35)")
    sp.add_argument("--resolution", default="720", help="\u5206\u8fa8\u7387 (default: 720, or 'original')")
    sp.add_argument("--compress", action="store_true", help="\u538b\u7f29\u5230\u76ee\u6807\u5927\u5c0f")
    sp.add_argument("--target-size", type=int, default=0, help="\u76ee\u6807\u5927\u5c0fMB (default: 0)")
    sp.add_argument("--subfolders", action="store_true", help="\u9012\u5f52\u5904\u7406\u5b50\u6587\u4ef6\u5939")

    # delogo
    sp = subparsers.add_parser("delogo", help="\u906e\u76d6\u56db\u89d2\u6c34\u5370 (delogo filter)")
    add_common(sp)
    sp.add_argument("--dl-tl", default="", help="Delogo top-left coords")
    sp.add_argument("--dl-tr", default="", help="Delogo top-right coords")
    sp.add_argument("--dl-bl", default="", help="Delogo bottom-left coords")
    sp.add_argument("--dl-br", default="", help="Delogo bottom-right coords")

    # crop
    sp = subparsers.add_parser("crop", help="\u88c1\u6389\u56db\u89d2\u6c34\u5370")
    add_common(sp)

    # blur-pad
    sp = subparsers.add_parser("blur-pad", help="\u865a\u5316\u586b\u5145\u5230\u6807\u51c6\u5c3a\u5bf8")
    add_common(sp)
    sp.add_argument("--strength", default="5:1", help="Blur strength (default: 5:1)")
    sp.add_argument("--bg-scale", default="1/8", help="Background scale (default: 1/8)")

    # trim
    sp = subparsers.add_parser("trim", help="\u53bb\u7247\u5934\u7247\u5c3e")
    add_common(sp)
    sp.add_argument("--start", type=int, default=0, help="Trim start seconds (default: 0)")
    sp.add_argument("--end", type=int, default=11, help="Trim end seconds (default: 11)")
    sp.add_argument("--mode", default="copy", choices=["copy", "encode"],
                    help="Trim mode (default: copy)")
    sp.add_argument("--min-length", type=int, default=5,
                    help="Min length after trim (default: 5)")

    # add-intro-outro
    sp = subparsers.add_parser("add-intro-outro", help="\u52a0\u7247\u5934\u7247\u5c3e\uff08720p \u62fc\u63a5\uff09")
    add_common(sp)
    sp.add_argument("--intro", default="", help="\u7247\u5934\u6587\u4ef6")
    sp.add_argument("--outro", default="", help="\u7247\u5c3e\u6587\u4ef6")

    # concat
    sp = subparsers.add_parser("concat", help="\u591a\u89c6\u9891\u5408\u6210")
    add_common(sp)
    sp.add_argument("--method", default="demuxer", choices=["demuxer", "filter"],
                    help="Concat method (default: demuxer)")
    sp.add_argument("--scale", default="first",
                    help="Scale mode: first/720p/1080p/smart (default: first)")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        print()
        print("OmniPublish Video Processor")
        print("Usage: python video_process.py <command> [options]")
        print()
        print("Commands:")
        print("  watermark        MOV \u56db\u89d2\u8f6e\u8f6c\u6c34\u5370")
        print("  delogo           \u906e\u76d6\u56db\u89d2\u6c34\u5370 (delogo filter)")
        print("  crop             \u88c1\u6389\u56db\u89d2\u6c34\u5370")
        print("  blur-pad         \u865a\u5316\u586b\u5145\u5230\u6807\u51c6\u5c3a\u5bf8")
        print("  trim             \u53bb\u7247\u5934\u7247\u5c3e")
        print("  add-intro-outro  \u52a0\u7247\u5934\u7247\u5c3e\uff08720p \u62fc\u63a5\uff09")
        print("  concat           \u591a\u89c6\u9891\u5408\u6210")
        print()
        print("Common options:")
        print("  --input DIR      \u8f93\u5165\u6587\u4ef6\u5939 (required)")
        print("  --output DIR     \u8f93\u51fa\u6587\u4ef6\u5939 (default: input/\u5df2\u5904\u7406)")
        print("  --codec CODEC    \u7f16\u7801\u5668 (default: h264_videotoolbox / libx264)")
        print("  --bitrate RATE   \u7801\u7387 (default: 2M)")
        print("  --orient MODE    \u65b9\u5411: auto/portrait/landscape (default: auto)")
        sys.exit(0)

    dispatch = {
        "watermark": cmd_watermark,
        "delogo": cmd_delogo,
        "crop": cmd_crop,
        "blur-pad": cmd_blur_pad,
        "trim": cmd_trim,
        "add-intro-outro": cmd_add_intro_outro,
        "concat": cmd_concat,
    }

    handler = dispatch.get(args.command)
    if handler:
        handler(args)
    else:
        die(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
