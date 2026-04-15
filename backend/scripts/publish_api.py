#!/usr/bin/env python3
"""OmniPublish - API Publisher (rewrite based on s5_publish.py reference)

Encryption: AES-128-CBC + SHA256/MD5 signing
Platform API: project_list, loginByPassword, config, r2upload_info, upload_mv,
              mv_list, create_update, create_video

CLI actions:
  login          Login and save credentials
  projects       List available projects
  upload-video   Upload videos to R2 + register via upload_mv
  publish        Upload images + match m3u8 via mv_list + create post draft
"""

import argparse, hashlib, json, os, re, sys, time, uuid, random
from base64 import b64encode, b64decode

try:
    import requests
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad, unpad
except ImportError:
    print("[ERROR] Missing dependencies. Run: pip3 install pycryptodome requests")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════════════
# Region 1: Crypto primitives (from s5_publish.py, identical logic)
# ═══════════════════════════════════════════════════════════════════════

# ── 加密密钥从环境变量或 config.json 加载，禁止硬编码 ──
def _load_crypto_config():
    """从环境变量或 config.json 加载加密配置。"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # 优先找项目根目录的 config.json（Docker: /app/config.json），再找 backend 级别
    config_file = os.path.join(script_dir, "..", "..", "config.json")
    if not os.path.exists(config_file):
        config_file = os.path.join(script_dir, "..", "config.json")
    config = {}
    if os.path.exists(config_file):
        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)
    crypto = config.get("crypto", {})
    return {
        "appkey":    os.environ.get("OMNIPUB_APPKEY",    crypto.get("appkey", "")),
        "key":       os.environ.get("OMNIPUB_AES_KEY",   crypto.get("aes_key", "")).encode()[:16],
        "iv":        os.environ.get("OMNIPUB_AES_IV",    crypto.get("aes_iv", "")).encode()[:16],
        "media_key": os.environ.get("OMNIPUB_MEDIA_KEY", crypto.get("media_key", "")).encode()[:16],
        "media_iv":  os.environ.get("OMNIPUB_MEDIA_IV",  crypto.get("media_iv", "")).encode()[:16],
        "bundle_id": os.environ.get("OMNIPUB_BUNDLE_ID", crypto.get("bundle_id", "com.pc.jyaw")),
    }

_CRYPTO = _load_crypto_config()
APPKEY    = _CRYPTO["appkey"]
KEY       = _CRYPTO["key"]
IV        = _CRYPTO["iv"]
MEDIA_KEY = _CRYPTO["media_key"]
MEDIA_IV  = _CRYPTO["media_iv"]
BUNDLE_ID = _CRYPTO["bundle_id"]
DEFAULT_BASE_URL = os.environ.get("OMNIPUB_BASE_URL", "")

# 启动时校验密钥是否已配置 — 快速失败，避免运行时加密错误
if not APPKEY or len(KEY) < 16 or len(IV) < 16:
    print("[FATAL] 加密密钥未配置或不完整，无法安全启动！")
    print("[FATAL] 请在 config.json 的 crypto 节或环境变量中配置:")
    print("[FATAL]   OMNIPUB_APPKEY, OMNIPUB_AES_KEY (≥16字符), OMNIPUB_AES_IV (≥16字符)")
    # 仅在直接执行时快速退出；被 import 时仅警告（后端 tools 可能不需要此模块的加密功能）
    if __name__ == "__main__":
        sys.exit(1)

def _sha256(data):
    return hashlib.sha256(data.encode("utf-8")).hexdigest()

def _md5(data):
    return hashlib.md5(data.encode("utf-8")).hexdigest()

def _aes_encrypt(plaintext, key=KEY, iv=IV):
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return b64encode(cipher.encrypt(pad(plaintext.encode("utf-8"), AES.block_size))).decode("utf-8")

def _aes_decrypt(ciphertext, key=KEY, iv=IV):
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return unpad(cipher.decrypt(b64decode(ciphertext)), AES.block_size).decode("utf-8")

def _sign(data_b64, timestamp):
    return _md5(_sha256(f"data={data_b64}&timestamp={timestamp}{APPKEY}"))

def encrypt_data(plaintext):
    ct = _aes_encrypt(plaintext)
    ts = int(time.time())
    return f"timestamp={ts}&data={ct}&sign={_sign(ct, ts)}"

def decrypt_data(ciphertext):
    return _aes_decrypt(ciphertext)

def _normalize_tags(s):
    if not s:
        return ""
    s = s.replace("#", ",").replace("\uff0c", ",")
    return ",".join(p.strip() for p in s.split(",") if p.strip())


# ═══════════════════════════════════════════════════════════════════════
# Region 2: RemotePublishClient (based on s5 RemotePublisher + enhancements)
# ═══════════════════════════════════════════════════════════════════════

class RemotePublishClient:
    """Platform API client with AES encryption, auto-relogin, SSL retry."""

    # 请求限速：两次请求之间最小间隔（秒），防止触发平台封号
    MIN_REQUEST_INTERVAL = float(os.environ.get("OMNIPUB_RATE_LIMIT", "1.0"))

    def __init__(self, base_url=DEFAULT_BASE_URL):
        # 去掉 URL 中的 hash fragment（如 /#/auth/login）
        clean_url = base_url.split("#")[0] if "#" in base_url else base_url
        self.base_url = clean_url.rstrip("/")
        self.session = requests.Session()
        # 禁用 SSL 验证（部分平台证书不匹配，Docker 环境 CA 可能不全）
        self.session.verify = False
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        # NOTE: Do NOT set Content-Type on session — it breaks multipart uploads
        self.token = None
        self.projects = []
        self.current_project = None
        self._api_base = None
        self._credentials = None       # (username, password) for auto-relogin
        self._site_config = None        # cached site config
        self._config_result = None      # full config response (categories, authors)
        self.project_code = None
        self._last_request_time = 0     # 上次请求时间戳

    # ── Properties ──

    @property
    def api_base(self):
        if self._api_base:
            return self._api_base
        if not self.current_project:
            raise RuntimeError("No project selected. Call select_project() first.")
        apis = self.current_project.get("api", [])
        if not apis:
            raise RuntimeError(f"Project has no API URLs: {self.current_project.get('title')}")
        self._api_base = random.choice(apis)
        return self._api_base

    @property
    def _is_remote_php(self):
        return "remote.php" in (self._api_base or self.api_base)

    # ── Core transport ──

    def _rate_limit(self):
        """限速：确保两次请求间隔不小于 MIN_REQUEST_INTERVAL。"""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self.MIN_REQUEST_INTERVAL:
            time.sleep(self.MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

    def _raw_post(self, url, params, use_token=True):
        """Encrypted POST — mirrors s5's _post_encrypted exactly."""
        self._rate_limit()
        request_data = {
            "oauth_id": uuid.uuid4().hex[:32],
            "bundleId": BUNDLE_ID,
            "version": (self.current_project or {}).get("version", "1.0.0"),
            "oauth_type": "web",
            "language": "zh",
            "via": "web",
            "token": self.token if use_token else None,
            **params,
        }
        encrypted_body = encrypt_data(json.dumps(request_data, ensure_ascii=False))
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        resp = self.session.post(url, data=encrypted_body, headers=headers, timeout=60)
        resp.raise_for_status()

        # Parse response — try json first, regex fallback for quirky responses
        try:
            resp_json = resp.json()
        except (json.JSONDecodeError, ValueError):
            m = re.search(r'\{.*\}', resp.text, re.DOTALL)
            if not m:
                raise RuntimeError(f"No JSON in response: {resp.text[:200]}")
            resp_json = json.loads(m.group(0))

        # Decrypt inner data if present
        if resp_json.get("data") and isinstance(resp_json["data"], str):
            try:
                decrypted = json.loads(decrypt_data(resp_json["data"]))
                return decrypted
            except Exception:
                pass
        return resp_json

    def _post_encrypted(self, url, params, use_token=True):
        """Encrypted POST with auto-relogin on token expiry."""
        result = self._raw_post(url, params, use_token)

        # Auto-relogin on token failure
        if use_token and self._credentials and isinstance(result, dict):
            msg = str(result.get("msg", ""))
            status = result.get("status", 1)
            if status == 0 and ("token" in msg.lower() or "系统错误" in msg):
                print(f"[WARN]  Token expired ({msg}), re-logging in...")
                try:
                    self._do_login(*self._credentials)
                    result = self._raw_post(url, params, use_token)
                except Exception as e:
                    print(f"[ERROR] Re-login failed: {e}")
        return result

    # ── Project & Login ──

    def get_projects(self):
        result = self._post_encrypted(
            f"{self.base_url}/api/remote/project_list", {},
            use_token=False,
        )
        if isinstance(result, dict) and "data" in result:
            self.projects = result["data"] if isinstance(result["data"], list) else []
        elif isinstance(result, list):
            self.projects = result
        else:
            self.projects = result.get("list", result.get("projects", []))
        print(f"[OK]    Got {len(self.projects)} projects")
        return self.projects

    def select_project(self, project_code=None):
        code = project_code or self.project_code
        if not code:
            raise RuntimeError("No project code provided")
        if not self.projects:
            self.get_projects()
        for p in self.projects:
            ptype = p.get("type", "")
            if _md5(ptype)[:8] == code:
                self.current_project = p
                self._api_base = None
                self._site_config = None
                self._config_result = None
                print(f"[OK]    Project: {p.get('title')} (type={ptype})")
                print(f"[OK]    API base: {self.api_base}")
                return p
        raise RuntimeError(f"Project code '{code}' not found in {len(self.projects)} projects")

    def login(self, username, password):
        if not self.current_project:
            self.select_project()
        self._credentials = (username, password)
        return self._do_login(username, password)

    def _do_login(self, username, password):
        project_type = (self.current_project or {}).get("type", "")
        is_hlw = "hlw" in project_type.lower()
        path = "/api/index/login" if is_hlw else "/api/remote/loginByPassword"

        result = self._raw_post(
            f"{self.api_base}{path}",
            {"username": username, "password": password},
            use_token=False,
        )

        if is_hlw:
            token = (result.get("data") or {}).get("token")
        else:
            if result.get("status") != 0:
                token = result.get("data")
                if isinstance(token, dict):
                    token = token.get("token")
            else:
                raise RuntimeError(f"Login failed: {result.get('msg', 'unknown')}")

        if not token:
            raise RuntimeError(f"Login failed, no token: {json.dumps(result, ensure_ascii=False)[:200]}")

        self.token = str(token)
        print(f"[OK]    Login success, token: {self.token[:6]}***{self.token[-4:]}")
        return self.token

    # ── Config ──

    def _get_site_config(self):
        if not self._site_config:
            result = self._post_encrypted(f"{self.api_base}/api/remote/config", {})
            self._config_result = result
            self._site_config = (result.get("data") or {}).get("config") or result.get("config") or {}
        return self._site_config

    def _get_full_config(self):
        self._get_site_config()
        return self._config_result or {}

    def resolve_category_id(self, category_name):
        cfg = self._get_full_config()
        cats = cfg.get("category") or cfg.get("categories") or \
               (cfg.get("data") or {}).get("category") or []
        if isinstance(cats, list):
            for cat in cats:
                if isinstance(cat, dict):
                    cname = cat.get("name", "") or cat.get("title", "")
                    if cname == category_name:
                        return str(cat.get("id", ""))
        print(f"[WARN]  Category '{category_name}' not found, using as-is")
        return category_name

    # ── Image Upload (dedicated endpoint, not R2) ──

    def upload_image(self, image_path):
        cfg = self._get_site_config()
        img_upload_url = cfg.get("img_upload_url")
        img_base = cfg.get("img_base", "")
        if not img_upload_url:
            print(f"[ERROR] No img_upload_url in config")
            return None

        from pathlib import Path
        ext = Path(image_path).suffix.lower()
        ct = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
        fname = os.path.basename(image_path)

        print(f"[INFO]  Uploading image: {fname}...")
        with open(image_path, "rb") as f:
            resp = self.session.post(
                img_upload_url,
                files={"cover": (fname, f, ct)},
                data={"key": cfg.get("upload_img_key", "")},
                timeout=60,
            )
            resp.raise_for_status()

        rj = resp.json()
        if rj.get("code") != 1:
            print(f"[ERROR] Image upload failed: {rj.get('msg', 'unknown')}")
            return None

        full_url = f"{img_base}{rj['msg']}" if img_base else rj["msg"]
        print(f"[OK]    Image -> {full_url[:80]}...")
        return full_url

    # ── R2 Upload (video binary) ──

    def _get_r2_info(self):
        result = self._post_encrypted(f"{self.api_base}/api/remote/r2upload_info", {})
        inner = result.get("data", result) if isinstance(result.get("data"), dict) else result
        upload_url = inner.get("uploadUrl") or inner.get("upload_url")
        public_url = inner.get("publicUrl") or inner.get("public_url")
        upload_name = inner.get("UploadName") or inner.get("upload_name")
        if not upload_url:
            raise RuntimeError(f"No uploadUrl: {json.dumps(result, ensure_ascii=False)[:200]}")
        return upload_url, public_url, upload_name

    def _put_to_r2(self, file_path, upload_url, public_url, content_type="video/mp4"):
        """PUT file to R2 presigned URL with SSL retry."""
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        fsize = os.path.getsize(file_path)
        print(f"[INFO]  Uploading {os.path.basename(file_path)} ({fsize} bytes)...")

        max_retries = 3
        verify = True
        for attempt in range(1, max_retries + 1):
            try:
                with open(file_path, "rb") as f:
                    resp = requests.put(
                        upload_url, data=f,
                        headers={"Content-Type": content_type},
                        timeout=900,
                        verify=verify,
                    )
                if resp.status_code in (200, 201):
                    url = public_url or upload_url.split("?")[0]
                    print(f"[OK]    Uploaded -> {url[:80]}...")
                    return url
                raise RuntimeError(f"PUT failed ({resp.status_code}): {resp.text[:200]}")
            except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
                print(f"[WARN]  Upload attempt {attempt}/{max_retries} failed: {type(e).__name__}")
                if attempt == max_retries:
                    raise RuntimeError(f"Upload failed after {max_retries} attempts: {e}")
                time.sleep(2 * attempt)
                verify = False  # Fallback for LibreSSL 2.8.3 — 安全风险，仅限重试场景
                print(f"[WARN]  SSL 验证已禁用（仅本次重试），存在中间人攻击风险")
                print(f"[INFO]  Getting fresh upload URL...")
                upload_url, new_public, _ = self._get_r2_info()
                public_url = new_public or public_url

    # ── Video Upload & Registration ──

    def upload_video(self, video_path, cover_url=None, display_name=None):
        """Upload video to R2 + register via upload_mv. Returns {mp4_url, cover_url}.
        display_name: human-readable name for registration (e.g. article title + seq)."""
        upload_url, public_url, upload_name = self._get_r2_info()
        mp4_url = self._put_to_r2(video_path, upload_url, public_url)

        # Cover: use provided, or extract from video
        if not cover_url:
            cover_url = self._extract_cover(video_path)

        # Register via upload_mv — prefer display_name for human readability
        reg_params = {
            "name": display_name or upload_name or os.path.splitext(os.path.basename(video_path))[0],
            "mp4_url": mp4_url,
            "upload_type": 1,
            "cover": cover_url or "",
        }
        result = self._post_encrypted(f"{self.api_base}/api/remote/upload_mv", reg_params)
        status = result.get("status")
        if status == 1 or status == "1":
            print(f"[OK]    Video registered: {os.path.basename(video_path)}")
        else:
            print(f"[WARN]  Register status: {result.get('msg', '')} (video is on R2, may need retry)")

        return {"mp4_url": mp4_url, "cover_url": cover_url or ""}

    def _extract_cover(self, video_path):
        """Extract frame from video via ffmpeg, upload via image endpoint."""
        import subprocess, tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()
        try:
            subprocess.run([
                "ffmpeg", "-y", "-i", video_path,
                "-ss", "1", "-frames:v", "1", "-q:v", "2", tmp.name,
            ], capture_output=True, timeout=30)
            if os.path.getsize(tmp.name) > 0:
                print(f"[INFO]  Auto-extracted cover from video")
                return self.upload_image(tmp.name)
        except Exception as e:
            print(f"[WARN]  Cover extraction failed: {e}")
        finally:
            try: os.unlink(tmp.name)
            except OSError: pass
        return None

    # ── Video List (mv_list) ──

    def get_mv_list(self):
        """Fetch list of uploaded videos with m3u8 URLs and slice status."""
        result = self._post_encrypted(f"{self.api_base}/api/remote/mv_list", {})
        data = result.get("data", result)
        if isinstance(data, dict):
            return data.get("list", [])
        if isinstance(data, list):
            return data
        return []

    def find_video_by_mp4(self, mp4_url):
        """Find a video's m3u8 URL by matching its mp4_url in mv_list.
        Returns {video_url, cover, id, slice_status} or None."""
        videos = self.get_mv_list()
        for v in videos:
            if v.get("mp4_url") == mp4_url:
                if v.get("slice_status") == 2:
                    return v
                else:
                    print(f"[WARN]  Video found but still slicing (status={v.get('slice_status')}): {mp4_url[:60]}")
                    return None
        print(f"[WARN]  Video not found in mv_list: {mp4_url[:60]}")
        return None

    # ── Post Publishing ──

    def publish_post(self, title, body, cover_url="", category_id="",
                     tags="", keyword="", desc="", is_draft=3):
        """Create post via create_update (standard) or addArticle (HLW)."""
        project_type = (self.current_project or {}).get("type", "")
        is_hlw = "hlw" in project_type.lower()

        if is_hlw:
            params = {
                "title": title,
                "thumb": cover_url,
                "content": body,
                "tag": _normalize_tags(tags),
                "keyword": _normalize_tags(keyword),
            }
            path = "/api/index/addArticle"
        else:
            params = {
                "title": title,
                "body": body,
                "cover": cover_url,
                "category_id": category_id,
                "tags": _normalize_tags(tags),
                "keyword": _normalize_tags(keyword),
                "desc": desc or title,
                "is_draft": is_draft,
            }
            path = "/api/remote/create_update"

        result = self._post_encrypted(f"{self.api_base}{path}", params)
        if result.get("status") == 1:
            print(f"[OK]    Post created (draft): {title[:50]}")
            return result.get("data")
        print(f"[ERROR] Post failed: {json.dumps(result, ensure_ascii=False, default=str)[:300]}")
        return None


