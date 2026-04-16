---
name: omnipublish
version: 2.0.0
description: "全链路多平台发帖工作台（单机版）。一键部署、启动、运维 OmniPublish V2.0（FastAPI + Vue 3 + SQLite）六步流水线：素材选择→AI文案→图片处理→封面制作→水印→多平台发布。"
emoji: 🚀
user-invocable: true
homepage: https://github.com/XavierMary56/OmniPublish
metadata:
  openclaw:
    requires:
      bins:
        - python3
        - node
        - npm
      anyBins:
        - ffmpeg
    install:
      - kind: brew
        package: python@3.11
      - kind: brew
        package: node
      - kind: brew
        package: ffmpeg
---

# OmniPublish V2.0 — 单机版工作台

全链路多平台发帖工作台。6 步流水线自动推进，一次多平台并行分发，SQLite 零配置单机运行。

---

## 激活时立即执行

当用户调用 /omnipublish 时，**立即运行以下状态检查和启动流程**：

```bash
# 1. 检查服务状态
curl -sf http://127.0.0.1:9527/api/ping

# 2. 如未运行，用 launcher.py 启动（自动处理 venv / 前端构建 / config）
python "$SKILL_DIR/launcher.py" start

# 3. 在浏览器打开（Windows）
start http://127.0.0.1:9527
# Mac/Linux:
# open http://127.0.0.1:9527
```

服务就绪后告知用户：
- 访问地址：http://127.0.0.1:9527
- 默认账号：admin / admin123

---

## 项目位置

技能目录：`$SKILL_DIR`（`.claude/skills/omnipublish/`）  
项目根目录：`$SKILL_DIR` 上三级（`launcher.py` 自动推导）

launcher.py 做的事：
1. 创建 Python venv（首次）
2. pip install 依赖
3. npm build 前端（首次，约 1-2 分钟）
4. 后台启动 `python backend/main.py`
5. 等待 `/api/ping` 就绪

---

## 常用操作命令（Bash 工具执行）

```bash
# 启动
python "$SKILL_DIR/launcher.py" start

# 停止
python "$SKILL_DIR/launcher.py" stop

# 重启
python "$SKILL_DIR/launcher.py" restart

# 状态
python "$SKILL_DIR/launcher.py" status

# 查看日志
tail -f "$SKILL_DIR/../../../logs/server.log"
```

---

## 本地 API（WebFetch 工具调用）

基础地址：`http://127.0.0.1:9527`

```
GET  /api/ping                健康检查 → {"ok":true}
POST /api/auth/login          登录 {username, password}
GET  /api/tasks               任务列表
GET  /api/platforms           业务线列表
GET  /api/stats/overview      统计数据
GET  /docs                    Swagger 交互式文档
```

登录示例：
```bash
curl -X POST http://127.0.0.1:9527/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

---

## 技术栈

| 层 | 技术 |
|---|------|
| 后端 | FastAPI (Python 3.10+) |
| 数据库 | SQLite（aiosqlite，data/omnipub.db） |
| 前端 | Vue 3 + TypeScript + Vite（首次运行自动构建） |
| 实时推送 | WebSocket（FastAPI 内置） |
| 图片处理 | Pillow + YOLOv8 |
| 视频处理 | FFmpeg（需本机安装） |
| AI 文案 | OpenAI / 兼容 API |

---

## 目录结构

```
OmniPublish/                         ← 项目根（$SKILL_DIR/../../../）
├── .claude/skills/omnipublish/
│   ├── SKILL.md                     ← 本文件
│   └── launcher.py                  ← 自适应启动器
├── config.json                      ← 运行时配置（首次自动创建）
├── data/omnipub.db                  ← SQLite 数据库（自动创建）
├── logs/server.log                  ← 服务日志
├── backend/                         ← FastAPI 后端
│   ├── main.py
│   ├── database.py                  ← SQLite + asyncpg 兼容层
│   ├── routers/
│   └── services/
└── frontend/
    ├── src/                         ← Vue 源码
    └── dist/                        ← 构建产物（首次运行自动生成）
```

---

## 流水线步骤

| 步骤 | currentStep | 后端路由 |
|------|-------------|---------|
| Step 1：素材 & 平台 | 0 | POST /api/pipeline |
| Step 2：AI 文案 | 1 | POST /step/2/generate |
| Step 3：图片重命名 | 2 | PUT /step/3/confirm |
| Step 4：封面制作 | 3 | POST /step/4/generate |
| Step 5：水印处理 | 4 | GET /step/5/plan, PUT /step/5/confirm |
| Step 6：上传发布 | 5 | POST /step/6/publish |

---

## 配置文件

`config.json`（从 `config.json.example` 自动创建）：

```jsonc
{
  "api_key": "sk-xxx",       // LLM API 密钥（AI 文案，可不填）
  "api_base": "https://api.openai.com",
  "server": { "port": 9527, "auth_token": "change-me" },
  "crypto": { "appkey": "", "aes_key": "", "aes_iv": "" }
}
```

修改后：`python "$SKILL_DIR/launcher.py" restart`

---

## 调试命令

```bash
# 查看实时日志
tail -f "$SKILL_DIR/../../../logs/server.log"

# 检查数据库
sqlite3 "$SKILL_DIR/../../../data/omnipub.db" ".tables"

# 检查 FFmpeg
ffmpeg -version

# 重置管理员密码
cd "$SKILL_DIR/../../../backend"
python -c "
import asyncio, bcrypt
from database import get_pool
async def reset():
    pool = await get_pool()
    async with pool.acquire() as conn:
        h = bcrypt.hashpw(b'newpass123', bcrypt.gensalt()).decode()
        await conn.execute(\"UPDATE users SET password=? WHERE username='admin'\", h)
        print('密码已重置为 newpass123')
asyncio.run(reset())
"
```

---

## 开发规范

- Python：snake_case 函数，PascalCase 类，async/await IO，asyncio.to_thread() 耗时操作
- Vue：TypeScript 严格模式，状态统一 Pinia，上一步不清除数据，变更后 saveDraft()

---

## 常见问题

| 问题 | 排查 |
|------|------|
| 水印处理失败 | `ffmpeg -version` 检查是否安装 |
| AI 文案报错 | 检查 config.json 的 api_key 和 api_base |
| 端口占用 | 修改 config.json 的 server.port，重启 |
| 前端空白 | `python launcher.py restart`（重新构建） |
| 数据库损坏 | `cp data/omnipub.db data/omnipub_backup.db` 恢复 |
