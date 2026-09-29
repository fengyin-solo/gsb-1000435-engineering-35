#!/usr/bin/env bash
# 可重复的本地后端启动：建虚拟环境 -> 装依赖 -> 加载 .env -> 建表/幂等初始化 -> 起服务
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt

# .env 存在则导出，但不覆盖调用方已经显式给出的环境变量（便于临时改端口/库文件）
if [ -f .env ]; then
  while IFS='=' read -r key value; do
    case "$key" in
      ''|'#'*) continue ;;  # 跳过空行与注释
    esac
    value="${value%\"}"; value="${value#\"}"
    if [ -z "${!key:-}" ]; then
      export "$key=$value"
    fi
  done < .env
fi

: "${APP_HOST:=127.0.0.1}"
: "${APP_PORT:=8000}"
export APP_HOST APP_PORT

# 初始化单独跑一遍：失败整体回滚，能在启动前看清错误；命令本身幂等，可重复执行
.venv/bin/python -m app.cli init >/dev/null

exec .venv/bin/uvicorn app.main:app --host "$APP_HOST" --port "$APP_PORT"