# ═══════════════════════════════════════════════════════════════════════
# Region 3: OmniPublish skill logic (txt, markdown, folder, CLI)
# ═══════════════════════════════════════════════════════════════════════

# ── TXT Parser ──

def parse_txt_file(txt_path):
    with open(txt_path, "r", encoding="utf-8") as f:
        content = f.read()

    meta = {"title": "", "author": "", "category": "", "keywords": "", "sections": []}
    lines = content.strip().split("\n")
    body_start = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("title:") or stripped.startswith("标题:"):
            meta["title"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("author:") or stripped.startswith("作者:"):
            meta["author"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("category:") or stripped.startswith("分类:"):
            meta["category"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("keywords:") or stripped.startswith("关键词:"):
            meta["keywords"] = stripped.split(":", 1)[1].strip()
        elif stripped == "":
            body_start = i + 1
            break
        body_start = i + 1

    current_heading = ""
    current_paragraphs = []
    for line in lines[body_start:]:
        stripped = line.strip()
        if stripped.startswith("## "):
            if current_paragraphs or current_heading:
                meta["sections"].append({"h": current_heading, "p": "\n".join(current_paragraphs)})
            current_heading = stripped[3:].strip()
            current_paragraphs = []
        elif stripped:
            current_paragraphs.append(stripped)
    if current_paragraphs or current_heading:
        meta["sections"].append({"h": current_heading, "p": "\n".join(current_paragraphs)})
    return meta


# ── Markdown Builder ──

def _video_tag(video_url, poster=""):
    """Generate platform-compatible DPlayer shortcode."""
    pic_attr = f' pic="{poster}"' if poster else ''
    return f'[dplayer url="{video_url}"{pic_attr} /]'


def build_markdown(meta, image_urls, video_entries=None, layout_template=None):
    """Build post body. video_entries = [{video_url, cover}] from mv_list."""
    video_entries = video_entries or []

    if not layout_template:
        md_parts = []
        img_idx = 0
        for sec in meta["sections"]:
            if sec["h"]:
                md_parts.append(f"## {sec['h']}")
            if sec["p"]:
                md_parts.append(sec["p"])
            for _ in range(3):
                if img_idx < len(image_urls):
                    md_parts.append(f"![img]({image_urls[img_idx]})")
                    img_idx += 1
        while img_idx < len(image_urls):
            md_parts.append(f"![img]({image_urls[img_idx]})")
            img_idx += 1
        for ve in video_entries:
            md_parts.append(_video_tag(ve.get("video_url", ""), ve.get("cover", "")))
        return "\n\n".join(md_parts)

    # Template-based layout (plain-text format)
    # Convert plain-text tokens to internal markers for processing
    md = layout_template
    # Normalize: 正文 → {正文}, 图片N-M → {img:N-M}, 视频 → {vid:next}, ## 小标题 → ## {小标题}
    md = re.sub(r'^(正文)$', r'{正文}', md, flags=re.MULTILINE)
    md = re.sub(r'^## 小标题$', r'## {小标题}', md, flags=re.MULTILINE)
    md = re.sub(r'^图片(\d+)-(\d+)$', r'{img:\1-\2}', md, flags=re.MULTILINE)
    md = re.sub(r'^图片(\d+)$', r'{img:\1}', md, flags=re.MULTILINE)
    md = re.sub(r'^视频(\d+)$', r'{vid:\1}', md, flags=re.MULTILINE)
    md = re.sub(r'^视频$', r'{vid:next}', md, flags=re.MULTILINE)

    section_idx = 0
    while "{正文}" in md and section_idx < len(meta["sections"]):
        md = md.replace("{正文}", meta["sections"][section_idx].get("p", ""), 1)
        section_idx += 1
    # 小标题只取非空的（第一段通常无标题）
    headings = [s["h"] for s in meta["sections"] if s.get("h")]
    h_idx = 0
    while "{小标题}" in md and h_idx < len(headings):
        md = md.replace("{小标题}", headings[h_idx], 1)
        h_idx += 1
    # Track which images/videos are placed by template
    placed_imgs = set()
    placed_vids = set()
    for match in re.finditer(r'\{img:(\d+)-(\d+)\}', md):
        start, end = int(match.group(1)) - 1, int(match.group(2))
        for i in range(start, min(end, len(image_urls))):
            placed_imgs.add(i)
        replacement = "\n\n".join(f"![img]({u})" for u in image_urls[start:end])
        md = md.replace(match.group(0), replacement, 1)
    for match in re.finditer(r'\{img:(\d+)\}', md):
        idx = int(match.group(1)) - 1
        if idx < len(image_urls):
            placed_imgs.add(idx)
            md = md.replace(match.group(0), f"![img]({image_urls[idx]})", 1)
    for match in re.finditer(r'\{vid:(\d+)\}', md):
        idx = int(match.group(1)) - 1
        if idx < len(video_entries):
            placed_vids.add(idx)
            ve = video_entries[idx]
            md = md.replace(match.group(0), _video_tag(ve.get("video_url", ""), ve.get("cover", "")), 1)
    # Handle {vid:next} — place next unplaced video
    vid_next_idx = 0
    while '{vid:next}' in md:
        while vid_next_idx in placed_vids and vid_next_idx < len(video_entries):
            vid_next_idx += 1
        if vid_next_idx < len(video_entries):
            ve = video_entries[vid_next_idx]
            placed_vids.add(vid_next_idx)
            md = md.replace('{vid:next}', _video_tag(ve.get("video_url", ""), ve.get("cover", "")), 1)
            vid_next_idx += 1
        else:
            md = md.replace('{vid:next}', '', 1)
    md = re.sub(r'\{vid:\d+(-\d+)?\}', '', md)
    # Append any videos NOT placed by template (always append — videos are critical)
    remaining_vids = [ve for i, ve in enumerate(video_entries) if i not in placed_vids]
    if remaining_vids:
        vid_tags = "\n\n".join(_video_tag(ve.get("video_url", ""), ve.get("cover", "")) for ve in remaining_vids)
        md = md.rstrip() + "\n\n" + vid_tags
    return md


# ── Publish Folder Orchestration ──

def publish_folder(api, folder, layout_template=None):
    txt_files = [f for f in os.listdir(folder) if f.endswith(".txt")]
    if not txt_files:
        print("[ERROR] No TXT file found in folder")
        return False

    meta = parse_txt_file(os.path.join(folder, txt_files[0]))
    print(f"[INFO]  Title: {meta['title']}")
    print(f"[INFO]  Category: {meta['category']}, Keywords: {meta['keywords']}")
    print(f"[INFO]  Sections: {len(meta['sections'])}")

    exts_img = {".jpg", ".jpeg", ".png", ".webp"}
    all_files = sorted(f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f)))
    image_files = [f for f in all_files if os.path.splitext(f)[1].lower() in exts_img and "_cover" not in f.lower()]
    cover_files = [f for f in all_files if "_cover" in f.lower() and os.path.splitext(f)[1].lower() in exts_img]

    # Upload cover
    cover_url = ""
    if cover_files:
        cover_url = api.upload_image(os.path.join(folder, cover_files[0])) or ""

    # Upload body images
    print(f"\n[INFO]  Uploading {len(image_files)} images...")
    image_urls = []
    for fname in image_files:
        url = api.upload_image(os.path.join(folder, fname))
        if url:
            image_urls.append(url)

    # Load video upload results from previous upload-video step
    video_entries = []
    result_file = os.path.join(folder, ".video_upload_results.json")
    if os.path.exists(result_file):
        with open(result_file) as f:
            saved = json.load(f)
        video_data = saved.get("videos", [])
        if not cover_url:
            cover_url = saved.get("cover_url", "")
        print(f"[INFO]  Loaded {len(video_data)} video results from previous upload")

        # Match each video's mp4_url to its m3u8 address via mv_list
        if video_data:
            print(f"[INFO]  Querying mv_list for m3u8 addresses...")
            for vd in video_data:
                mp4_url = vd.get("mp4_url", "")
                if mp4_url:
                    matched = api.find_video_by_mp4(mp4_url)
                    if matched:
                        video_entries.append({
                            "video_url": matched.get("video_url", ""),
                            "cover": matched.get("cover", "") or vd.get("cover_url", "") or cover_url,
                            "id": matched.get("id"),
                        })
                        print(f"[OK]    Matched video -> {matched.get('video_url', '')[:60]}...")
                    else:
                        print(f"[WARN]  Video not ready or not found, skipping: {mp4_url[:60]}")
    else:
        print(f"[WARN]  No .video_upload_results.json found. Run upload-video first.")

    # Resolve category
    cat_id = api.resolve_category_id(meta["category"])
    print(f"[INFO]  Category: '{meta['category']}' -> id={cat_id}")

    # Build post body with images + video tags
    body = build_markdown(meta, image_urls, video_entries, layout_template)
    print(f"\n[INFO]  Body length: {len(body)} chars, videos embedded: {len(video_entries)}")

    # Create post draft
    result = api.publish_post(
        title=meta["title"],
        body=body,
        cover_url=cover_url,
        category_id=cat_id,
        tags=meta["keywords"],
        keyword=meta["keywords"],
        is_draft=3,
    )

    if result:
        print(f"\n[OK]    Draft saved successfully!")
        return True
    return False


# ── CLI ──

def _ensure_login(api, args):
    """Fresh login every time (tokens expire between upload and publish)."""
    api.select_project()

    if api.token:
        return

    token_path = os.path.expanduser("~/.omnipublish_token")
    if not os.path.exists(token_path):
        print("[ERROR] No saved credentials. Run --action login first.")
        sys.exit(1)

    with open(token_path) as f:
        saved = json.load(f)

    username = saved.get("username", "")
    password = saved.get("password", "")
    if not username or not password:
        print("[ERROR] No credentials saved. Run --action login first.")
        sys.exit(1)

    print(f"[INFO]  Logging in as {username}...")
    api.login(username, password)


def main():
    parser = argparse.ArgumentParser(description="OmniPublish API Publisher")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--project-code", required=True)
    parser.add_argument("--username", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--token", default="")
    parser.add_argument("--folder", default="")
    parser.add_argument("--layout-template", default="")
    parser.add_argument("--action", required=True,
                        choices=["login", "projects", "upload-video", "publish", "decrypt", "mv-list", "categories"])
    args = parser.parse_args()

    api = RemotePublishClient(args.base_url)
    api.project_code = args.project_code
    if args.token:
        api.token = args.token

    if args.action == "projects":
        projects = api.get_projects()
        print(json.dumps(projects, indent=2, ensure_ascii=False))

    elif args.action == "login":
        if not args.username or not args.password:
            print("[ERROR] --username and --password required")
            sys.exit(1)
        api.select_project()
        token = api.login(args.username, args.password)
        token_path = os.path.expanduser("~/.omnipublish_token")
        with open(token_path, "w") as f:
            json.dump({
                "token": token, "base_url": args.base_url,
                "project_code": args.project_code,
                "username": args.username, "password": args.password,
            }, f)
        print(f"[OK]    Credentials saved to {token_path}")

    elif args.action == "upload-video":
        if not args.folder:
            print("[ERROR] --folder required"); sys.exit(1)
        if not os.path.isdir(args.folder):
            print(f"[ERROR] Folder not found: {args.folder}")
            print(f"[HINT]  请重新选择文件夹路径（可能是旧缓存路径）")
            sys.exit(1)
        _ensure_login(api, args)

        exts_img = {".jpg", ".jpeg", ".png", ".webp"}
        exts_vid = {".mp4", ".mov", ".avi", ".mkv"}
        all_files = sorted(f for f in os.listdir(args.folder)
                           if os.path.isfile(os.path.join(args.folder, f)))

        # Read title from txt for video naming
        txt_files = [f for f in all_files if f.endswith(".txt")]
        video_title = ""
        if txt_files:
            try:
                meta = parse_txt_file(os.path.join(args.folder, txt_files[0]))
                video_title = meta.get("title", "")
                print(f"[INFO]  Video display name from txt: {video_title or '(empty title)'}")
            except Exception as e:
                print(f"[WARN]  Failed to read txt for title: {e}")
        else:
            print(f"[INFO]  No txt file found, video will use filename as display name")
        print(f"[INFO]  Files in folder: {all_files[:10]}")

        # Upload cover
        cover_files = [f for f in all_files if "_cover" in f.lower() and os.path.splitext(f)[1].lower() in exts_img]
        cover_url = ""
        if cover_files:
            print(f"[INFO]  Found cover: {cover_files[0]}")
            cover_url = api.upload_image(os.path.join(args.folder, cover_files[0])) or ""

        # Upload videos
        videos = [f for f in all_files if os.path.splitext(f)[1].lower() in exts_vid]
        if not videos:
            print(f"[WARN]  No video files found in {args.folder}")

        video_results = []
        for i, vf in enumerate(videos):
            # Name: title + sequence (e.g. "吃瓜事件_1") or just title for single video
            if video_title:
                display_name = f"{video_title}_{i+1}" if len(videos) > 1 else video_title
            else:
                display_name = os.path.splitext(vf)[0]
            print(f"[INFO]  Uploading video [{i+1}/{len(videos)}]: {vf} → name: {display_name}")
            vd = api.upload_video(os.path.join(args.folder, vf), cover_url=cover_url, display_name=display_name)
            if vd:
                video_results.append(vd)

        # Save results
        result_file = os.path.join(args.folder, ".video_upload_results.json")
        with open(result_file, "w") as f:
            json.dump({"cover_url": cover_url, "videos": video_results}, f, ensure_ascii=False)
        print(f"[OK]    Results saved to {result_file}")

    elif args.action == "publish":
        if not args.folder:
            print("[ERROR] --folder required"); sys.exit(1)
        if not os.path.isdir(args.folder):
            print(f"[ERROR] Folder not found: {args.folder}")
            print(f"[HINT]  请重新选择文件夹路径（可能是旧缓存路径）")
            sys.exit(1)
        _ensure_login(api, args)
        tpl = args.layout_template.replace('\\n', '\n') if args.layout_template else None
        publish_folder(api, args.folder, tpl)

    elif args.action == "decrypt":
        # Decrypt intercepted encrypted data from F12 Network
        print("Paste the encrypted 'data' field value (base64 string), then press Enter:")
        cipher = input().strip()
        if not cipher:
            print("[ERROR] No data provided")
            sys.exit(1)
        try:
            plain = decrypt_data(cipher)
            parsed = json.loads(plain)
            print(json.dumps(parsed, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"[ERROR] Decrypt failed: {e}")
            # Try as full "timestamp=x&data=x&sign=x" body
            if "data=" in cipher:
                parts = dict(p.split("=", 1) for p in cipher.split("&") if "=" in p)
                if "data" in parts:
                    plain = decrypt_data(parts["data"])
                    parsed = json.loads(plain)
                    print(json.dumps(parsed, indent=2, ensure_ascii=False))

    elif args.action == "mv-list":
        _ensure_login(api, args)
        videos = api.get_mv_list()
        for v in videos[:20]:
            status = "ready" if v.get("slice_status") == 2 else f"slicing({v.get('slice_status')})"
            print(f"  [{status}] id={v.get('id')} {v.get('name','')[:30]}")
            print(f"    mp4:   {v.get('mp4_url','')[:70]}")
            print(f"    m3u8:  {v.get('video_url','')[:70]}")
            print(f"    cover: {v.get('cover','')[:70]}")
        print(f"\nTotal: {len(videos)} videos")

    elif args.action == "categories":
        _ensure_login(api, args)
        cfg = api._get_full_config()
        # Print raw config keys for debugging
        print(f"[INFO]  Config keys: {list(cfg.keys()) if isinstance(cfg, dict) else type(cfg)}")
        cats = cfg.get("category") or cfg.get("categories") or \
               (cfg.get("data") or {}).get("category") or []
        if isinstance(cats, list):
            for cat in cats:
                if isinstance(cat, dict):
                    cid = cat.get("id", "")
                    cname = cat.get("name", "") or cat.get("title", "")
                    print(f"  [{cid}] {cname}")
            print(f"\nTotal: {len(cats)} categories")
        else:
            print(f"[WARN]  Categories not a list: {type(cats)} = {str(cats)[:500]}")


if __name__ == "__main__":
    main()
