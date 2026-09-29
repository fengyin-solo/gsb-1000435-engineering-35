#!/usr/bin/env bash
# 后端本地开发启动：准备虚拟环境 -> 装依赖 -> 启动 uvicorn。
# 首次启动会自动执行幂等迁移并按 SEED_ON_START 决定是否补样例（默认补）。
set -euo pipefail
cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"

if [ ! -d .venv ]; then
  "$PYTHON_BIN" -m venv .venv || {
    echo "venv 创建失败：如为 Debian/Ubuntu，请先安装 ${PYTHON_BIN}-venv" >&2
    exit 1
  }
fi
.venv/bin/pip install -q -r requirements.txt

export APP_ENV="${APP_ENV:-local}"
export APP_HOST="${APP_HOST:-127.0.0.1}"
export APP_PORT="${APP_PORT:-8000}"
# 本地默认数据库落在 data/app.db，可用 DATABASE_URL 覆盖；生产设 SEED_ON_START=0。
export SEED_ON_START="${SEED_ON_START:-1}"

exec .venv/bin/uvicorn app.main:app --host "$APP_HOST" --port "$APP_PORT" --reload
