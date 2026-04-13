#!/usr/bin/env bash
# OmniPublish - 视频批量处理统一脚本
# Usage: bash video_process.sh <command> [options]
# Commands: watermark, delogo, crop, blur-pad, trim, concat

set -uo pipefail

# ═══ Defaults ═══
CODEC="h264_videotoolbox"
BITRATE="2M"
FPS=30
ORIENT="auto"

# Fallback codec for non-macOS
if ! ffmpeg -hide_banner -encoders 2>/dev/null | grep -q h264_videotoolbox; then
  CODEC="libx264"
fi

VIDEO_EXTS="mp4|mov|avi|mkv|flv|wmv|webm|ts|m4v"

# ═══ Helpers ═══
die() { echo "[ERROR] $*" >&2; exit 1; }
info() { echo "[INFO]  $*"; }
ok()   { echo "[OK]    $*"; }

detect_orient() {
  local f="$1"
  local w h
  w=$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=p=0 "$f" 2>/dev/null)
  h=$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 "$f" 2>/dev/null)
  if [ "$w" -gt "$h" ]; then echo "landscape"; else echo "portrait"; fi
}

get_duration() {
  ffprobe -v error -show_entries format=duration -of csv=p=0 "$1" 2>/dev/null | cut -d. -f1
}

find_videos() {
  local dir="$1"
  find -L "$dir" -maxdepth 1 -type f | grep -iE "\.($VIDEO_EXTS)$" | sort
}

# Smart 720p target: detect orientations, pick best base, scale to 720p.
# Follows merge_videos.py logic exactly:
#   - Mixed (portrait+landscape): use portrait video's ratio as base
#   - All same orientation: use largest resolution as base
#   - Scale base to 720p level, ensure even dimensions
# Sets global vars: SMART_TW, SMART_TH
calc_smart_target() {
  local -a files=("$@")
  local -a widths=() heights=()
  local has_portrait=0 has_landscape=0

  # Collect dimensions
  for f in "${files[@]}"; do
    local w h
    w=$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=p=0 "$f" 2>/dev/null)
    h=$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 "$f" 2>/dev/null)
    [ -z "$w" ] || [ -z "$h" ] && continue
    widths+=("$w"); heights+=("$h")
    if [ "$h" -ge "$w" ]; then has_portrait=1; else has_landscape=1; fi
  done

  local n=${#widths[@]}
  [ "$n" -eq 0 ] && { SMART_TW=720; SMART_TH=1280; return; }

  local base_w=${widths[0]} base_h=${heights[0]}

  if [ "$has_portrait" -eq 1 ] && [ "$has_landscape" -eq 1 ]; then
    # Mixed: pick largest portrait as base
    local best_area=0
    for ((i=0; i<n; i++)); do
      local w=${widths[$i]} h=${heights[$i]}
      if [ "$h" -ge "$w" ]; then
        local area=$((w * h))
        if [ "$area" -gt "$best_area" ]; then
          base_w=$w; base_h=$h; best_area=$area
        fi
      fi
    done
    info "Mixed orientations → portrait base (${base_w}x${base_h})"
  else
    # All same orientation: pick largest by area
    local best_area=0
    for ((i=0; i<n; i++)); do
      local w=${widths[$i]} h=${heights[$i]}
      local area=$((w * h))
      if [ "$area" -gt "$best_area" ]; then
        base_w=$w; base_h=$h; best_area=$area
      fi
    done
    info "Same orientation → largest base (${base_w}x${base_h})"
  fi

  # Scale to 720p level (matching merge_videos.py exactly)
  if [ "$base_h" -ge "$base_w" ]; then
    # Portrait: width=720, height proportional
    SMART_TW=720
    SMART_TH=$((720 * base_h / base_w))
  else
    # Landscape: height=720, width proportional
    SMART_TH=720
    SMART_TW=$((720 * base_w / base_h))
  fi
  # Even dimensions (x264 requirement)
  SMART_TW=$((SMART_TW - SMART_TW % 2))
  SMART_TH=$((SMART_TH - SMART_TH % 2))
  info "Smart target: ${SMART_TW}x${SMART_TH}"
}

ensure_outdir() {
  local d="$1"
  [ -z "$d" ] && return
  mkdir -p "$d"
}

