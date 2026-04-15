#!/bin/bash
# OmniPublish V2.0 — 单机版启动脚本（Mac/Linux）
set -e

echo "============================================"
echo "  OmniPublish V2.0 — 单机版启动器"
echo "============================================"
echo ""

cd "$(dirname "$0")"

# ── 检查 Python ──
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] 未找到 Python3，请先安装 Python 3.10+"
    echo "        Mac: brew install python3"
    echo "        Ubuntu: sudo apt install python3 python3-venv"
    exit 1
fi
PY_VER=$(python3 --version 2>&1)
echo "[OK] $PY_VER"

# ── 创建虚拟环境（首次） ──
if [ ! -d "venv" ]; then
    echo "[SETUP] 首次运行，创建虚拟环境..."
    python3 -m venv venv
fi
source venv/bin/activate

# ── 安装依赖 ──
echo "[SETUP] 检查依赖..."
pip install -q -r backend/requirements.txt
echo "[OK] 依赖就绪"

# ── 确保 data 目录存在 ──
mkdir -p data

# ── 首次运行复制配置 ──
if [ ! -f "config.json" ] && [ -f "config.json.example" ]; then
    echo "[SETUP] 首次运行，复制配置文件..."
    cp config.json.example config.json
    echo "[INFO] 已创建 config.json（AI 文案功能需填写 api_key）"
fi

# ── 检查 FFmpeg ──
if command -v ffmpeg &>/dev/null; then
    echo "[OK] FFmpeg 已安装"
else
    echo "[WARN] 未找到 FFmpeg（视频水印功能不可用）"
    echo "       Mac: brew install ffmpeg"
    echo "       Ubuntu: sudo apt install ffmpeg"
fi

# ── 启动 ──
echo ""
echo "[START] 启动 OmniPublish..."
echo "        访问: http://localhost:9527"
echo "        账号: admin / admin123"
echo "        按 Ctrl+C 停止服务"
echo ""

cd backend
python3 main.py
