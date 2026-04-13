# OmniPublish v2.0 — 轻量容器化 (Mac版直接打包)
FROM python:3.11-slim

# UTF-8 locale (修复中文文件名)
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

WORKDIR /app

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制全部文件
COPY server.py .
COPY OmniPublish_v2.html .
COPY config.json .
COPY yolov8n.pt .
COPY scripts/ ./scripts/

# 创建运行时目录
RUN mkdir -p uploads tmp

ENV PYTHONUNBUFFERED=1

EXPOSE 9527

CMD ["python", "server.py", "--port", "9527"]
