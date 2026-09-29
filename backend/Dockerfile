FROM python:3.12-slim
WORKDIR /srv/app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    APP_DATABASE_URL=sqlite:///data/app.db

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# 运行期数据目录单独挂卷；镜像里先建好，保证普通用户也能写
RUN mkdir -p data

EXPOSE 8000

# 启动前先幂等初始化（建表+按需补样例，失败整体回滚），再起 HTTP 服务
CMD ["sh", "-c", "python -m app.cli init && uvicorn app.main:app --host ${APP_HOST} --port ${APP_PORT}"]
