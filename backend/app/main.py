"""冷链物流温控管理平台 后端服务入口。

启动：uvicorn app.main:app --host 127.0.0.1 --port 8000
健康检查：GET /api/health
初始化/回填命令：python -m app.cli init|rebuild|reconcile
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import ROUTERS
from app.store import store

logger = logging.getLogger("coldchain")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 启动初始化在一个事务内完成：失败整体回滚，进程不会带着半份数据起来；
    # local 默认补样例，prod 默认只建表并把空概览刷成 0，由 APP_SEED_ON_STARTUP 控制。
    result = store.setup()
    if result.get("inserted"):
        logger.info("初始化写入完成：新增样例 %s 条", result["inserted"])
    check = store.reconcile()
    if not check["ok"]:  # 快照理论上随写随刷，这里只做启动期兜底
        logger.warning("概览与明细不一致，启动时自动重算：%s", check["drift"])
        store.rebuild_overview()
    yield
    store.close()


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in ROUTERS:
    app.include_router(module.router)


@app.get("/api/health")
def health() -> dict[str, object]:
    """健康检查：确认服务已经监听、业务模块已登记、概览快照与明细对得上。"""
    check = store.reconcile()
    return {
        "ok": True,
        "app": settings.app_name,
        "env": settings.env,
        "modules": len(store.module_names()),
        "overview_consistent": check["ok"],
        "overview_ref_date": check["ref_date"],
    }


@app.get("/api/overview")
def overview() -> dict[str, object]:
    """运营概览：数字由业务明细在同一事务内重算，口径与运单明细逐条对得上。"""
    return store.overview()
