"""OmniPublish V2.0 — 配置加载模块"""

import json
import os
from pathlib import Path
from dataclasses import dataclass, field


# 项目根目录
ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
UPLOADS_DIR = BACKEND_DIR / "uploads"
SCRIPTS_DIR = BACKEND_DIR / "scripts"
PROMPTS_DIR = SCRIPTS_DIR / "cw_prompts"

# 确保必要目录存在
DATA_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)
(UPLOADS_DIR / "watermarks").mkdir(exist_ok=True)


@dataclass
class CryptoConfig:
    appkey: str = ""
    aes_key: str = ""
    aes_iv: str = ""
    media_key: str = ""
    media_iv: str = ""
    bundle_id: str = "com.pc.jyaw"


@dataclass
class ServerConfig:
    port: int = 9527
    auth_secret: str = "change-me-in-production"
    allowed_origins: list = field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"])
    token_expire_hours: int = 24


@dataclass
class YoloConfig:
    face_model: str = "yolov8n-face.pt"
    general_model: str = "yolov8n.pt"


@dataclass
class DefaultsConfig:
    img_width: int = 800
    wm_width: int = 264
    wm_position: str = "bottom-right"
    wm_opacity: int = 100
    cover_layout: str = "triple"
    cover_candidates: int = 3
    video_codec: str = "auto"
    video_bitrate: str = "2M"
    video_fps: int = 30


@dataclass
class AppConfig:
    # LLM API
    api_base: str = ""
    api_key: str = ""
    cw_model: str = "gpt-4o"
    # 子配置
    crypto: CryptoConfig = field(default_factory=CryptoConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    yolo: YoloConfig = field(default_factory=YoloConfig)
    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)
    # 数据库
    db_path: str = ""  # 保留兼容，SQLite 备用
    database_url: str = ""

    def __post_init__(self):
        if not self.db_path:
            self.db_path = str(DATA_DIR / "omnipub.db")
        if not self.database_url:
            self.database_url = os.environ.get(
                "DATABASE_URL",
"postgresql://omnipub:omnipub2026@localhost:5433/omnipub"
            )


def load_config() -> AppConfig:
    """从 config.json 和环境变量加载配置。环境变量优先。"""
    config_file = ROOT_DIR / "config.json"
    raw = {}
    if config_file.exists():
        with open(config_file, "r", encoding="utf-8") as f:
            raw = json.load(f)

    # 构建配置对象
    crypto_raw = raw.get("crypto", {})
    server_raw = raw.get("server", {})
    yolo_raw = raw.get("yolo", {})
    defaults_raw = raw.get("defaults", {})

    config = AppConfig(
        api_base=os.environ.get("OPENAI_API_BASE") or os.environ.get("ANTHROPIC_BASE_URL") or raw.get("api_base", ""),
        api_key=os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or raw.get("api_key", ""),
        cw_model=os.environ.get("CW_MODEL") or raw.get("cw_model", "gpt-4o"),
        crypto=CryptoConfig(
            appkey=os.environ.get("OMNIPUB_APPKEY", crypto_raw.get("appkey", "")),
            aes_key=os.environ.get("OMNIPUB_AES_KEY", crypto_raw.get("aes_key", "")),
            aes_iv=os.environ.get("OMNIPUB_AES_IV", crypto_raw.get("aes_iv", "")),
            media_key=os.environ.get("OMNIPUB_MEDIA_KEY", crypto_raw.get("media_key", "")),
            media_iv=os.environ.get("OMNIPUB_MEDIA_IV", crypto_raw.get("media_iv", "")),
            bundle_id=crypto_raw.get("bundle_id", "com.pc.jyaw"),
        ),
        server=ServerConfig(
            port=int(os.environ.get("OMNIPUB_PORT", server_raw.get("port", 9527))),
            auth_secret=os.environ.get("OMNIPUB_AUTH_SECRET", server_raw.get("auth_token", "change-me-in-production")),
            allowed_origins=os.environ.get("OMNIPUB_CORS_ORIGINS", "").split(",") if os.environ.get("OMNIPUB_CORS_ORIGINS") else server_raw.get("allowed_origins", ["*"]),
            token_expire_hours=server_raw.get("token_expire_hours", 24),
        ),
        yolo=YoloConfig(**{k: v for k, v in yolo_raw.items() if k in YoloConfig.__dataclass_fields__}),
        defaults=DefaultsConfig(**{k: v for k, v in defaults_raw.items() if k in DefaultsConfig.__dataclass_fields__}),
    )

    return config


# 全局单例
settings = load_config()

# 安全警告
if settings.server.auth_secret in ("change-me-in-production", ""):
    import warnings
    warnings.warn(
        "\n⚠️  [OmniPublish] auth_secret 使用默认值，生产环境请设置 OMNIPUB_AUTH_SECRET 环境变量！",
        stacklevel=1,
    )
