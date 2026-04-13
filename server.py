#!/usr/bin/env python3
"""OmniPublish Local Server — 本地执行桥接服务

启动后在浏览器打开 http://127.0.0.1:9527，HTML 面板中的按钮即可直接执行命令。

用法:
    python3 server.py              # 默认端口 9527
    python3 server.py --port 8080  # 自定义端口
"""

import http.server, json, subprocess, os, sys, signal, argparse, time, threading, platform, tempfile, shlex
from pathlib import Path

SKILL_DIR = str(Path(__file__).resolve().parent)
SCRIPTS_DIR = Path(SKILL_DIR) / "scripts"

# ── Security: only these scripts are allowed to execute ──
ALLOWED_SCRIPTS = {
    "copywrite_gen.py", "make_cover.py", "image_rename.py",
    "image_watermark.py", "video_process.py", "publish_api.py",
}


def _parse_and_validate_cmd(cmd_str):
    """Parse a command string and validate it only runs an allowed script.

    Returns (cmd_list, error_string). On success error_string is None.
    """
    # Expand ~ before parsing
    cmd_str = cmd_str.replace("~/", os.path.expanduser("~/"))

    # Normalize shell-style line continuations (backslash + newline → space)
    cmd_str = cmd_str.replace("\\\n", " ")

    # Reject shell metacharacters (defense-in-depth: even without shell=True)
    for ch in [";", "|", "&&", "||", "`", "$(", ">", "<", "\n"]:
        if ch in cmd_str:
            return None, f"Rejected: shell metacharacter '{ch}' not allowed"

    try:
        parts = shlex.split(cmd_str)
    except ValueError as e:
        return None, f"Command parse error: {e}"

    if not parts:
        return None, "Empty command"

    # Find the .py script in the argument list
    script_idx = None
    for i, part in enumerate(parts):
        if part.endswith(".py"):
            script_idx = i
            break

    if script_idx is None:
        return None, "Rejected: only Python script execution is allowed"

    script_path = Path(parts[script_idx])

    # Resolve the script and verify it lives inside our scripts/ directory
    try:
        resolved = script_path.resolve(strict=False)
        scripts_resolved = SCRIPTS_DIR.resolve(strict=False)
        if not str(resolved).startswith(str(scripts_resolved) + os.sep) and resolved.parent != scripts_resolved:
            return None, f"Rejected: script not in {SCRIPTS_DIR}"
    except Exception:
        return None, f"Rejected: invalid script path"

    if script_path.name not in ALLOWED_SCRIPTS:
        return None, f"Rejected: '{script_path.name}' not in allowed scripts"

    if not resolved.exists():
        return None, f"Script not found: {resolved}"

    # Build safe command list: python executable + script + remaining args
    cmd_list = [sys.executable, str(resolved)] + parts[script_idx + 1:]
    return cmd_list, None

# Find the HTML file in skill directory
HTML_FILE = None
for f in Path(SKILL_DIR).iterdir():
    if f.suffix == ".html" and "omni" in f.name.lower():
        HTML_FILE = f
        break


def _get_search_dirs():
    """Platform-aware common search directories."""
    home = Path.home()
    skill_parent = Path(SKILL_DIR).parent
    dirs = [
        skill_parent, Path(SKILL_DIR),
        home / "Desktop", home / "Downloads", home / "Documents",
        home, home / "workspace",
    ]
    if platform.system() == "Darwin":
        dirs.append(Path("/Users/Shared"))
    elif platform.system() == "Windows":
        dirs.append(Path(os.environ.get("PUBLIC", r"C:\Users\Public")))
    # Docker 挂载的素材目录
    mnt_dir = Path("/mnt/素材")
    if mnt_dir.exists():
        dirs.insert(0, mnt_dir)
    dirs.append(Path(tempfile.gettempdir()))
    return dirs


