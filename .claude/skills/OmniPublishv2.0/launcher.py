#!/usr/bin/env python3
"""OmniPublish V2.0 — 技能启动器

从技能目录自动推导项目根目录，完成全套初始化并后台启动服务。

用法:
    python launcher.py          # 启动（如已运行则跳过）
    python launcher.py stop     # 停止
    python launcher.py status   # 状态检查
    python launcher.py restart  # 重启
"""

import os
import sys
import subprocess
import time
import shutil
import signal
from pathlib import Path

# ── 路径推导（自适应任意机器）──
# 技能路径: {project}/.claude/skills/OmniPublishv2.0/launcher.py
SKILL_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SKILL_DIR.parent.parent.parent      # 上三级 = 项目根
BACKEND_DIR = PROJECT_DIR / "backend"
FRONTEND_DIR = PROJECT_DIR / "frontend"
VENV_DIR = PROJECT_DIR / "venv"
LOG_DIR = PROJECT_DIR / "logs"
LOG_FILE = LOG_DIR / "server.log"
PID_FILE = LOG_DIR / "server.pid"
PORT = 9527

# 平台判断
IS_WIN = sys.platform == "win32"
PYTHON = VENV_DIR / ("Scripts/python.exe" if IS_WIN else "bin/python3")
PIP = VENV_DIR / ("Scripts/pip.exe" if IS_WIN else "bin/pip")


# ══════════════════════════════════════
# 工具函数
# ══════════════════════════════════════

def check_server() -> bool:
    """检查服务是否在运行。"""
    import urllib.request
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/ping", timeout=2)
        return True
    except Exception:
        return False


def read_pid() -> int | None:
    if PID_FILE.exists():
        try:
            return int(PID_FILE.read_text().strip())
        except Exception:
            pass
    return None


def is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def run(cmd: list, **kwargs) -> subprocess.CompletedProcess:
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    return subprocess.run(cmd, **kwargs)


# ══════════════════════════════════════
# 操作
# ══════════════════════════════════════

def setup_venv():
    """创建虚拟环境（首次）。"""
    if VENV_DIR.exists():
        return
    print("[SETUP] 创建 Python 虚拟环境...")
    run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)


def install_deps():
    """安装 Python 依赖。"""
    req = BACKEND_DIR / "requirements.txt"
    print("[SETUP] 检查 Python 依赖...")
    run([str(PIP), "install", "-q", "-r", str(req)], check=True)


def build_frontend():
    """构建 Vue 前端（仅首次或 dist/ 不存在时）。"""
    dist = FRONTEND_DIR / "dist"
    if dist.exists() and any(dist.iterdir()):
        return  # 已构建

    print("[BUILD] 构建前端（首次约 1-2 分钟）...")

    # 检查 npm
    npm = shutil.which("npm")
    if not npm:
        print("[ERROR] 未找到 npm，请安装 Node.js: https://nodejs.org/")
        sys.exit(1)

    node_modules = FRONTEND_DIR / "node_modules"
    if not node_modules.exists():
        print("[BUILD] npm install...")
        run([npm, "install", "--legacy-peer-deps"], cwd=str(FRONTEND_DIR), check=True)

    run([npm, "run", "build"], cwd=str(FRONTEND_DIR), check=True)
    print("[BUILD] 前端构建完成")


def ensure_config():
    """首次运行复制配置文件。"""
    cfg = PROJECT_DIR / "config.json"
    example = PROJECT_DIR / "config.json.example"
    if not cfg.exists() and example.exists():
        shutil.copy(example, cfg)
        print("[SETUP] 已创建 config.json（AI 文案功能需填写 api_key）")


def start():
    """启动服务（后台运行）。"""
    if check_server():
        print(f"[OK] OmniPublish 已在运行 → http://127.0.0.1:{PORT}")
        return

    # 初始化
    setup_venv()
    install_deps()
    build_frontend()
    ensure_config()

    # 确保日志目录
    LOG_DIR.mkdir(exist_ok=True)

    print("[START] 后台启动 OmniPublish...")
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        kwargs = dict(stdout=f, stderr=f, cwd=str(BACKEND_DIR))
        if IS_WIN:
            kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        proc = subprocess.Popen([str(PYTHON), "main.py"], **kwargs)

    PID_FILE.write_text(str(proc.pid))

    # 等待就绪（最多 15 秒）
    print("[START] 等待服务就绪", end="", flush=True)
    for _ in range(15):
        time.sleep(1)
        print(".", end="", flush=True)
        if check_server():
            print()
            print(f"[OK] OmniPublish 已启动 (PID {proc.pid})")
            print(f"[OK] 访问地址: http://127.0.0.1:{PORT}")
            print(f"[OK] 账号: admin / admin123")
            print(f"[OK] 日志: {LOG_FILE}")
            return

    print()
    print(f"[WARN] 启动超时，请查看日志: {LOG_FILE}")


def stop():
    """停止服务。"""
    pid = read_pid()
    if pid and is_pid_alive(pid):
        print(f"[STOP] 停止 OmniPublish (PID {pid})...")
        try:
            if IS_WIN:
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=True)
            else:
                os.kill(pid, signal.SIGTERM)
            time.sleep(1)
            print("[OK] 服务已停止")
        except Exception as e:
            print(f"[ERROR] 停止失败: {e}")
    else:
        if check_server():
            print("[WARN] 服务在运行但找不到 PID 文件，请手动停止")
        else:
            print("[OK] 服务未运行")

    if PID_FILE.exists():
        PID_FILE.unlink()


def status():
    """显示服务状态。"""
    running = check_server()
    pid = read_pid()
    print(f"  服务状态: {'运行中' if running else '已停止'}")
    if pid:
        alive = is_pid_alive(pid)
        print(f"  PID: {pid} ({'存活' if alive else '已退出'})")
    print(f"  地址: http://127.0.0.1:{PORT}")
    print(f"  项目: {PROJECT_DIR}")
    print(f"  数据库: {PROJECT_DIR / 'data' / 'omnipub.db'}")
    dist = FRONTEND_DIR / "dist"
    print(f"  前端构建: {'已构建' if dist.exists() and any(dist.iterdir()) else '未构建'}")


# ══════════════════════════════════════
# 主入口
# ══════════════════════════════════════

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "start"

    if cmd == "start":
        start()
    elif cmd == "stop":
        stop()
    elif cmd == "restart":
        stop()
        time.sleep(1)
        start()
    elif cmd == "status":
        status()
    else:
        print(f"用法: python launcher.py [start|stop|restart|status]")
        sys.exit(1)
