#!/usr/bin/env bash
# =============================================================
# OmniPublish — 自动部署脚本
# 用法：VPS cron 每 5 分钟执行一次，有新提交才重建
# =============================================================
set -euo pipefail

# ── 配置区（按实际 VPS 路径修改）────────────────────────────
PROJECT_DIR="/opt/OmniPublish"          # VPS 上项目目录
COMPOSE_FILE="$PROJECT_DIR/docker-compose.yml"
LOG_FILE="$PROJECT_DIR/logs/auto_deploy.log"
LOCK_FILE="/tmp/omnipub_deploy.lock"
GIT_REMOTE="origin"
GIT_BRANCH="main"
# ─────────────────────────────────────────────────────────────

# 时间戳函数
ts() { date '+%Y-%m-%d %H:%M:%S'; }

# 日志函数
log() { echo "[$(ts)] $*" | tee -a "$LOG_FILE"; }
log_err() { echo "[$(ts)] ERROR: $*" | tee -a "$LOG_FILE" >&2; }

# 确保日志目录存在
mkdir -p "$(dirname "$LOG_FILE")"

# ── 防并发锁 ─────────────────────────────────────────────────
if [ -f "$LOCK_FILE" ]; then
    LOCK_PID=$(cat "$LOCK_FILE" 2>/dev/null || echo "")
    if [ -n "$LOCK_PID" ] && kill -0 "$LOCK_PID" 2>/dev/null; then
        log "已有部署进程运行中 (PID=$LOCK_PID)，跳过"
        exit 0
    else
        log "发现过期锁文件，清理"
        rm -f "$LOCK_FILE"
    fi
fi
echo $$ > "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT

# ── 进入项目目录 ──────────────────────────────────────────────
cd "$PROJECT_DIR" || { log_err "项目目录不存在: $PROJECT_DIR"; exit 1; }

# ── 检查是否有新提交 ──────────────────────────────────────────
git fetch "$GIT_REMOTE" "$GIT_BRANCH" --quiet 2>>"$LOG_FILE"

LOCAL_SHA=$(git rev-parse HEAD)
REMOTE_SHA=$(git rev-parse "$GIT_REMOTE/$GIT_BRANCH")

if [ "$LOCAL_SHA" = "$REMOTE_SHA" ]; then
    # 无新提交，静默退出（不写日志，避免刷日志）
    exit 0
fi

log "======================================================"
log "检测到新提交: ${LOCAL_SHA:0:7} → ${REMOTE_SHA:0:7}"
log "开始自动部署..."

# ── 拉取代码 ──────────────────────────────────────────────────
log "[1/4] git pull $GIT_REMOTE $GIT_BRANCH"
git pull "$GIT_REMOTE" "$GIT_BRANCH" 2>>"$LOG_FILE" || {
    log_err "git pull 失败，终止部署"
    exit 1
}

# ── 判断是否需要重建镜像 ──────────────────────────────────────
# 以下文件变更才触发完整 docker compose build
REBUILD_TRIGGERS=(
    "Dockerfile"
    "backend/requirements.txt"
    "frontend/package.json"
    "frontend/package-lock.json"
    "backend/"
    "frontend/src/"
    "frontend/public/"
)

CHANGED_FILES=$(git diff --name-only "${LOCAL_SHA}" "${REMOTE_SHA}" 2>/dev/null || echo "")
NEED_REBUILD=false

for trigger in "${REBUILD_TRIGGERS[@]}"; do
    if echo "$CHANGED_FILES" | grep -q "^${trigger}"; then
        NEED_REBUILD=true
        log "  变更触发重建: $trigger"
        break
    fi
done

# ── 部署 ──────────────────────────────────────────────────────
if [ "$NEED_REBUILD" = true ]; then
    log "[2/4] docker compose build (前端+后端)"
    docker compose -f "$COMPOSE_FILE" build --no-cache 2>>"$LOG_FILE" || {
        log_err "docker compose build 失败"
        exit 1
    }

    log "[3/4] docker compose up -d (重启服务)"
    docker compose -f "$COMPOSE_FILE" up -d 2>>"$LOG_FILE" || {
        log_err "docker compose up 失败"
        exit 1
    }
else
    log "[2/4] 仅 config.json 或文档变更，热更新配置 (重启不重建)"
    docker compose -f "$COMPOSE_FILE" up -d 2>>"$LOG_FILE" || {
        log_err "docker compose up 失败"
        exit 1
    }
fi

# ── 健康检查 ──────────────────────────────────────────────────
log "[4/4] 等待服务就绪..."
sleep 8
MAX_RETRY=10
for i in $(seq 1 $MAX_RETRY); do
    if curl -sf "http://127.0.0.1:9527/api/ping" >/dev/null 2>&1; then
        log "✅ 部署成功！服务已就绪 (第 ${i} 次检查)"
        break
    fi
    if [ "$i" -eq "$MAX_RETRY" ]; then
        log_err "❌ 健康检查失败，服务可能未正常启动，请手动检查"
        log_err "查看日志: docker compose -f $COMPOSE_FILE logs --tail=50 omnipub"
        exit 1
    fi
    log "  等待中... ($i/$MAX_RETRY)"
    sleep 5
done

log "======================================================"
