# OmniPublish V2.0 — 部署文档

## 目录

- [一、环境要求](#一环境要求)
- [二、生产环境部署（VPS + Docker）](#二生产环境部署vps--docker)
- [三、自动部署（代码推送自动更新）](#三自动部署代码推送自动更新)
- [四、本地开发环境](#四本地开发环境)
- [五、配置文件详解](#五配置文件详解)
- [六、Nginx 反向代理](#六nginx-反向代理)
- [七、数据库维护与备份](#七数据库维护与备份)
- [八、故障排查](#八故障排查)

---

## 一、环境要求

### 生产环境（VPS）

| 组件 | 最低要求 | 说明 |
|------|---------|------|
| OS | Ubuntu 20.04+ / Debian 11+ | 推荐 Ubuntu 22.04 LTS |
| CPU | 2 核+ | 视频水印处理 CPU 密集 |
| 内存 | 4 GB+ | YOLOv8 模型加载约 500MB |
| 磁盘 | 50 GB+ | 素材文件 + 处理中间文件 |
| Docker Engine | 24.0+ | 含 docker compose v2 |
| Git | 2.x | 用于代码拉取 |

### 本地开发环境

| 组件 | 版本 |
|------|------|
| Python | 3.10+ |
| Node.js | 18+ |
| FFmpeg | 5.0+ |
| Docker Desktop | 最新版（可选） |

---

## 二、生产环境部署（VPS + Docker）

### 2.1 首次部署

```bash
# 1. SSH 登录 VPS
ssh root@your-vps-ip

# 2. 安装 Docker（如未安装）
curl -fsSL https://get.docker.com | sh
systemctl enable docker && systemctl start docker

# 3. 克隆项目
git clone https://github.com/XavierMary56/OmniPublish.git /opt/omnipublish
cd /opt/omnipublish

# 4. 创建配置文件
cp config.json.example config.json
nano config.json   # 填入 api_key、crypto 等真实值（见第五节）

# 5. 创建 PostgreSQL 数据卷（首次才需要）
docker volume create omnipublish_omnipub-pgdata

# 6. 构建镜像并启动
docker compose build
docker compose up -d

# 7. 验证服务正常
curl http://127.0.0.1:9527/api/ping
# 返回 {"ok":true,"version":"2.0.0"} 即为成功
```

### 2.2 docker-compose.yml 关键配置说明

```yaml
services:
  db:
    image: postgres:15-alpine
    ports:
      - "5433:5432"         # 宿主机端口 5433（避免与系统 pg 冲突）
    volumes:
      - pgdata:/var/lib/postgresql/data   # 数据持久化

  omnipub:
    build: .                # 每次部署从 Dockerfile 构建
    ports:
      - "9527:9527"         # 对外端口（建议 Nginx 反代后关闭直接暴露）
    volumes:
      - ./config.json:/app/config.json:ro          # 配置文件热挂载
      - ./backend/uploads:/app/backend/uploads     # 水印/上传文件持久化
      - ${MATERIALS_DIR:-/tmp/omnipub_materials}:/mnt/materials  # 素材目录
    environment:
      - DATABASE_URL=postgresql://omnipub:omnipub2026@db:5432/omnipub
      - OMNIPUB_AUTH_SECRET=omnipub-jwt-secret-x7k9m2p4v8w1   # 建议修改
```

> **安全提示**：生产环境请修改 `OMNIPUB_AUTH_SECRET` 为随机字符串，数据库密码也建议更换。

### 2.3 常用运维命令

```bash
cd /opt/omnipublish

# 查看服务状态
docker compose ps

# 查看实时日志
docker compose logs -f omnipub
docker compose logs -f db

# 重启服务（不重建镜像）
docker compose restart omnipub

# 停止服务
docker compose down

# 手动更新代码并重建
git pull origin main
docker compose build --no-cache
docker compose up -d
```

---

## 三、自动部署（代码推送自动更新）

项目内置 `scripts/auto_deploy.sh`，VPS 上配置 cron 后，每次 `git push` 到 main 分支，VPS 最多 5 分钟内自动拉取重建。

### 3.1 配置步骤

```bash
cd /opt/omnipublish

# 赋执行权限
chmod +x scripts/auto_deploy.sh

# 手动测试（当前无新提交会静默退出）
scripts/auto_deploy.sh

# 配置 cron（每 5 分钟检测一次）
crontab -e
```

在 crontab 中添加：

```
*/5 * * * * /opt/omnipublish/scripts/auto_deploy.sh
```

### 3.2 脚本行为说明

| 场景 | 行为 |
|------|------|
| main 分支无新提交 | 静默退出，不写日志 |
| 代码/前端/依赖有变更 | `git pull` → `docker compose build --no-cache` → `docker compose up -d` |
| 仅 config.json / 文档变更 | `git pull` → `docker compose up -d`（跳过重建，秒级生效） |
| 上次部署仍在运行 | 检测到锁文件，本次跳过 |
| 健康检查失败 | 写错误日志，需手动排查 |

### 3.3 查看部署日志

```bash
# 实时查看
tail -f /opt/omnipublish/logs/auto_deploy.log

# 只看错误
grep ERROR /opt/omnipublish/logs/auto_deploy.log
```

### 3.4 GitHub SSH 授权（如拉取需要密码）

```bash
# 生成 Deploy Key（只读权限）
ssh-keygen -t ed25519 -f ~/.ssh/omnipub_deploy -N ""
cat ~/.ssh/omnipub_deploy.pub
# 复制公钥 → GitHub 仓库 → Settings → Deploy keys → Add deploy key

# 配置 SSH（让 git 使用此 key）
cat >> ~/.ssh/config << 'EOF'
Host github.com
    IdentityFile ~/.ssh/omnipub_deploy
    IdentitiesOnly yes
EOF

# 测试
ssh -T git@github.com
```

---

## 四、本地开发环境

### 4.1 后端（Python）

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 启动后端（开发模式，自动重载）
python main.py
# 服务监听 http://localhost:9527
# Swagger UI: http://localhost:9527/docs
```

### 4.2 前端（Vue 3）

```bash
cd frontend
npm install
npm run dev
# 开发服务器 http://localhost:5173，API 请求自动代理到 9527
```

### 4.3 本地数据库

```bash
# 使用 Docker 跑一个 PostgreSQL（推荐）
docker run -d \
  --name omnipub-db \
  -e POSTGRES_DB=omnipub \
  -e POSTGRES_USER=omnipub \
  -e POSTGRES_PASSWORD=omnipub2026 \
  -p 5433:5432 \
  postgres:15-alpine
```

### 4.4 素材目录挂载（Windows）

在项目根目录创建 `.env` 文件（已加入 `.gitignore`）：

```
MATERIALS_DIR=D:/Users/Public/claude_ia
```

之后 `docker compose up` 会自动把该目录挂载到容器内的 `/mnt/materials`。

### 4.5 FFmpeg 安装

```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows
# 下载 https://ffmpeg.org/download.html，解压后加入系统 PATH
```

---

## 五、配置文件详解

配置文件路径：`config.json`（从 `config.json.example` 复制后修改）

```jsonc
{
  // ── LLM API（文案生成）──────────────────────────
  "api_base": "https://api.openai.com",   // API 服务地址
  "api_key": "sk-xxxx",                   // 必填，LLM API 密钥
  "cw_model": "gpt-4o",                   // 文案生成模型

  // ── 平台 API 加密参数（发帖用）────────────────────
  "crypto": {
    "appkey": "",          // 平台 AppKey
    "aes_key": "",         // AES 加密 Key（16位）
    "aes_iv": "",          // AES 加密 IV（16位）
    "media_key": "",       // 媒体上传加密 Key
    "media_iv": "",        // 媒体上传加密 IV
    "bundle_id": "com.pc.jyaw"
  },

  // ── 服务配置 ──────────────────────────────────────
  "server": {
    "port": 9527,
    "auth_token": "change-me-in-production",  // 必改！JWT 签名密钥
    "allowed_origins": ["*"],                  // 生产环境建议限制域名
    "token_expire_hours": 24                   // Token 有效期（小时）
  },

  // ── YOLOv8 人脸检测模型 ───────────────────────────
  "yolo": {
    "face_model": "yolov8n-face.pt",    // 首次运行自动下载
    "general_model": "yolov8n.pt"
  },

  // ── 默认参数（可在业务线配置中覆盖）──────────────
  "defaults": {
    "img_width": 800,           // 图片处理宽度
    "wm_width": 264,            // 水印默认宽度（px）
    "wm_position": "bottom-right",  // 水印默认位置
    "wm_opacity": 100,          // 水印不透明度（0-100）
    "cover_layout": "triple",   // 封面默认拼接方式
    "cover_candidates": 3,      // 封面候选数量
    "video_codec": "auto",      // 视频编码（auto/h264/h265）
    "video_bitrate": "2M",      // 视频码率
    "video_fps": 30             // 视频帧率
  }
}
```

> **注意**：修改 `config.json` 后需重启服务：`docker compose restart omnipub`

---

## 六、Nginx 反向代理

生产环境推荐用 Nginx 做反向代理，对外只暴露 80/443，9527 端口不对外开放。

```nginx
server {
    listen 80;
    server_name omnipub.yourdomain.com;

    # 静态资源缓存
    location ~* \.(js|css|png|jpg|ico|woff2)$ {
        proxy_pass http://127.0.0.1:9527;
        proxy_cache_valid 200 1d;
    }

    # API 请求
    location /api/ {
        proxy_pass http://127.0.0.1:9527;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        client_max_body_size 200M;    # 大视频上传限制
        proxy_read_timeout 300s;      # 长任务超时
    }

    # WebSocket（水印/发布进度实时推送）
    location /ws/ {
        proxy_pass http://127.0.0.1:9527;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400s;    # WebSocket 长连接
    }

    # 上传文件访问（水印预览等）
    location /uploads/ {
        proxy_pass http://127.0.0.1:9527;
    }

    # 前端 SPA（其余路径）
    location / {
        proxy_pass http://127.0.0.1:9527;
        proxy_set_header Host $host;
    }
}
```

**HTTPS 配置（推荐）**：

```bash
# 使用 certbot 申请免费证书
apt install certbot python3-certbot-nginx
certbot --nginx -d omnipub.yourdomain.com
```

---

## 七、数据库维护与备份

### 数据库位置

- PostgreSQL 数据卷：`omnipublish_omnipub-pgdata`（Docker 卷）
- 水印/上传文件：`/opt/omnipublish/backend/uploads/`

### 备份

```bash
# 备份数据库（导出 SQL）
docker exec omnipub-db pg_dump -U omnipub omnipub > /backup/omnipub_$(date +%Y%m%d).sql

# 备份水印和上传文件
tar czf /backup/uploads_$(date +%Y%m%d).tar.gz /opt/omnipublish/backend/uploads/

# 自动备份（加入 crontab，每天凌晨 3 点）
0 3 * * * docker exec omnipub-db pg_dump -U omnipub omnipub > /backup/omnipub_$(date +\%Y\%m\%d).sql
```

### 恢复数据库

```bash
# 从 SQL 文件恢复
docker exec -i omnipub-db psql -U omnipub omnipub < /backup/omnipub_20260415.sql
```

### 数据库迁移

每次更新后，迁移脚本位于 `backend/migrations/`，自动在启动时执行。

---

## 八、故障排查

### 服务无法启动

```bash
# 查看详细错误
docker compose logs omnipub --tail=50

# 常见原因：
# 1. config.json 格式错误 → 用 JSON 校验器检查
# 2. 端口 9527 已被占用 → lsof -i:9527
# 3. 数据库未就绪 → docker compose logs db
```

### 水印处理失败

```bash
# 确认 FFmpeg 在容器内可用
docker exec omnipub ffmpeg -version

# 查看处理日志
docker compose logs omnipub | grep -i watermark
```

### 文案生成超时

- 检查 `config.json` 中 `api_base` 和 `api_key` 是否正确
- VPS 检查出网是否可访问 OpenAI/Anthropic 接口：`curl https://api.openai.com`
- 可换用国内可访问的兼容 API 地址

### 健康检查接口

```bash
curl http://127.0.0.1:9527/api/ping
# 正常返回: {"ok": true, "version": "2.0.0"}
```

### 重置管理员密码

```bash
docker exec -it omnipub python -c "
import asyncio
from database import get_pool
import bcrypt

async def reset():
    pool = await get_pool()
    async with pool.acquire() as conn:
        hashed = bcrypt.hashpw(b'newpassword123', bcrypt.gensalt()).decode()
        await conn.execute(\"UPDATE users SET password_hash=\$1 WHERE username='admin'\", hashed)
        print('密码已重置为 newpassword123')

asyncio.run(reset())
"
```

### 常见问题速查

| 问题 | 排查方向 |
|------|---------|
| `invalid volume specification` | docker-compose.yml 有 Windows 路径，检查 MATERIALS_DIR 环境变量 |
| 9527 端口无响应 | `docker compose ps` 确认容器运行状态 |
| 水印图片位置不对 | 业务线管理中检查水印配置，或在水印步骤单独调整 |
| 登录 Token 频繁过期 | 修改 `config.json` 中 `token_expire_hours` |
| YOLOv8 模型下载慢 | 手动下载 `.pt` 文件放到项目根目录，配置对应路径 |
| PostgreSQL 连接失败 | 确认 db 容器健康：`docker compose ps` 查看 Health 状态 |