compress_to_size() {
  # Compress video to target size in MB by calculating required bitrate
  local file="$1" target_mb="$2"
  local dur; dur=$(get_duration "$file")
  [ -z "$dur" ] || [ "$dur" -eq 0 ] && { info "Skip compress (can't read duration): $(basename "$file")"; return; }
  local cur_size_kb; cur_size_kb=$(du -k "$file" | cut -f1)
  local target_kb=$((target_mb * 1024))
  # Skip if already under target
  [ "$cur_size_kb" -le "$target_kb" ] && { info "Already under ${target_mb}MB: $(basename "$file") ($(( cur_size_kb / 1024 ))MB)"; return; }
  # Target bitrate = target_size_bits / duration (leave 128kbps for audio)
  local target_vbr=$(( (target_kb * 8 / dur) - 128 ))
  [ "$target_vbr" -lt 100 ] && target_vbr=100
  info "Compressing $(basename "$file"): ${cur_size_kb}KB → ~${target_kb}KB (${target_vbr}k video bitrate)"
  local tmpf="${file%.mp4}_compressed.mp4"
  ffmpeg -y -i "$file" \
    -c:v "$CODEC" -b:v "${target_vbr}k" \
    -c:a aac -b:a 128k \
    -pix_fmt yuv420p -movflags +faststart \
    "$tmpf" -loglevel warning
  if [ -f "$tmpf" ]; then
    mv "$tmpf" "$file"
    local new_size_kb; new_size_kb=$(du -k "$file" | cut -f1)
    ok "Compressed: $(basename "$file") → $(( new_size_kb / 1024 ))MB"
  fi
}

# ═══ Parse global options ═══
CMD="${1:-help}"
shift || true

INPUT="" OUTPUT="" WM_FILE="" WM_SCALE_RATIO=15 RESOLUTION=720
WM_MODE="corner-cycle" WM_FIXED_POS="bottom-right" WM_FILE2="" WM_SCALE_LANDSCAPE=35 WM_SCALE_PORTRAIT=35
STRENGTH="5:1" BG_SCALE="1/8"
TRIM_START=0 TRIM_END=11 TRIM_MODE="copy" MIN_LENGTH=5
CONCAT_METHOD="demuxer" CONCAT_SCALE="first"
COMPRESS=0 TARGET_SIZE_MB=0
SUBFOLDERS=0
INTRO_FILE="" OUTRO_FILE=""
# Delogo coords (set per orient)
DL_TL="" DL_TR="" DL_BL="" DL_BR=""

while [ $# -gt 0 ]; do
  case "$1" in
    --input)       INPUT="$2"; shift 2;;
    --output)      OUTPUT="$2"; shift 2;;
    --watermark)   WM_FILE="$2"; shift 2;;
    --scale-ratio) WM_SCALE_RATIO="$2"; shift 2;;
    --wm-mode)     WM_MODE="$2"; shift 2;;
    --fixed-pos)   WM_FIXED_POS="$2"; shift 2;;
    --wmfile2)     WM_FILE2="$2"; shift 2;;
    --scale-landscape) WM_SCALE_LANDSCAPE="$2"; shift 2;;
    --scale-portrait)  WM_SCALE_PORTRAIT="$2"; shift 2;;
    --resolution)  RESOLUTION="$2"; shift 2;;
    --codec)       CODEC="$2"; shift 2;;
    --bitrate)     BITRATE="$2"; shift 2;;
    --fps)         FPS="$2"; shift 2;;
    --orient)      ORIENT="$2"; shift 2;;
    --strength)    STRENGTH="$2"; shift 2;;
    --bg-scale)    BG_SCALE="$2"; shift 2;;
    --start)       TRIM_START="$2"; shift 2;;
    --end)         TRIM_END="$2"; shift 2;;
    --mode)        TRIM_MODE="$2"; shift 2;;
    --min-length)  MIN_LENGTH="$2"; shift 2;;
    --method)      CONCAT_METHOD="$2"; shift 2;;
    --scale)       CONCAT_SCALE="$2"; shift 2;;
    --dl-tl)       DL_TL="$2"; shift 2;;
    --dl-tr)       DL_TR="$2"; shift 2;;
    --dl-bl)       DL_BL="$2"; shift 2;;
    --dl-br)       DL_BR="$2"; shift 2;;
    --compress)    COMPRESS=1; shift;;
    --target-size) TARGET_SIZE_MB="$2"; shift 2;;
    --subfolders)  SUBFOLDERS=1; shift;;
    --intro)       INTRO_FILE="$2"; shift 2;;
    --outro)       OUTRO_FILE="$2"; shift 2;;
    *) die "Unknown option: $1";;
  esac
