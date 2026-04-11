#!/usr/bin/env python3
"""OmniPublish V2.0 Local Server — REST API 架构

改进点:
- REST 资源路由（/api/tasks, /api/platforms, /api/watermark 等）
- Token 认证（从 config.json 读取）
- 请求大小限制（防 DoS）
- 文件上传大小限制
- 路径安全校验增强
- SSE 流式任务进度

启动:
    python3 server.py              # 默认端口 9527
    python3 server.py --port 8080  # 自定义端口
"""

import http.server, json, subprocess, os, sys, signal, argparse, time
import threading, platform, tempfile, shlex, hashlib
from pathlib import Path

SKILL_DIR = str(Path(__file__).resolve().parent)
SCRIPTS_DIR = Path(SKILL_DIR)

MAX_BODY_SIZE = 10 * 1024 * 1024   # 10MB 请求体限制
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB 文件上传限制

# ── Security: only these scripts are allowed to execute ──
ALLOWED_SCRIPTS = {
    "copywrite_gen.py", "make_cover.py", "image_rename.py",
    "image_watermark.py", "video_process.py", "publish_api.py",
}

# ── 配置加载 ──
def _load_config():
    config_file = Path(SKILL_DIR).parent / "config.json"
    if config_file.exists():
        with open(config_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

CONFIG = _load_config()
AUTH_TOKEN = CONFIG.get("server", {}).get("auth_token", "")
ALLOWED_ORIGINS = CONFIG.get("server", {}).get("allowed_origins", ["*"])

# Find the HTML file
HTML_FILE = None
for f in Path(SKILL_DIR).parent.iterdir():
    if f.suffix == ".html" and "omni" in f.name.lower():
        HTML_FILE = f
        break
if not HTML_FILE:
    for f in Path(SKILL_DIR).iterdir():
        if f.suffix == ".html" and "omni" in f.name.lower():
            HTML_FILE = f
            break


def _parse_and_validate_cmd(cmd_str):
    """Parse and validate command — only allowed scripts can execute."""
    cmd_str = cmd_str.replace("~/", os.path.expanduser("~/"))
    cmd_str = cmd_str.replace("\\\n", " ")

    for ch in [";", "|", "&&", "||", "`", "$(", ">", "<", "\n"]:
        if ch in cmd_str:
            return None, f"Rejected: shell metacharacter '{ch}' not allowed"

    try:
        parts = shlex.split(cmd_str)
    except ValueError as e:
        return None, f"Command parse error: {e}"

    if not parts:
        return None, "Empty command"

    script_idx = None
    for i, part in enumerate(parts):
        if part.endswith(".py"):
            script_idx = i
            break

    if script_idx is None:
        return None, "Rejected: only Python script execution is allowed"

    script_path = Path(parts[script_idx])

    try:
        resolved = script_path.resolve(strict=False)
        scripts_resolved = SCRIPTS_DIR.resolve(strict=False)
        if not str(resolved).startswith(str(scripts_resolved) + os.sep) and resolved.parent != scripts_resolved:
            return None, f"Rejected: script not in {SCRIPTS_DIR}"
    except Exception:
        return None, "Rejected: invalid script path"

    if script_path.name not in ALLOWED_SCRIPTS:
        return None, f"Rejected: '{script_path.name}' not in allowed scripts"

    if not resolved.exists():
        return None, f"Script not found: {resolved}"

    cmd_list = [sys.executable, str(resolved)] + parts[script_idx + 1:]
    return cmd_list, None


class OmniHandler(http.server.SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=SKILL_DIR, **kwargs)

    # ── 认证检查 ──
    def _check_auth(self):
        """验证 Bearer Token。如果未配置 auth_token 则跳过检查。"""
        if not AUTH_TOKEN:
            return True
        auth_header = self.headers.get("Authorization", "")
        if auth_header == f"Bearer {AUTH_TOKEN}":
            return True
        self._json(401, {"error": "Unauthorized. Provide Authorization: Bearer <token>"})
        return False

    # ── GET ──
    def do_GET(self):
        if self.path == "/":
            self._serve_html()
        elif self.path == "/api/info":
            if not self._check_auth(): return
            self._json(200, {"skill_dir": SKILL_DIR, "version": "2.0", "platform": platform.system()})
        elif self.path == "/api/ping":
            self._json(200, {"ok": True})
        elif self.path == "/api/platforms":
            if not self._check_auth(): return
            self._handle_list_platforms()
        else:
            super().do_GET()

    # ── POST ──
    def do_POST(self):
        # REST API 路由
        routes = {
            "/api/run":           self._handle_run,
            "/api/stop":          self._handle_stop,
            "/api/pick-folder":   self._handle_pick_folder,
            "/api/find-path":     self._handle_find_path,
            "/api/upload-file":   self._handle_upload_file,
            "/api/prepare-files": self._handle_prepare_files,
            "/api/save-file":     self._handle_save_file,
            # V2.0 新增 REST 端点
            "/api/copywrite":     self._handle_copywrite,
            "/api/rename":        self._handle_rename,
            "/api/cover":         self._handle_cover,
            "/api/watermark":     self._handle_watermark,
        }
        handler = routes.get(self.path)
        if handler:
            if not self._check_auth():
                return
            handler()
        else:
            self._json(404, {"error": "not found"})

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    # ── V2.0 REST 端点 ──

    def _handle_list_platforms(self):
        """GET /api/platforms — 返回所有业务线配置（从 config 或数据库）"""
        # 暂从内存返回，后续改为数据库
        self._json(200, {"platforms": [], "total": 0, "_hint": "TODO: 连接数据库"})

    def _handle_copywrite(self):
        """POST /api/copywrite — 触发 AI 文案生成（SSE 流式返回）"""
        body = self._read_body()
        protagonist = body.get("protagonist", "")
        event = body.get("event", "")
        style = body.get("style", "反转打脸风")
        category = body.get("category", "今日吃瓜")

        if not protagonist or not event:
            self._json(400, {"error": "需要 protagonist 和 event 字段"})
            return

        cmd_str = (
            f'python3 copywrite_gen.py --protagonist "{protagonist}" '
            f'--event "{event}" --style "{style}" --category "{category}"'
        )
        cmd_list, err = _parse_and_validate_cmd(cmd_str)
        if err:
            self._json(403, {"error": err})
            return
        self._run_sse(cmd_list)

    def _handle_rename(self):
        """POST /api/rename — 触发图片重命名"""
        body = self._read_body()
        folder = body.get("folder", "")
        prefix = body.get("prefix", "image")
        dry_run = body.get("dry_run", False)

        if not folder:
            self._json(400, {"error": "需要 folder 字段"})
            return

        cmd_str = f'python3 image_rename.py --folder "{folder}" --prefix "{prefix}"'
        if dry_run:
            cmd_str += " --dry-run"

        cmd_list, err = _parse_and_validate_cmd(cmd_str)
        if err:
            self._json(403, {"error": err})
            return
        self._run_sse(cmd_list)

    def _handle_cover(self):
        """POST /api/cover — 触发封面生成"""
        body = self._read_body()
        folder = body.get("folder", "")
        layout = body.get("layout", "triple")
        candidates = body.get("candidates", 3)

        if not folder:
            self._json(400, {"error": "需要 folder 字段"})
            return

        cmd_str = f'python3 make_cover.py --folder "{folder}" --layout {layout} --candidates {candidates}'
        cmd_list, err = _parse_and_validate_cmd(cmd_str)
        if err:
            self._json(403, {"error": err})
            return
        self._run_sse(cmd_list)

    def _handle_watermark(self):
        """POST /api/watermark — 触发水印处理"""
        body = self._read_body()
        folder = body.get("folder", "")
        watermark = body.get("watermark", "")
        position = body.get("position", "bottom-right")

        if not folder or not watermark:
            self._json(400, {"error": "需要 folder 和 watermark 字段"})
            return

        cmd_str = f'python3 image_watermark.py --folder "{folder}" --watermark "{watermark}" --position {position}'
        cmd_list, err = _parse_and_validate_cmd(cmd_str)
        if err:
            self._json(403, {"error": err})
            return
        self._run_sse(cmd_list)

    # ── 原有处理函数（保留兼容） ──

    def _serve_html(self):
        if not HTML_FILE or not HTML_FILE.exists():
            self._json(404, {"error": "HTML file not found"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self._cors()
        self.end_headers()
        self.wfile.write(HTML_FILE.read_bytes())

    def _handle_run(self):
        body = self._read_body()
        cmd_str = body.get("cmd", "")
        if not cmd_str:
            self._json(400, {"error": "no command"})
            return
        cmd_list, err = _parse_and_validate_cmd(cmd_str)
        if err:
            self._json(403, {"error": err})
            return
        self._run_sse(cmd_list)

    def _run_sse(self, cmd_list):
        """SSE 流式执行命令。"""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self._cors()
        self.end_headers()

        try:
            proc = subprocess.Popen(
                cmd_list,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            with self.server._pid_lock:
                self.server._current_pids.add(proc.pid)

            for line in iter(proc.stdout.readline, ""):
                self._sse({"line": line.rstrip("\n")})

            proc.wait()
            with self.server._pid_lock:
                self.server._current_pids.discard(proc.pid)
            self._sse({"done": True, "code": proc.returncode})
        except Exception as e:
            self._sse({"done": True, "code": -1, "error": str(e)})

    def _handle_stop(self):
        with self.server._pid_lock:
            pids = list(self.server._current_pids)
        if pids:
            stopped = []
            for pid in pids:
                try:
                    if platform.system() == "Windows":
                        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
                    else:
                        os.kill(pid, signal.SIGTERM)
                    stopped.append(pid)
                except (ProcessLookupError, OSError):
                    pass
            with self.server._pid_lock:
                self.server._current_pids -= set(stopped)
            self._json(200, {"stopped": True, "pids": stopped})
        else:
            self._json(200, {"stopped": False, "msg": "no running process"})

    def _handle_pick_folder(self):
        body = self._read_body()
        files = body.get("files", [])
        if not files:
            self._json(200, {"path": ""})
            return
        target = files[0]
        fname = target.get("name", "")
        fsize = target.get("size", -1)
        if not fname:
            self._json(200, {"path": ""})
            return
        search_dirs = _get_search_dirs()
        for d in search_dirs:
            if not d.exists():
                continue
            for depth in [fname, f"*/{fname}", f"*/*/{fname}"]:
                for match in d.glob(depth):
                    if fsize >= 0 and match.is_file() and match.stat().st_size != fsize:
                        continue
                    folder = str(match.parent) if match.is_file() else str(match)
                    self._json(200, {
                        "path": folder, "file": str(match),
                        "files": [f.name for f in match.parent.iterdir()
                                  if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov"}]
                    })
                    return
        self._json(200, {"path": "", "files": []})

    def _handle_find_path(self):
        body = self._read_body()
        name = body.get("name", "")
        if not name:
            self._json(400, {"error": "no filename"})
            return
        search_dirs = _get_search_dirs()
        for d in search_dirs:
            if not d.exists():
                continue
            for depth_glob in [name, f"*/{name}", f"*/*/{name}"]:
                matches = list(d.glob(depth_glob))
                if matches:
                    match = matches[0]
                    folder = str(match) if match.is_dir() else str(match.parent)
                    self._json(200, {"path": folder, "file": str(match)})
                    return
        self._json(200, {"path": "", "total": 0})

    def _handle_upload_file(self):
        body = self._read_body()
        name = body.get("name", "")
        data_b64 = body.get("data", "")
        if not name or not data_b64:
            self._json(400, {"error": "need name and data"})
            return

        import base64
        try:
            raw = base64.b64decode(data_b64)
        except Exception:
            self._json(400, {"error": "invalid base64"})
            return

        # 大小限制
        if len(raw) > MAX_UPLOAD_SIZE:
            self._json(413, {"error": f"File too large (max {MAX_UPLOAD_SIZE // 1024 // 1024}MB)"})
            return

        # 文件名安全检查
        safe_name = Path(name).name  # 去除路径分隔符
        upload_dir = Path(SKILL_DIR) / "uploads"
        upload_dir.mkdir(exist_ok=True)
        dest = upload_dir / safe_name
        with open(dest, "wb") as f:
            f.write(raw)
        self._json(200, {"file": str(dest), "size": len(raw)})

    def _handle_prepare_files(self):
        body = self._read_body()
        folder = body.get("folder", "")
        files = body.get("files", [])
        if not folder or not files:
            self._json(400, {"error": "need folder and files"})
            return
        folder_path = Path(folder)
        if not folder_path.is_dir():
            self._json(400, {"error": f"folder not found: {folder}"})
            return
        tmp_base = Path(SKILL_DIR) / "tmp"
        tmp_base.mkdir(exist_ok=True)
        tmp_dir = Path(tempfile.mkdtemp(dir=tmp_base))
        linked = []
        for fname in files:
            src = folder_path / fname
            if src.exists():
                dst = tmp_dir / fname
                try:
                    os.symlink(src, dst)
                    linked.append(fname)
                except OSError:
                    import shutil
                    shutil.copy2(str(src), str(dst))
                    linked.append(fname)
        self._json(200, {"path": str(tmp_dir), "files": linked, "count": len(linked)})

    def _handle_save_file(self):
        body = self._read_body()
        file_path = body.get("path", "")
        content = body.get("content", "")
        if not file_path:
            self._json(400, {"error": "need path"})
            return
        try:
            p = Path(os.path.expanduser(file_path)).resolve()
            # 安全检查：只允许写入 home 目录（防止 symlink 逃逸）
            home = Path.home().resolve()
            if not str(p).startswith(str(home) + os.sep) and p.parent != home:
                self._json(403, {"error": "Writing outside home directory is not allowed"})
                return
            # 额外检查：解析后的路径是否仍在 home 下（防 symlink）
            if p.exists() and p.is_symlink():
                real = p.resolve()
                if not str(real).startswith(str(home) + os.sep):
                    self._json(403, {"error": "Symlink target outside home directory"})
                    return
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            self._json(200, {"saved": str(p)})
        except Exception as e:
            self._json(500, {"error": str(e)})

    # ── Helpers ──

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_BODY_SIZE:
            self._json(413, {"error": f"Request too large (max {MAX_BODY_SIZE // 1024}KB)"})
            return {}
        return json.loads(self.rfile.read(length)) if length else {}

    def _json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _sse(self, data):
        try:
            self.wfile.write(f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()
        except BrokenPipeError:
            pass

    def _cors(self):
        origin = self.headers.get("Origin", "*")
        if ALLOWED_ORIGINS == ["*"] or origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
        else:
            self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGINS[0])
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def log_message(self, fmt, *args):
        req = args[0] if args else ""
        if any(req.startswith(p) for p in ["GET /api/ping", "GET /scripts/", "OPTIONS"]):
            return
        sys.stderr.write(f"[OmniPublish] {fmt % args}\n")


def _get_search_dirs():
    home = Path.home()
    skill_parent = Path(SKILL_DIR).parent
    dirs = [
        skill_parent, Path(SKILL_DIR),
        home / "Desktop", home / "Downloads", home / "Documents",
        home,
    ]
    if platform.system() == "Darwin":
        dirs.append(Path("/Users/Shared"))
    elif platform.system() == "Windows":
        dirs.append(Path(os.environ.get("PUBLIC", r"C:\Users\Public")))
    return dirs


def main():
    parser = argparse.ArgumentParser(description="OmniPublish V2.0 Local Server")
    parser.add_argument("--port", type=int, default=CONFIG.get("server", {}).get("port", 9527))
    args = parser.parse_args()

    print(f"[OmniPublish] Server starting...")
    print(f"[OmniPublish] URL:       http://127.0.0.1:{args.port}")
    print(f"[OmniPublish] Skill dir: {SKILL_DIR}")
    print(f"[OmniPublish] Auth:      {'enabled' if AUTH_TOKEN else 'disabled (set server.auth_token in config.json)'}")
    if HTML_FILE:
        print(f"[OmniPublish] HTML:      {HTML_FILE.name}")
    else:
        print(f"[OmniPublish] WARNING: No HTML file found!")
    print(f"[OmniPublish] Ctrl+C to stop\n")

    print("[OmniPublish] REST API endpoints:")
    print("  GET  /api/ping          Health check")
    print("  GET  /api/info          Server info")
    print("  GET  /api/platforms     List platforms")
    print("  POST /api/run           Execute script (legacy)")
    print("  POST /api/copywrite     AI 文案生成")
    print("  POST /api/rename        图片重命名")
    print("  POST /api/cover         封面生成")
    print("  POST /api/watermark     水印处理")
    print("  POST /api/upload-file   上传文件")
    print()

    class ThreadingServer(http.server.ThreadingHTTPServer):
        allow_reuse_address = True

    server = ThreadingServer(("127.0.0.1", args.port), OmniHandler)
    server._current_pids = set()
    server._pid_lock = threading.Lock()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[OmniPublish] Server stopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
