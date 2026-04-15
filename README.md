# OmniPublish V2.0

> 面向内容编辑团队的**全链路多平台发帖工作台**
> 6 步流水线自动推进 · 多平台并行分发 · 实时任务看板

---

## 快速开始

```bash
# 1. 克隆项目
git clone https://github.com/XavierMary56/OmniPublish.git
cd OmniPublish

# 2. 配置
cp config.json.example config.json
# 编辑 config.json，填入 api_key、crypto 等

# 3. 启动（Docker）
docker compose up -d

# 4. 访问
# http://localhost:9527   账号: admin / admin123
```

详细部署说明见 → [docs/DEPLOY.md](docs/DEPLOY.md)

---

## 项目结构

```
OmniPublish/
│
├── README.md                    ← 本文件
├── CLAUDE.md                    ← AI 编码规范（项目级）
├── Dockerfile                   ← 多阶段构建（前端 Node + 后端 Python）
├── docker-compose.yml           ← 生产部署编排（omnipub + PostgreSQL）
├── config.json.example          ← 配置文件模板（复制为 config.json 后填写）
├── .env                         ← 本地环境变量（.gitignore，不提交）
│
├── backend/                     ← FastAPI 后端
│   ├── main.py                  # 入口：注册路由、挂载静态资源、启动 DB
│   ├── config.py                # 配置加载（config.json → 全局对象）
│   ├── database.py              # PostgreSQL 连接池（asyncpg）+ 建表迁移
│   │
│   ├── routers/                 # API 路由层
│   │   ├── auth.py              # 登录 / 用户管理 /api/auth/*
│   │   ├── pipeline.py          # 流水线 6 步 /api/pipeline/*
│   │   ├── tasks.py             # 任务看板 /api/tasks/*
│   │   ├── platforms.py         # 业务线管理 /api/platforms/*
│   │   ├── accounts.py          # 账号管理 /api/accounts/*
│   │   ├── stats.py             # 数据统计 /api/stats/*
│   │   └── tools.py             # 工具箱 /api/tools/*
│   │
│   ├── services/                # 业务逻辑层
│   │   ├── pipeline_service.py  # 任务状态机、步骤推进、日志
│   │   ├── copywrite_service.py # Step 2：AI 文案生成（调用 LLM API）
│   │   ├── rename_service.py    # Step 3：图片批量重命名
│   │   ├── cover_service.py     # Step 4：封面生成（YOLOv8 人脸检测 + PIL 拼图）
│   │   ├── watermark_service.py # Step 5：图片/视频水印并行处理
│   │   ├── publish_service.py   # Step 6：CMS API 发布（AES 加密 + requests）
│   │   └── tools_service.py     # 工具箱：视频处理、压缩、合成等
│   │
│   ├── models/                  # Pydantic 数据模型
│   │   ├── common.py            # ApiResponse / PaginatedResponse
│   │   ├── task.py              # 任务相关请求/响应模型
│   │   └── user.py              # 用户模型
│   │
│   ├── middleware/
│   │   └── auth.py              # JWT 认证中间件
│   │
│   ├── websocket/
│   │   └── manager.py           # WebSocket 连接管理（任务进度推送）
│   │
│   ├── migrations/              # 数据库迁移 SQL（启动时自动执行）
│   ├── scripts/                 # 底层处理脚本（被 services 调用）
│   │   └── publish_api.py       # CMS 发布核心逻辑
│   └── uploads/                 # 水印文件 / 上传素材（volume 挂载持久化）
│
├── frontend/                    ← Vue 3 + TypeScript + Vite 前端 SPA
│   ├── src/
│   │   ├── main.ts              # 入口
│   │   ├── App.vue              # 根组件（侧边栏布局 + 路由出口）
│   │   ├── router.ts            # 路由定义
│   │   │
│   │   ├── api/
│   │   │   ├── http.ts          # Axios 实例（统一错误处理、Token 注入）
│   │   │   └── ws.ts            # WebSocket 封装（自动重连）
│   │   │
│   │   ├── stores/
│   │   │   ├── auth.ts          # 用户认证状态（Pinia）
│   │   │   └── pipeline.ts      # 流水线状态机（草稿持久化 / WebSocket 联动）
│   │   │
│   │   └── views/
│   │       ├── Login.vue        # 登录页
│   │       ├── Dashboard.vue    # 工作台（今日统计 + 最近任务）
│   │       ├── Pipeline.vue     # 发帖流水线（6 步向导核心页面）
│   │       ├── Tasks.vue        # 任务看板
│   │       ├── Platforms.vue    # 业务线管理
│   │       ├── Accounts.vue     # 账号管理
│   │       ├── Analytics.vue    # 数据统计
│   │       └── Toolbox.vue      # 工具箱
│   │
│   ├── index.html
│   ├── vite.config.ts           # Vite 配置（开发代理 → 9527）
│   └── package.json
│
├── scripts/                     ← 独立脚本（可单独调用，也被 services 复用）
│   ├── auto_deploy.sh           # VPS 自动拉取部署脚本（cron 每 5 分钟执行）
│   ├── publish_api.py           # CMS 发布 API（独立版本）
│   ├── copywrite_gen.py         # 文案生成脚本
│   ├── image_rename.py          # 图片重命名脚本
│   ├── make_cover.py            # 封面制作脚本
│   ├── image_watermark.py       # 图片水印脚本
│   ├── video_process.py         # 视频处理 7 合 1 脚本
│   └── cw_prompts/              # AI 文案提示词模板
│       ├── base_instruction.txt
│       ├── article_structure.txt
│       └── style_*.txt
│
└── docs/                        ← 文档
    ├── DEPLOY.md                # 部署文档（VPS / Docker / 自动部署）
    ├── USER_GUIDE.md            # 用户操作手册
    └── API.md                   # API 接口文档（Swagger: /docs）
```

---

## 技术栈

| 层 | 技术 |
|---|------|
| 后端 | FastAPI (Python 3.10+) + asyncpg |
| 前端 | Vue 3 + TypeScript + Vite + Pinia |
| 数据库 | PostgreSQL 15 |
| 实时推送 | WebSocket (FastAPI 内置) |
| 图片处理 | Pillow + YOLOv8 (ultralytics) |
| 视频处理 | FFmpeg |
| AI 文案 | OpenAI / 兼容 API |
| CMS 发布 | AES 加密 + requests |
| 部署 | Docker Compose + Nginx |

---

## 文档导航

| 文档 | 说明 |
|------|------|
| [docs/DEPLOY.md](docs/DEPLOY.md) | VPS 部署、自动部署配置、Nginx、备份、故障排查 |
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | 编辑操作手册（流水线 6 步、任务看板、业务线管理） |
| [docs/API.md](docs/API.md) | REST API 接口文档（也可访问 `/docs` 查看 Swagger UI） |

---

## 流水线概览

```
Step 1           Step 2           Step 3           Step 4           Step 5           Step 6
素材 & 平台  →   AI 文案生成  →  图片重命名  →   封面制作    →   水印处理    →  上传 & 发布
选文件夹         LLM 生成         批量重命名        YOLOv8 裁剪      各平台并行        CMS API
选平台           人工确认         人工确认          人工选择         图片+视频          多平台并行
                                                                    水印处理          自动发布
```

每步均可点「← 上一步」返回修改，数据不丢失。
