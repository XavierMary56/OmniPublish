---
name: omnipublish
description: OmniPublish v2.0 - 全链路多平台发帖工作台。帮助开发、调试、部署 OmniPublish V2.0（FastAPI + Vue 3 + PostgreSQL + Docker）。当用户提到 OmniPublish、发帖流水线、水印处理、平台发布、pipeline 等时激活。
user-invocable: true
---

# OmniPublish V2.0 — 开发者上下文

## 项目概述

面向内容编辑团队的**全链路多平台发帖工作台**。

- **核心流程**：6 步流水线（素材选择 → AI 文案 → 图片重命名 → 封面制作 → 水印处理 → 上传发布）
- **多平台并行**：单次任务同时发布到多个平台（最多 30+ 个）
- **实时推送**：WebSocket 推送水印进度、发布状态
- **草稿恢复**：localStorage 保存草稿，页面刷新后数据不丢

---

## 项目路径

- **本地代码**：`D:\Users\Public\php20250819\2026www\OmniPublish`
- **VPS 部署**：`/opt/omnipublish`（`76.13.218.203`，SSH key `~/.ssh/id_ed25519`）
- **GitHub**：`https://github.com/XavierMary56/OmniPublish`
- **访问地址**：`http://76.13.218.203:9527`（或 VPS 配置的域名）

---

## 技术栈

| 层 | 技术 |
|---|------|
| 后端 | FastAPI (Python 3.10+) + asyncpg |
| 前端 | Vue 3 + TypeScript + Vite + Pinia |
| 数据库 | PostgreSQL 15（Docker 容器 `omnipub-db`，端口 5433） |
| 实时推送 | WebSocket（FastAPI 内置，`/ws/pipeline/{task_id}`） |
| 图片处理 | Pillow + YOLOv8（ultralytics）人脸检测 |
| 视频处理 | FFmpeg（外部二进制） |
| AI 文案 | OpenAI / 兼容 API（`config.json` 配置） |
| CMS 发布 | AES 加密 + requests |
| 部署 | Docker Compose + Nginx |

---

## 目录结构（关键文件）

```
OmniPublish/
├── Dockerfile                    多阶段构建（Node 构建前端 → Python 运行后端）
├── docker-compose.yml            omnipub + omnipub-db 两个容器
├── config.json                   运行时配置（api_key、crypto、server 等）
├── .env                          本地环境变量（MATERIALS_DIR，不提交 git）
│
├── backend/
│   ├── main.py                   FastAPI 入口，挂载路由和静态文件
│   ├── config.py                 从 config.json 加载全局配置对象
│   ├── database.py               asyncpg 连接池 + 建表迁移（启动时自动执行）
│   │
│   ├── routers/
│   │   ├── auth.py               /api/auth/* 登录、用户管理
│   │   ├── pipeline.py           /api/pipeline/* 流水线 6 步核心路由
│   │   ├── tasks.py              /api/tasks/* 任务看板
│   │   ├── platforms.py          /api/platforms/* 业务线 CRUD + 水印上传
│   │   ├── accounts.py           /api/accounts/* 平台账号管理
│   │   ├── stats.py              /api/stats/* 数据统计
│   │   └── tools.py              /api/tools/* 工具箱（视频处理等）
│   │
│   ├── services/
│   │   ├── pipeline_service.py   任务状态机、步骤推进、日志写入
│   │   ├── copywrite_service.py  Step 2：调 LLM API 生成文案
│   │   ├── rename_service.py     Step 3：图片批量重命名
│   │   ├── cover_service.py      Step 4：YOLOv8 人脸检测 + PIL 拼图生成封面
│   │   ├── watermark_service.py  Step 5：图片/视频水印并行处理（asyncio）
│   │   ├── publish_service.py    Step 6：CMS API 发布
│   │   └── tools_service.py      工具箱各功能实现
│   │
│   ├── models/
│   │   ├── common.py             ApiResponse / PaginatedResponse
│   │   ├── task.py               流水线请求/响应 Pydantic 模型
│   │   └── user.py               用户模型
│   │
│   ├── middleware/auth.py        JWT Bearer Token 认证
│   ├── websocket/manager.py      WebSocket 连接管理，按 task_id 分组推送
│   ├── migrations/               建表 SQL，database.py 启动时自动执行
│   └── scripts/publish_api.py    CMS 发布底层逻辑
│
├── frontend/src/
│   ├── App.vue                   根组件（侧边栏布局 + 路由出口）
│   ├── router.ts                 路由定义
│   ├── api/
│   │   ├── http.ts               Axios 实例（统一错误处理、自动注入 Token）
│   │   └── ws.ts                 WebSocket 封装（自动重连）
│   ├── stores/
│   │   ├── auth.ts               用户认证状态（Pinia）
│   │   └── pipeline.ts           流水线状态机（草稿持久化、WebSocket 联动）
│   └── views/
│       ├── Pipeline.vue          6 步向导核心页面（最复杂，约 1200 行）
│       ├── Dashboard.vue         工作台（统计卡片 + 最近任务）
│       ├── Tasks.vue             任务看板（筛选、搜索、展开子任务）
│       ├── Platforms.vue         业务线管理（水印配置、分类库）
│       ├── Accounts.vue          平台账号管理
│       ├── Analytics.vue         数据统计图表
│       └── Toolbox.vue           工具箱
│
└── scripts/
    ├── auto_deploy.sh            VPS 自动部署脚本（cron 每 5 分钟执行）
    └── *.py / *.sh               底层处理脚本（被 services 调用，也可单独运行）
```

