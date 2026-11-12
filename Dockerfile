# ---- Stage 1: 构建前端 ----
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# 复制 package 文件并安装依赖（使用淘宝源加速）
COPY frontend/package.json ./
RUN npm install --registry=https://registry.npmmirror.com

# 复制前端源码并构建
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: 构建后端 ----
FROM python:3.12-slim AS builder

WORKDIR /app

# 安装构建依赖（使用清华源加速）
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn

# ---- Stage 3: 生产镜像 ----
FROM python:3.12-slim

WORKDIR /app

# 从构建阶段复制 Python 依赖
COPY --from=builder /install /usr/local

# 从构建阶段复制前端构建产物
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# 复制应用代码
COPY config.py .
COPY main.py .
COPY models/ ./models/
COPY router/ ./router/
COPY service/ ./service/
COPY utils/ ./utils/

# 创建非 root 用户和数据目录
RUN groupadd -r appuser && useradd -r -g appuser appuser && mkdir -p /app/data && chown -R appuser:appuser /app
USER appuser

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health')" || exit 1

# 启动命令
CMD ["python", "main.py"]