done

[ -z "$INPUT" ] && die "Missing --input"

# ═══ WATERMARK ═══
cmd_watermark() {
  [ -z "$WM_FILE" ] && die "Missing --watermark"
  [ -f "$WM_FILE" ] || die "Watermark file not found: $WM_FILE"

  # Subfolder mode: recurse into each subdirectory
  if [ "$SUBFOLDERS" -eq 1 ]; then
    local sub_count=0
    for sub in "$INPUT"/*/; do
      [ -d "$sub" ] || continue
      info "═══ 处理子文件夹: $(basename "$sub") ═══"
      # Re-invoke self with same args but for this subfolder (no --subfolders to avoid infinite recursion)
      local sub_args=("$0" watermark --input "$sub" --output "$sub/已处理" --watermark "$WM_FILE")
      sub_args+=(--wm-mode "$WM_MODE" --scale-landscape "$WM_SCALE_LANDSCAPE" --scale-portrait "$WM_SCALE_PORTRAIT")
      sub_args+=(--resolution "$RESOLUTION" --codec "$CODEC" --bitrate "$BITRATE" --fps "$FPS")
      [ "$WM_MODE" = "fixed" ] && sub_args+=(--fixed-pos "$WM_FIXED_POS")
      [ -n "$WM_FILE2" ] && sub_args+=(--wmfile2 "$WM_FILE2")
      [ "$COMPRESS" -eq 1 ] && sub_args+=(--compress --target-size "$TARGET_SIZE_MB")
      bash "${sub_args[@]}"
      sub_count=$((sub_count+1))
    done
    ok "Subfolder mode complete: $sub_count subdirectories processed"
    return
  fi

  [ -z "$OUTPUT" ] && OUTPUT="${INPUT}/已处理"
  ensure_outdir "$OUTPUT"

  # Get watermark duration for corner cycling
  local wm_dur
  wm_dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$WM_FILE" 2>/dev/null | awk '{printf "%d", $1}')
  [ -z "$wm_dur" ] || [ "$wm_dur" -eq 0 ] && wm_dur=15

  local count=0
  while IFS= read -r f <&3; do
    local name; name=$(basename "$f")
    local base="${name%.*}"
    local outf="$OUTPUT/${base}.mp4"

    # Detect orientation for per-orient scale
    local orient
    orient=$(detect_orient "$f")
    local scale_ratio
    if [ "$orient" = "landscape" ]; then
      scale_ratio="$WM_SCALE_LANDSCAPE"
    else
      scale_ratio="$WM_SCALE_PORTRAIT"
    fi

    info "Processing: $name (mode=$WM_MODE, orient=$orient, scale=${scale_ratio}%)"

    # Scale filter: shorter side to resolution (like super_console.sh)
    local scale_filter
    if [ "$RESOLUTION" = "original" ]; then
      scale_filter="scale=trunc(iw/2)*2:trunc(ih/2)*2"
    else
      scale_filter="scale=w='if(gt(iw,ih),-2,$RESOLUTION)':h='if(gt(iw,ih),$RESOLUTION,-2)'"
    fi

    # Watermark scale: percentage of video short side
    local wm_scale="iw*${scale_ratio}/100"

    case "$WM_MODE" in
      corner-cycle)
        # 4-corner cycling: TL → BR → BL → TR
        local cycle=$((wm_dur * 4))
        local d1=$wm_dur d2=$((wm_dur*2)) d3=$((wm_dur*3))
        local overlay_x="'if(lt(mod(t,$cycle),$d1),0,if(lt(mod(t,$cycle),$d2),W-w,if(lt(mod(t,$cycle),$d3),0,W-w)))'"
        local overlay_y="'if(lt(mod(t,$cycle),$d1),0,if(lt(mod(t,$cycle),$d2),H-h,if(lt(mod(t,$cycle),$d3),H-h,0)))'"

        ffmpeg -y -i "$f" -stream_loop -1 -i "$WM_FILE" \
          -filter_complex "[0:v]${scale_filter},setsar=1[main];[1:v]scale=${wm_scale}:-1[wm];[main][wm]overlay=x=${overlay_x}:y=${overlay_y}:shortest=1,format=yuv420p" \
          -c:v "$CODEC" -b:v "$BITRATE" -r "$FPS" \
          -c:a aac -b:a 128k \
          -pix_fmt yuv420p -movflags +faststart \
          "$outf" -loglevel warning
        ;;

      fixed)
        # Fixed position overlay
        local ox oy
        case "$WM_FIXED_POS" in
          top-left)     ox=10; oy=10;;
          top-right)    ox="W-w-10"; oy=10;;
          bottom-left)  ox=10; oy="H-h-10";;
          bottom-right) ox="W-w-10"; oy="H-h-10";;
          *)            ox="W-w-10"; oy="H-h-10";;
        esac

        ffmpeg -y -i "$f" -stream_loop -1 -i "$WM_FILE" \
          -filter_complex "[0:v]${scale_filter},setsar=1[main];[1:v]scale=${wm_scale}:-1[wm];[main][wm]overlay=x=${ox}:y=${oy}:shortest=1,format=yuv420p" \
          -c:v "$CODEC" -b:v "$BITRATE" -r "$FPS" \
          -c:a aac -b:a 128k \
          -pix_fmt yuv420p -movflags +faststart \
          "$outf" -loglevel warning
        ;;

      diagonal)
        # 双水印: wm1 stays top, wm2 stays bottom, x swaps diagonally
        [ -z "$WM_FILE2" ] && die "Diagonal mode requires --wmfile2"
        [ -f "$WM_FILE2" ] || die "Second watermark not found: $WM_FILE2"
        local half_cycle=$wm_dur
        local full_cycle=$((wm_dur * 2))
        # Phase 1: wm1=TL, wm2=BR  |  Phase 2: wm1=TR, wm2=BL
        ffmpeg -y -i "$f" -stream_loop -1 -i "$WM_FILE" -stream_loop -1 -i "$WM_FILE2" \
          -filter_complex "[0:v]${scale_filter},setsar=1[main];\
[1:v]scale=${wm_scale}:-1[wm1];[2:v]scale=${wm_scale}:-1[wm2];\
[main][wm1]overlay=x='if(lt(mod(t,$full_cycle),$half_cycle),0,W-w)':y=0:shortest=1[tmp];\
[tmp][wm2]overlay=x='if(lt(mod(t,$full_cycle),$half_cycle),W-w,0)':y=H-h:shortest=1,format=yuv420p" \
          -c:v "$CODEC" -b:v "$BITRATE" -r "$FPS" \
          -c:a aac -b:a 128k \
          -pix_fmt yuv420p -movflags +faststart \
          "$outf" -loglevel warning
        ;;

      *) die "Unknown watermark mode: $WM_MODE";;
    esac

    ok "$name → $(basename "$outf")"
    # Post-process compression if requested
    if [ "$COMPRESS" -eq 1 ] && [ "$TARGET_SIZE_MB" -gt 0 ]; then
      compress_to_size "$outf" "$TARGET_SIZE_MB"
    fi
    count=$((count+1))
  done 3< <(find_videos "$INPUT")

  ok "Watermark complete: $count videos (mode=$WM_MODE)"
}

# ═══ DELOGO ═══
cmd_delogo() {
  [ -z "$OUTPUT" ] && OUTPUT="${INPUT}/已处理"
  ensure_outdir "$OUTPUT"

  local count=0
  while IFS= read -r f <&3; do
    local name; name=$(basename "$f")
    local base="${name%.*}"
    local outf="$OUTPUT/${base}.mp4"
    local o="$ORIENT"
    [ "$o" = "auto" ] && o=$(detect_orient "$f")

    info "Delogo ($o): $name"

    # Get actual video dimensions
    local vw vh
    vw=$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=p=0 "$f" 2>/dev/null)
    vh=$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 "$f" 2>/dev/null)

    # Scale to standard resolution first, then delogo with fixed coords (matching super_console.sh)
    local scale_filter delogo_str
    if [ "$o" = "portrait" ]; then
      delogo_str="delogo=x=1:y=1:w=304:h=160,delogo=x=415:y=1:w=304:h=160,delogo=x=1:y=1119:w=304:h=160,delogo=x=415:y=1119:w=304:h=160"
      if [ "$vw" -eq 720 ] && [ "$vh" -eq 1280 ]; then
        scale_filter=""
      else
        scale_filter="scale=720:1280,"
      fi
    else
      delogo_str="delogo=x=1:y=1:w=305:h=160,delogo=x=974:y=1:w=305:h=160,delogo=x=1:y=559:w=305:h=160,delogo=x=974:y=559:w=305:h=160"
      if [ "$vw" -eq 1280 ] && [ "$vh" -eq 720 ]; then
        scale_filter=""
      else
        scale_filter="scale=1280:720,"
      fi
    fi

    ffmpeg -y -i "$f" \
      -vf "${scale_filter}${delogo_str}" \
      -c:v "$CODEC" -b:v "$BITRATE" -c:a copy \
      -pix_fmt yuv420p -movflags +faststart \
      "$outf" -loglevel warning

    ok "$name → $(basename "$outf")"
    count=$((count+1))
  done 3< <(find_videos "$INPUT")

  ok "Delogo complete: $count videos"
}

# ═══ CROP ═══
cmd_crop() {
  [ -z "$OUTPUT" ] && OUTPUT="${INPUT}/已处理"
  ensure_outdir "$OUTPUT"

  local count=0
  while IFS= read -r f <&3; do
    local name; name=$(basename "$f")
    local base="${name%.*}"
    local outf="$OUTPUT/${base}.mp4"
    local o="$ORIENT"
    [ "$o" = "auto" ] && o=$(detect_orient "$f")

    local crop_filter
    if [ "$o" = "portrait" ]; then
      # Portrait: crop to 3:4 (720x960)
      crop_filter="crop=iw:'floor(iw*4/3/2)*2'"
    else
      # Landscape: crop to 670:720 ratio
      crop_filter="crop='floor(ih*670/720/2)*2':'floor(ih/2)*2'"
    fi

    info "Crop ($o): $name"

    ffmpeg -y -i "$f" \
      -vf "$crop_filter" \
      -c:v "$CODEC" -b:v "$BITRATE" -c:a copy \
      -pix_fmt yuv420p -movflags +faststart \
      "$outf" -loglevel warning

    ok "$name → $(basename "$outf")"
    count=$((count+1))
  done 3< <(find_videos "$INPUT")

  ok "Crop complete: $count videos"
}

# ═══ BLUR-PAD ═══
cmd_blur_pad() {
  [ -z "$OUTPUT" ] && OUTPUT="${INPUT}/已处理"
  ensure_outdir "$OUTPUT"

  local count=0
  while IFS= read -r f <&3; do
    local name; name=$(basename "$f")
    local base="${name%.*}"
    local outf="$OUTPUT/${base}.mp4"
    local o="$ORIENT"
    [ "$o" = "auto" ] && o=$(detect_orient "$f")

    local tw th
    if [ "$o" = "landscape" ]; then
      tw=1280; th=720
    else
      tw=720; th=1280
    fi

    info "Blur-pad ($o → ${tw}x${th}): $name"

    ffmpeg -y -i "$f" \
      -filter_complex "\
[0:v]scale=${tw}/${BG_SCALE}:${th}/${BG_SCALE},boxblur=${STRENGTH},scale=${tw}:${th}[bg];\
[0:v]scale='if(gt(a,${tw}/${th}),${tw},-2)':'if(gt(a,${tw}/${th}),-2,${th})'[fg];\
[bg][fg]overlay=(W-w)/2:(H-h)/2" \
      -c:v "$CODEC" -b:v "$BITRATE" -c:a aac -b:a 128k \
      -pix_fmt yuv420p -movflags +faststart \
      "$outf" -loglevel warning

    ok "$name → $(basename "$outf")"
    count=$((count+1))
  done 3< <(find_videos "$INPUT")

  ok "Blur-pad complete: $count videos"
}

# ═══ TRIM ═══
cmd_trim() {
  [ -z "$OUTPUT" ] && OUTPUT="${INPUT}/已处理"
  ensure_outdir "$OUTPUT"

  local count=0
  while IFS= read -r f <&3; do
    local name; name=$(basename "$f")
    local base="${name%.*}"
    local ext="${name##*.}"
    local outf="$OUTPUT/${base}.${ext}"
    local dur; dur=$(get_duration "$f")

    [ -z "$dur" ] && { info "Skip (can't read duration): $name"; continue; }

    local new_dur=$((dur - TRIM_START - TRIM_END))
    [ "$new_dur" -lt "$MIN_LENGTH" ] && { info "Skip (too short after trim: ${new_dur}s < ${MIN_LENGTH}s): $name"; continue; }

    info "Trim: $name (${dur}s → ${new_dur}s, cut head=${TRIM_START}s tail=${TRIM_END}s)"

    if [ "$TRIM_MODE" = "copy" ]; then
      ffmpeg -y -ss "$TRIM_START" -i "$f" -t "$new_dur" \
        -c copy -movflags +faststart \
        "$outf" -loglevel warning
    else
      ffmpeg -y -ss "$TRIM_START" -i "$f" -t "$new_dur" \
        -c:v "$CODEC" -b:v "$BITRATE" -c:a aac -b:a 128k \
        -pix_fmt yuv420p -movflags +faststart \
        "$outf" -loglevel warning
    fi

    ok "$name → $(basename "$outf")"
    count=$((count+1))
  done 3< <(find_videos "$INPUT")

  ok "Trim complete: $count videos"
}

# ═══ ADD INTRO/OUTRO ═══
cmd_add_intro_outro() {
  [ -z "$INTRO_FILE" ] && [ -z "$OUTRO_FILE" ] && die "Need at least --intro or --outro"
  [ -n "$INTRO_FILE" ] && [ ! -f "$INTRO_FILE" ] && die "Intro file not found: $INTRO_FILE"
  [ -n "$OUTRO_FILE" ] && [ ! -f "$OUTRO_FILE" ] && die "Outro file not found: $OUTRO_FILE"
  [ -z "$OUTPUT" ] && OUTPUT="${INPUT}/已处理"
  ensure_outdir "$OUTPUT"

  local tmp_dir; tmp_dir=$(mktemp -d /tmp/intro_outro_XXXXXX)

  local count=0
  while IFS= read -r f <&3; do
    local name; name=$(basename "$f")
    local base="${name%.*}"
    local outf="$OUTPUT/${base}.mp4"

    info "Add intro/outro: $name"

    # Collect all files to determine smart target
    local -a all_files=("$f")
    [ -n "$INTRO_FILE" ] && all_files+=("$INTRO_FILE")
    [ -n "$OUTRO_FILE" ] && all_files+=("$OUTRO_FILE")
    calc_smart_target "${all_files[@]}"
    local tw=$SMART_TW th=$SMART_TH
    local scale_vf="scale=${tw}:${th}:force_original_aspect_ratio=decrease,pad=${tw}:${th}:(ow-iw)/2:(oh-ih)/2,setsar=1"

    # Encode all to same format (libx264 CRF, matching merge_videos.py)
    local intro_enc="" outro_enc=""
    if [ -n "$INTRO_FILE" ]; then
      intro_enc="$tmp_dir/intro_enc.mp4"
      ffmpeg -y -i "$INTRO_FILE" \
        -vf "$scale_vf" \
        -c:v libx264 -preset fast -crf 23 -c:a aac \
        -movflags +faststart \
        "$intro_enc" -loglevel warning
    fi
    if [ -n "$OUTRO_FILE" ]; then
      outro_enc="$tmp_dir/outro_enc.mp4"
      ffmpeg -y -i "$OUTRO_FILE" \
        -vf "$scale_vf" \
        -c:v libx264 -preset fast -crf 23 -c:a aac \
        -movflags +faststart \
        "$outro_enc" -loglevel warning
    fi

    local main_enc="$tmp_dir/main_enc.mp4"
    ffmpeg -y -i "$f" \
      -vf "$scale_vf" \
      -c:v libx264 -preset fast -crf 23 -c:a aac \
      -movflags +faststart \
      "$main_enc" -loglevel warning

    # Build concat list
    local list_file="$tmp_dir/concat.txt"
    > "$list_file"
    [ -n "$intro_enc" ] && echo "file '$intro_enc'" >> "$list_file"
    echo "file '$main_enc'" >> "$list_file"
    [ -n "$outro_enc" ] && echo "file '$outro_enc'" >> "$list_file"

    ffmpeg -y -f concat -safe 0 -i "$list_file" \
      -c copy -movflags +faststart \
      "$outf" -loglevel warning

    ok "$name → $(basename "$outf")"
    count=$((count+1))
  done 3< <(find_videos "$INPUT")

  rm -rf "$tmp_dir"
  ok "Add intro/outro complete: $count videos"
}

# ═══ CONCAT ═══
cmd_concat() {
  [ -z "$OUTPUT" ] && OUTPUT="${INPUT}/已处理/merged.mp4"
  local outdir; outdir=$(dirname "$OUTPUT")
  ensure_outdir "$outdir"

  # Collect video files
  local -a vfiles=()
  while IFS= read -r f <&3; do
    vfiles+=("$f")
  done 3< <(find_videos "$INPUT")

  local count=${#vfiles[@]}
  [ "$count" -eq 0 ] && die "No videos found in $INPUT"

  info "Concat: $count videos → $OUTPUT (method=$CONCAT_METHOD, scale=$CONCAT_SCALE)"

  if [ "$CONCAT_METHOD" = "demuxer" ] && [ "$CONCAT_SCALE" = "first" ]; then
    # Fast demuxer concat (only works well for same-format videos)
    local list_file; list_file=$(mktemp /tmp/concat_XXXXXX.txt)
    for f in "${vfiles[@]}"; do
      echo "file '$(realpath "$f")'" >> "$list_file"
    done
    ffmpeg -y -f concat -safe 0 -i "$list_file" \
      -c copy -movflags +faststart \
      "$OUTPUT" -loglevel warning
    rm -f "$list_file"
  else
    # Smart resolution: detect orientations and pick best 720p base
    local tw th
    case "$CONCAT_SCALE" in
      720p)  tw=1280; th=720;;
      1080p) tw=1920; th=1080;;
      *)
        calc_smart_target "${vfiles[@]}"
        tw=$SMART_TW; th=$SMART_TH
        ;;
    esac

    info "Target resolution: ${tw}x${th}"

    # Build filter_complex string (exactly matching merge_videos.py)
    # IMPORTANT: only process video in filter, reference audio streams directly
    # to avoid bash glob expansion issue with [$n:a] bracket patterns
    local -a cmd_args=(-y)
    local filter="" stream_list=""
    local n=0
    for f in "${vfiles[@]}"; do
      cmd_args+=(-i "$f")
      filter="${filter}[${n}:v]scale=${tw}:${th}:force_original_aspect_ratio=decrease,pad=${tw}:${th}:(ow-iw)/2:(oh-ih)/2,setsar=1[v${n}]; "
      stream_list="${stream_list}[v${n}][${n}:a]"
      n=$((n+1))
    done
    filter="${filter}${stream_list}concat=n=${count}:v=1:a=1[outv][outa]"

    # Use -filter_complex directly (matching merge_videos.py approach)
    ffmpeg "${cmd_args[@]}" \
      -filter_complex "${filter}" \
      -map "[outv]" -map "[outa]" \
      -c:v libx264 -preset fast -crf 23 \
      -c:a aac \
      -movflags +faststart \
      "$OUTPUT" -loglevel warning
  fi

  ok "Concat complete: $count videos → $OUTPUT"
}

# ═══ Dispatch ═══
case "$CMD" in
  watermark)  cmd_watermark;;
  delogo)     cmd_delogo;;
  crop)       cmd_crop;;
  blur-pad)   cmd_blur_pad;;
  trim)       cmd_trim;;
  add-intro-outro) cmd_add_intro_outro;;
  concat)     cmd_concat;;
  help|*)
    echo "OmniPublish Video Processor"
    echo "Usage: bash video_process.sh <command> [options]"
    echo ""
    echo "Commands:"
    echo "  watermark        MOV 四角轮转水印"
    echo "  delogo           遮盖四角水印 (delogo filter)"
    echo "  crop             裁掉四角水印"
    echo "  blur-pad         虚化填充到标准尺寸"
    echo "  trim             去片头片尾"
    echo "  add-intro-outro  加片头片尾（720p 拼接）"
    echo "  concat           多视频合成"
    echo ""
    echo "Common options:"
    echo "  --input DIR      输入文件夹 (required)"
    echo "  --output DIR     输出文件夹 (default: input/已处理)"
    echo "  --codec CODEC    编码器 (default: h264_videotoolbox / libx264)"
    echo "  --bitrate RATE   码率 (default: 2M)"
    echo "  --orient MODE    方向: auto/portrait/landscape (default: auto)"
    ;;
esac
