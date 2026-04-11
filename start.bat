@echo off
:: OmniPublish V2.0 — Windows 一键启动脚本（开发模式）
echo =============================================
echo     OmniPublish V2.0 启动中
echo =============================================

cd /d "%~dp0"

:: 1. 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 未安装
    pause
    exit /b 1
)

:: 2. 检查虚拟环境
if not exist "backend\venv" (
    echo [SETUP] 创建 Python 虚拟环境...
    python -m venv backend\venv
)

call backend\venv\Scripts\activate.bat

:: 3. 安装依赖
echo [SETUP] 安装 Python 依赖...
pip install -q -r backend\requirements.txt

:: 4. 初始化数据库
echo [SETUP] 初始化数据库...
cd backend
python -c "from database import init_db; import asyncio; asyncio.run(init_db())"
python migrations\002_seed_platforms.py

:: 5. 启动
echo.
echo [OK] 启动后端服务...
echo [OK] API:  http://127.0.0.1:9527
echo [OK] Docs: http://127.0.0.1:9527/docs
echo [OK] 默认账号: admin / admin123
echo.

python main.py --reload
pause
