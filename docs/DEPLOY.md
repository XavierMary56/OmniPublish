# OmniPublish V2.0 — 部署文档

## 一、环境要求

| 组件 | 最低版本 | 说明 |
|------|---------|------|
| Python | 3.10+ | 运行后端服务 |
| Node.js | 18+ | 构建前端（仅构建时需要） |
| FFmpeg | 5.0+ | 视频处理 |
| 磁盘空间 | 50GB+ | 素材文件 + 处理中间文件 |
| 内存 | 4GB+ | YOLOv8 模型加载约需 500MB |

---

## 二、快速部署（Docker，推荐）

### 2.1 前置条件

- 安装 Docker Desktop（Windows/Mac）或 Docker Engine（Linux）
- 准备 `config.json` 配置文件

### 2.2 部署步骤

```bash
# 1. 克隆项目
cd /path/to/OmniPublish

# 2. 复制并编辑配置
cp config.json.example config.json
# 编辑 config.json，填入：
#   - api_key（LLM API 密钥）
#   - crypto 节（平台加密密钥）
#   - server.auth_token（自定义一个随机字符串）

# 3. 启动
docker compose up -d

# 4. 查看日志
docker compose logs -f omnipub

# 5. 访问
# http://localhost:9527
```

### 2.3 Docker Compose 配置说明

```yaml
# docker-compose.yml
services:
  omnipub:
    build: .
    ports:
      - "9527:9527"
    volumes:
      - ./config.json:/app/config.json:ro    # 配置文件
      - ./data:/app/data                      # SQLite 数据库
      - ./backend/uploads:/app/uploads        # 水印文件
      - /path/to/素材:/materials              # 素材目录（按需挂载）
    environment:
      - TZ=Asia/Shanghai
    restart: unless-stopped
```

### 2.4 Nginx 反向代理（生产环境）

```nginx
server {
    listen 80;
    server_name omnipub.internal.com;

    location / {
        proxy_pass http://127.0.0.1:9527;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # WebSocket 支持
    location /ws/ {
        proxy_pass http://127.0.0.1:9527;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }

    # 文件上传大小限制
    client_max_body_size 100M;
}
```

---

## 三、手动部署（无 Docker）

### 3.1 安装 Python 依赖

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3.2 安装 FFmpeg

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Windows
# 下载 https://ffmpeg.org/download.html，加入 PATH
```

### 3.3 初始化数据库

```bash
cd backend
python -c "from database import init_db; import asyncio; asyncio.run(init_db())"
```

### 3.4 构建前端

```bash
cd frontend
npm install
npm run build
# 构建产物在 frontend/dist/，后端会自动 serve
```

### 3.5 启动服务

```bash
cd backend
python main.py --port 9527
```

### 3.6 配置为系统服务（Linux）

```ini
# /etc/systemd/system/omnipub.service
[Unit]
Description=OmniPublish V2.0
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/OmniPublish/backend
ExecStart=/opt/OmniPublish/backend/venv/bin/python main.py --port 9527
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable omnipub
sudo systemctl start omnipub
```

---

## 四、与现有 Docker PHP 环境集成

如果需要在现有 `docker-php7.3` 环境旁边运行：

```yaml
# 在 docker-php7.3/docker-compose.yml 中新增服务
services:
  # ... 现有的 fpm-server, nginx-server 等 ...

  omnipub:
    build: /path/to/OmniPublish
    ports:
      - "9527:9527"
    volumes:
      - /path/to/2026www/OmniPublish/config.json:/app/config.json:ro
      - /path/to/2026www/OmniPublish/data:/app/data
      - /path/to/素材目录:/materials
    networks:
      - default  # 与其他容器共享网络
```

Nginx 配置中添加 OmniPublish 路由：
```nginx
location /omnipub/ {
    proxy_pass http://omnipub:9527/;
    proxy_set_header Host $host;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

---

## 五、配置文件说明

```jsonc
// config.json
{
  // LLM API（文案生成）
  "api_base": "https://api.openai.com/v1",
  "api_key": "sk-xxx",           // 必填
  "cw_model": "gpt-4o",

  // 平台 API 加密密钥
  "crypto": {
    "appkey": "xxx",              // 必填
    "aes_key": "16位字符串",
    "aes_iv": "16位字符串",
    "media_key": "16位字符串",
    "media_iv": "16位字符串",
    "bundle_id": "com.pc.jyaw"
  },

  // 服务配置
  "server": {
    "port": 9527,
    "auth_token": "随机字符串",   // JWT 签名密钥，必填
    "allowed_origins": ["*"]
  },

  // YOLOv8 模型
  "yolo": {
    "face_model": "yolov8n-face.pt",
    "general_model": "yolov8n.pt"
  },

  // 默认参数
  "defaults": {
    "img_width": 800,
    "wm_width": 264,
    "cover_layout": "triple",
    "cover_candidates": 3,
    "video_bitrate": "2M",
    "video_fps": 30
  }
}
```

---

## 六、数据备份

```bash
# 备份数据库
cp data/omnipub.db data/omnipub_backup_$(date +%Y%m%d).db

# 备份水印文件
tar czf uploads_backup_$(date +%Y%m%d).tar.gz backend/uploads/

# 自动备份（crontab）
0 3 * * * cp /opt/OmniPublish/data/omnipub.db /backup/omnipub_$(date +\%Y\%m\%d).db
```

---

## 七、故障排查

| 问题 | 检查 |
|------|------|
| 无法访问 9527 端口 | `netstat -tlnp \| grep 9527`，检查防火墙 |
| FFmpeg 未找到 | `which ffmpeg`，确认 PATH |
| YOLOv8 模型下载慢 | 手动下载放到项目目录，配置 `yolo.face_model` 路径 |
| SQLite 写入失败 | 检查 `data/` 目录权限 |
| LLM API 超时 | 检查网络/代理，确认 `api_base` 可访问 |
| 视频处理 OOM | 减少并行平台数，或增加内存 |