class OmniHandler(http.server.SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=SKILL_DIR, **kwargs)

    # ── GET ──

    def do_GET(self):
        if self.path == "/":
            self._serve_html()
        elif self.path == "/api/info":
            self._json(200, {"skill_dir": SKILL_DIR, "version": "2.0", "platform": platform.system()})
        elif self.path == "/api/ping":
            self._json(200, {"ok": True})
        else:
            super().do_GET()

    # ── POST ──

    def do_POST(self):
        if self.path == "/api/run":
            self._handle_run()
        elif self.path == "/api/stop":
            self._handle_stop()
        elif self.path == "/api/pick-folder":
            self._handle_pick_folder()
        elif self.path == "/api/find-path":
            self._handle_find_path()
        elif self.path == "/api/upload-file":
            self._handle_upload_file()
        elif self.path == "/api/prepare-files":
            self._handle_prepare_files()
        elif self.path == "/api/save-file":
            self._handle_save_file()
        else:
            self._json(404, {"error": "not found"})

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    # ── Handlers ──

    def _serve_html(self):
        if not HTML_FILE or not HTML_FILE.exists():
            self._json(404, {"error": "HTML file not found in skill directory"})
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

        # Validate: only allowed scripts can be executed (no arbitrary shell commands)
        cmd_list, err = _parse_and_validate_cmd(cmd_str)
        if err:
            self._json(403, {"error": err})
            return

        # SSE streaming response
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
            # Store PID for potential stop (thread-safe)
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
                        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                                       capture_output=True)
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
        """Resolve folder from file info (name + size) sent by browser."""
        body = self._read_body()
        files = body.get("files", [])
        if not files:
            self._json(200, {"path": ""})
            return

        # Use first file's name + size to find the exact file on disk
        target = files[0]
        fname = target.get("name", "")
        fsize = target.get("size", -1)

        if not fname:
            self._json(200, {"path": ""})
            return

        home = Path.home()
        search_dirs = _get_search_dirs()
        for d in search_dirs:
            if not d.exists():
                continue
            for depth in [fname, f"*/{fname}", f"*/*/{fname}", f"*/*/*/{fname}"]:
                for match in d.glob(depth):
                    # Verify by file size if available
                    if fsize >= 0 and match.is_file() and match.stat().st_size != fsize:
                        continue
                    folder = str(match.parent) if match.is_file() else str(match)
                    self._json(200, {
                        "path": folder,
                        "file": str(match),
                        "files": [f.name for f in match.parent.iterdir()
                                  if f.suffix.lower() in {".jpg",".jpeg",".png",".webp",".gif",".mp4",".mov"}]
                    })
                    return

        self._json(200, {"path": "", "files": []})

    def _handle_find_path(self):
        """Try to resolve a filename to its absolute path. Best-effort, cross-platform."""
        body = self._read_body()
        name = body.get("name", "")
        if not name:
            self._json(400, {"error": "no filename"})
            return
        home = Path.home()
        search_dirs = _get_search_dirs()
        for d in search_dirs:
            if not d.exists():
                continue
            for depth_glob in [name, f"*/{name}", f"*/*/{name}"]:
                matches = list(d.glob(depth_glob))
                if matches:
                    match = matches[0]
                    # If match is a directory, return it directly; if file, return parent
                    folder = str(match) if match.is_dir() else str(match.parent)
                    self._json(200, {"path": folder, "file": str(match)})
                    return
        self._json(200, {"path": "", "total": 0})

    def _handle_upload_file(self):
        """Receive a file as base64 JSON {name, data} and save to skill_dir/uploads/."""
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
        upload_dir = Path(SKILL_DIR) / "uploads"
        upload_dir.mkdir(exist_ok=True)
        dest = upload_dir / name
        with open(dest, "wb") as f:
            f.write(raw)
        self._json(200, {"file": str(dest)})

    def _handle_prepare_files(self):
        """Create a temp directory with symlinks to selected files. Returns temp dir path."""
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
        # Create temp dir under skill_dir/tmp/
        import tempfile
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
                    # Fallback: copy if symlink fails (e.g. cross-device on Windows)
                    import shutil
                    shutil.copy2(str(src), str(dst))
                    linked.append(fname)
        self._json(200, {"path": str(tmp_dir), "files": linked, "count": len(linked)})

    def _handle_save_file(self):
        """Save text content to a file (restricted to user's home directory)."""
        body = self._read_body()
        file_path = body.get("path", "")
        content = body.get("content", "")
        if not file_path:
            self._json(400, {"error": "need path"})
            return
        try:
            p = Path(os.path.expanduser(file_path)).resolve()
            # Security: only allow writing under home dir or /app (Docker)
            home = Path.home().resolve()
            app_dir = Path(SKILL_DIR).resolve()
            allowed = (
                str(p).startswith(str(home) + os.sep) or p.parent == home
                or str(p).startswith(str(app_dir) + os.sep) or p.parent == app_dir
            )
            if not allowed:
                self._json(403, {"error": "Writing outside allowed directories is not allowed"})
                return
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            self._json(200, {"saved": str(p)})
        except Exception as e:
            self._json(500, {"error": str(e)})

    # ── Helpers ──

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
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
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, fmt, *args):
        # Quiet static file logs
        req = str(args[0]) if args else ""
        if any(req.startswith(p) for p in ["GET /api/ping", "GET /scripts/", "OPTIONS"]):
            return
        sys.stderr.write(f"[OmniPublish] {fmt % args}\n")


def main():
    parser = argparse.ArgumentParser(description="OmniPublish Local Server")
    parser.add_argument("--port", type=int, default=9527)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    print(f"[OmniPublish] Server starting...")
    print(f"[OmniPublish] URL:       http://{args.host}:{args.port}")
    print(f"[OmniPublish] Skill dir: {SKILL_DIR}")
    if HTML_FILE:
        print(f"[OmniPublish] HTML:      {HTML_FILE.name}")
    else:
        print(f"[OmniPublish] WARNING: No HTML file found!")
    print(f"[OmniPublish] Ctrl+C to stop\n")

    class ThreadingServer(http.server.ThreadingHTTPServer):
        allow_reuse_address = True

    server = ThreadingServer((args.host, args.port), OmniHandler)
    server._current_pids = set()  # Track multiple running processes
    server._pid_lock = threading.Lock()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[OmniPublish] Server stopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
