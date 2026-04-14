# OmniPublish V2.0 — 多阶段构建
# Stage 1: 构建前端
FROM node:22-alpine AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --legacy-peer-deps
COPY frontend/ .
RUN npm run build

# Stage 2: 运行后端
FROM python:3.11-slim

# UTF-8 locale
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONIOENCODING=utf-8

# 系统依赖: ffmpeg + OpenCV 运行时
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    locales \
    && sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen \
    && locale-gen \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8

# 项目结构: /app/ 是 ROOT_DIR
#   /app/backend/  — Python 代码 (BACKEND_DIR)
#   /app/frontend/dist/ — 前端产物
#   /app/config.json
#   /app/data/  — SQLite 备用目录
WORKDIR /app/backend

# Python 依赖
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 后端代码
COPY backend/ /app/backend/

# 前端构建产物
COPY --from=frontend-build /build/dist /app/frontend/dist

# 配置文件（docker-compose volume 会覆盖）
COPY config.json /app/config.json

# 创建运行时目录
RUN mkdir -p /app/backend/uploads /app/backend/uploads/watermarks /app/tmp /app/data

ENV PYTHONUNBUFFERED=1

EXPOSE 9527

CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "9527"]
