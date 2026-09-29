FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    DATABASE_URL=/data/app.db \
    SEED_ON_START=1

WORKDIR /srv/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY run.sh ./run.sh

# 数据库落在独立卷：重建镜像不丢运行数据。
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

# 容器启动即走 lifespan：迁移 -> 补样例（可用 SEED_ON_START=0 关闭）-> 概览回填。
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
