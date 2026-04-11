#!/bin/bash
# OmniPublish V2.0 — 一键启动脚本（开发模式）
set -e

echo "╔══════════════════════════════════════╗"
echo "║      OmniPublish V2.0 启动中         ║"
echo "╚══════════════════════════════════════╝"

cd "$(dirname "$0")"

# 1. 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python3 未安装"
    exit 1
fi

# 2. 检查虚拟环境
if [ ! -d "backend/venv" ]; then
    echo "[SETUP] 创建 Python 虚拟环境..."
    python3 -m venv backend/venv
fi

source backend/venv/bin/activate

# 3. 安装依赖
echo "[SETUP] 安装 Python 依赖..."
pip install -q -r backend/requirements.txt

# 4. 初始化数据库 + 种子数据
echo "[SETUP] 初始化数据库..."
cd backend
python -c "from database import init_db; import asyncio; asyncio.run(init_db())"
python migrations/002_seed_platforms.py

# 5. 启动后端
echo ""
echo "[OK] 启动后端服务..."
echo "[OK] API:  http://127.0.0.1:9527"
echo "[OK] Docs: http://127.0.0.1:9527/docs"
echo "[OK] 默认账号: admin / admin123"
echo ""

python main.py --reload
