@echo off
chcp 65001 >nul
title OmniPublish V2.0

echo ============================================
echo   OmniPublish V2.0 — 单机版启动器
echo ============================================
echo.

cd /d "%~dp0"

:: ── 检查 Python ──
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 未找到 Python，请先安装 Python 3.10+
    echo         下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [OK] Python %PY_VER%

:: ── 创建虚拟环境（首次） ──
if not exist "venv\Scripts\activate.bat" (
    echo [SETUP] 首次运行，创建虚拟环境...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] 创建虚拟环境失败
        pause
        exit /b 1
    )
)
call venv\Scripts\activate.bat

:: ── 安装依赖 ──
echo [SETUP] 检查依赖...
pip install -q -r backend\requirements.txt
if errorlevel 1 (
    echo [ERROR] 依赖安装失败，请检查网络
    pause
    exit /b 1
)
echo [OK] 依赖就绪

:: ── 确保 data 目录存在 ──
if not exist "data" mkdir data

:: ── 首次运行复制配置 ──
if not exist "config.json" (
    if exist "config.json.example" (
        echo [SETUP] 首次运行，复制配置文件...
        copy "config.json.example" "config.json" >nul
        echo [INFO] 已创建 config.json（AI 文案功能需填写 api_key）
    )
)

:: ── 启动 ──
echo.
echo [START] 启动 OmniPublish...
echo         访问: http://localhost:9527
echo         账号: admin / admin123
echo         按 Ctrl+C 停止服务
echo.

cd backend
python main.py

pause