---

## 流水线步骤 → 代码对应关系

| 步骤 | 前端（currentStep） | 后端路由 | 服务 |
|------|-------------------|---------|------|
| Step 1：素材 & 平台 | 0 | `POST /api/pipeline` | pipeline_service |
| Step 2：AI 文案 | 1 | `POST /step/2/generate` `PUT /step/2/confirm` | copywrite_service |
| Step 3：图片重命名 | 2 | `PUT /step/3/confirm` | rename_service |
| Step 4：封面制作 | 3 | `POST /step/4/generate` `PUT /step/4/confirm` | cover_service |
| Step 5：水印处理 | 4 | `GET /step/5/plan` `PUT /step/5/confirm` | watermark_service |
| Step 6：上传发布 | 5 | `POST /step/6/publish` | publish_service |

**currentStep** 在前端是 0-5 索引，对应 UI 显示的「第 1-6 步」。

---

## 数据库关键表

```sql
tasks              -- 主任务表（task_id、folder_path、target_platforms、current_step）
task_steps         -- 各步骤状态（step、status、data JSON）
platform_tasks     -- 各平台子任务（wm_status、wm_progress、publish_status）
platforms          -- 业务线配置（水印文件路径、位置、CMS API 参数）
users              -- 用户表（username、password_hash、role）
task_logs          -- 操作日志
```

---

## API 统一响应格式

```json
{"code": 0, "data": {}, "message": "ok"}
```

错误时 `code` 非 0，`data` 为 null，`message` 说明原因。

---

## WebSocket 事件类型

```json
{"type": "step_changed", "step": 4, "status": "done"}
{"type": "platform_update", "platform_id": 3, "wm_status": "done", "wm_progress": 100}
{"type": "platform_update", "platform_id": 3, "publish_status": "published"}
```

前端监听在 `pipeline.ts` 的 `connectWs()` 方法中。

---

## 草稿持久化（localStorage）

`saveDraft()` 保存的字段：
- taskId, taskNo, currentStep, status
- folderPath, folderId, selectedPlatforms, fileManifest
- copyResult, renamePrefix
- **coverCandidates, selectedCover**（封面候选，防止上一步丢失）

---

## 水印处理关键逻辑

