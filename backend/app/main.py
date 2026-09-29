"""冷链物流温控管理平台 后端服务入口。

启动：uvicorn app.main:app --host 127.0.0.1 --port 8000
健康检查：GET /api/health

启动顺序固定：迁移（建表） -> 按开关补写样例 -> 重算概览快照。
迁移与播种都是幂等的，重复启动不会覆盖运行数据。
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import db
from app.config import settings
from app.routers import ROUTERS
from app.seed import seed_transaction
from app.services import overview


def bootstrap() -> dict[str, int]:
    """启动引导：迁移 + 样例补写 + 概览回填，全部成功才算启动就绪。"""
    migrated = db.run_migrations()
    seeded = {"inserted": 0, "skipped": 0}
    with db.session() as conn:
        if settings.seed_on_start:
            seeded = seed_transaction(conn)
        # 无论本次有没有补样例，都按当前原始记录重算一次快照，保证两者对得上。
        overview.recompute_snapshots(conn)
    return {"migrated": len(migrated), **seeded}


@asynccontextmanager
async def lifespan(_: FastAPI):
    bootstrap()
    yield


app = FastAPI(title="冷链物流温控管理平台", version="1.1.0", lifespan=lifespan)

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
    """健康检查：服务监听且初始化已完成。"""
    with db.session() as conn:
        module_count = conn.execute("SELECT COUNT(DISTINCT module) FROM records").fetchone()[0]
    return {
        "ok": True,
        "app": settings.app_name,
        "env": settings.env,
        "modules": module_count,
        "data_source": settings.data_source_runtime,
    }


@app.get("/api/overview")
def get_overview(view: str = "live") -> dict[str, object]:
    """运营概览。

    - view=live（默认）：按原始业务记录实时聚合，是权威口径；
    - view=snapshot：返回最近一次迁移/回填写入的快照。
    """
    with db.session() as conn:
        return overview.get_overview(conn, prefer_snapshot=view == "snapshot")


@app.post("/api/admin/recompute-overview")
def admin_recompute_overview() -> dict[str, object]:
    """按原始业务记录重算并回填概览快照（单个事务，失败回滚）。"""
    with db.session() as conn:
        written = overview.recompute_snapshots(conn)
        result = overview.reconcile(conn)
    return {"ok": True, "message": f"已重算 {written} 个模块的概览", "reconcile": result}


@app.get("/api/admin/reconcile")
def admin_reconcile() -> dict[str, object]:
    """对账：概览快照 vs 原始业务记录（明细同口径）。"""
    with db.session() as conn:
        return overview.reconcile(conn)
