# OmniPublish V2.0 — 项目级 CLAUDE.md

## 1. 项目概述

OmniPublish V2.0 是面向内容编辑团队的**全链路发帖工作台**。
核心能力：6 步流水线自动推进 + 一次多平台并行分发 + 任务追踪看板。

---

## 2. 技术栈

| 层 | 技术 | 版本 |
|---|------|------|
| 后端 | FastAPI (Python) | Python 3.10+ |
| 前端 | Vue 3 + TypeScript + Vite | Vue 3.4+ |
| 数据库 | PostgreSQL 15 | Docker 容器 |
| 实时推送 | WebSocket (fastapi) | 内置 |
| 图片处理 | Pillow + YOLOv8 | ultralytics 8.0+ |
| 视频处理 | FFmpeg (外部二进制) | FFmpeg 5.0+ |
| AI 文案 | OpenAI/Anthropic API | 兼容格式 |
| CMS 发布 | AES 加密 + requests | pycryptodome |

---

## 3. 目录结构

```
OmniPublish/
├── CLAUDE.md              ← 本文件
├── backend/
│   ├── main.py            FastAPI 入口
│   ├── config.py          配置加载
│   ├── database.py        PostgreSQL 连接 (asyncpg)
│   ├── routers/           API 路由
│   ├── services/          业务逻辑
│   ├── models/            Pydantic 数据模型
│   ├── middleware/         中间件（认证等）
│   ├── scripts/           现有脚本（import 调用）
│   ├── migrations/        数据库迁移 SQL
│   ├── uploads/           上传文件（水印等）
│   └── websocket/         WebSocket 管理器
├── frontend/              Vue 3 SPA
├── docs/                  文档
│   ├── DEPLOY.md          部署文档
│   ├── USER_GUIDE.md      用户操作手册
│   └── API.md             API 接口文档
├── data/                  运行时数据（SQLite 文件）
├── config.json            全局配置
└── docker-compose.yml     容器部署
```

---

## 4. 运行方式

### 开发环境

```bash
# 后端
cd backend
pip install -r requirements.txt
python main.py

# 前端
cd frontend
npm install
npm run dev
```

### 生产环境

```bash
docker compose up -d
```

---

## 5. 编码规范

### Python 后端

- 函数和变量：`snake_case`
- 类名：`PascalCase`
- 常量：`UPPER_SNAKE_CASE`
- 类型注解：所有函数参数和返回值必须有类型注解
- 异步优先：IO 操作全部使用 `async/await`
- 错误处理：不静默吞掉异常，使用 `HTTPException` 返回
- 文件限制：单文件不超过 400 行，超过则拆分

### 脚本调用规范

- **禁止 subprocess 调用脚本**：所有脚本通过 `import` 方式调用核心函数
- 长耗时操作用 `asyncio.to_thread()` 包装
- 进度通过 WebSocket 推送，不依赖 stdout 解析

### API 规范

- RESTful 资源路由
- 统一响应格式：`{"code": 0, "data": {}, "message": ""}`
- 错误码：0=成功，40x=客户端错误，50x=服务端错误
- 分页：`?page=1&limit=20`，返回 `{"items": [], "total": N}`

---

## 6. 数据库规范

- 使用 PostgreSQL 15（Docker 容器 `omnipub-db`，端口 5433）
- 连接方式：asyncpg 异步连接池
- 所有表必须有 `created_at` 和 `updated_at`
- JSON 字段用 TEXT 类型存储（`json.dumps` / `json.loads`）
- 索引命名：`idx_{表名}_{字段名}`
- 迁移脚本位于 `backend/migrations/`

---

## 7. 安全规范

- 密钥/凭据**禁止硬编码**，全部从 `config.json` 或环境变量加载
- 用户密码 bcrypt 哈希存储
- API 认证使用 JWT（Bearer Token）
- 文件上传限制 50MB
- 请求体限制 10MB
- CMS 平台凭据 AES 加密存储

---

## 8. 流水线状态机

6 步流水线的状态流转严格按 `02_流水线状态机定义.md` 执行：
- 每步状态：`pending → running → awaiting_confirm → done / failed`
- Step 5/6 按平台拆分为子任务，并行处理
- 单平台失败不阻塞其他平台

---

## 9. 禁止项

- 不删除 `data/` 目录下的数据库文件
- 不修改 `scripts/` 下脚本的核心算法逻辑（只改接口封装）
- 不在前端存储敏感信息（token 用 httpOnly cookie 或 memory）
- 不对外暴露 9527 端口（生产环境通过 Nginx 反代）