`watermark_service.process_all_platforms(task_id, overrides=[])`:
1. 从 DB 读取各平台水印配置（`get_watermark_plan`）
2. 应用前端传入的 `overrides`（位置、宽度、模式、缩放可覆盖）
3. `asyncio.gather()` 并行处理所有平台
4. 每个平台通过 WebSocket 推送进度

前端在 `PUT /step/5/confirm` 时传入 `{"overrides": [...]}` 完成单平台微调。

---

## 部署与运维

### 快速部署

```bash
# VPS 首次
git clone https://github.com/XavierMary56/OmniPublish.git /opt/omnipublish
cd /opt/omnipublish && cp config.json.example config.json
docker volume create omnipublish_omnipub-pgdata
docker compose build && docker compose up -d

# 验证
curl http://127.0.0.1:9527/api/ping
```

### 自动部署（已配置）

VPS cron 每 5 分钟执行 `/opt/omnipublish/scripts/auto_deploy.sh`：
- 有新 commit → `git pull` + `docker compose build --no-cache` + `docker compose up -d`
- 仅文档/config 变更 → 跳过重建，直接 `docker compose up -d`
- 日志：`/opt/omnipublish/logs/auto_deploy.log`

### SSH 操作 VPS

```bash
ssh -i ~/.ssh/id_ed25519 root@76.13.218.203
```

### 常用命令

```bash
# 查日志
docker compose -f /opt/omnipublish/docker-compose.yml logs -f omnipub

# 重启（不重建）
docker compose -f /opt/omnipublish/docker-compose.yml restart omnipub

# 手动触发部署
/opt/omnipublish/scripts/auto_deploy.sh
```

---

## 开发规范

### Python 后端
- 函数/变量：`snake_case`，类名：`PascalCase`
- 所有 IO 操作用 `async/await`
- 长耗时操作（图片/视频处理）用 `asyncio.to_thread()` 包装
- 禁止 subprocess 调用脚本，通过 `import` 调用核心函数
- 单文件不超过 400 行，超过拆分

### Vue 前端
- TypeScript 严格模式，不用 `any`
- 状态统一放 Pinia store，不在组件内维护跨步骤状态
- 上一步返回不清除已有数据（`handlePrev` 只改 `currentStep`）
- 重要数据变更后调用 `store.saveDraft()` 持久化

---

## 配置文件关键字段

```jsonc
{
  "api_key": "sk-xxx",        // LLM API 密钥（文案生成）
  "cw_model": "gpt-4o",       // 文案模型
  "server": {
    "auth_token": "xxx",       // JWT 签名密钥（必改）
    "port": 9527
  },
  "crypto": {                  // CMS 发布 AES 加密参数
    "appkey": "", "aes_key": "", "aes_iv": "",
    "media_key": "", "media_iv": ""
  }
}
```

修改后执行：`docker compose restart omnipub`

---

## 常见任务处理思路

**新增业务线字段** → `backend/models/task.py` 加 Pydantic 模型 + `backend/routers/platforms.py` 加路由 + `backend/database.py` 加迁移 SQL + `frontend/src/views/Platforms.vue` 加表单字段

**新增流水线步骤** → `pipeline.ts` 加 store 状态和 API 方法 + `Pipeline.vue` 加 `v-if="store.currentStep === N"` 区块 + `backend/routers/pipeline.py` 加路由 + `backend/services/` 加服务

**调试 WebSocket 不推送** → 检查 `websocket/manager.py` 的 `send_to_task(task_id, ...)` 调用 + 前端 `ws.ts` 的 `on('event_type', handler)` 事件名是否匹配

**水印处理失败** → 检查 `watermark_service.py` 的 `_process_single_platform` + 容器内 `ffmpeg -version` 是否可用 + `/opt/omnipublish/logs/auto_deploy.log` 查错误

**前端步骤数据丢失** → 检查 `pipeline.ts` 的 `saveDraft()` 是否包含该字段 + `loadDraft()` 是否对应恢复 + `loadTask()` 从服务端重新加载是否覆盖了本地数据
