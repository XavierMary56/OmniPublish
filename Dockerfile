# ═══ Stage 1: 构建前端 ═══
FROM node:18-slim AS frontend-builder
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --production=false
COPY frontend/ ./
# 跳过 vue-tsc 类型检查，直接 vite build（确保快速构建）
RUN npx vite build

# ═══ Stage 2: Python 后端 ═══
FROM python:3.11-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python 依赖
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端代码
COPY backend/ ./backend/
COPY config.json ./

# 复制前端构建产物
COPY --from=frontend-builder /build/dist ./frontend/dist/

# 创建数据目录
RUN mkdir -p data backend/uploads/watermarks

# 环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/backend

EXPOSE 9527

# 启动时初始化数据库 + 种子数据 + 启动服务
CMD python backend/migrations/002_seed_platforms.py && \
    python backend/main.py --host 0.0.0.0 --port 9527
