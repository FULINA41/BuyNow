FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY ./app ./app

# 暴露端口
EXPOSE 8080

# 启动命令（Cloud Run 需要监听 PORT 环境变量）
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
