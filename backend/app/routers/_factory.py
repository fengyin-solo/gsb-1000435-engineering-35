"""按 ModuleSpec 生成各业务模块路由的工厂。

历史上每个 router 文件都是同一份模板拷贝；现在只保留一份实现，
字段/状态/动作的口径全部来自 app.modules，避免路由层和概览层各说各话。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.modules import ModuleSpec
from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.base import ModuleService


def build_router(spec: ModuleSpec, service: ModuleService) -> APIRouter:
    router = APIRouter(prefix=f"/api/{spec.name}", tags=[spec.label])
    entity = spec.entity
    status_hint = "、".join(spec.statuses)
    keyword_hint = f"按{spec.keyword_field}检索"

    @router.get("", response_model=PageResult[dict])
    def list_entries(
        keyword: str | None = Query(default=None, description=keyword_hint),
        status: str | None = Query(default=None, description=status_hint),
        page: int = 1,
        size: int = settings.page_size_default,
    ) -> PageResult[dict]:
        """按关键字与状态过滤列表；没有数据时返回空页，不报错。"""
        if size > settings.page_size_max:
            raise HTTPException(
                status_code=400,
                detail=f"每页最多 {settings.page_size_max} 条，请缩小分页范围",
            )
        items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
        return PageResult(items=items, total=total, page=page, size=size)

    @router.get("/export")
    def export_entries() -> dict[str, Any]:
        """导出当前模块清单：全量数据，与明细列表同口径。"""
        items, total = service.list_entries(page=1, size=10000)
        return {"module": spec.name, "total": total, "items": items}

    @router.get("/{entry_id}", response_model=dict)
    def get_entry(entry_id: int) -> dict:
        """读取单条明细；不存在时给出可读的错误说明。"""
        entry = service.get_entry(entry_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"{entity} {entry_id} 不存在或已归档")
        return entry

    @router.post("", response_model=ActionResult)
    def create_entry(payload: EntryPayload) -> ActionResult:
        """登记一条记录，缺字段时说明原因而不是静默丢弃。"""
        entry, missing = service.create_entry(payload.values)
        if missing:
            return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
        return ActionResult(ok=True, message=f"{entity}已登记", entry=entry)

    @router.post("/{entry_id}/actions", response_model=ActionResult)
    def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
        """对单条记录执行状态流转；不允许的动作会被拦下并说明原因。"""
        action = str(payload.values.get("action") or "").strip()
        entry, message = service.run_action(entry_id, action)
        if entry is None:
            return ActionResult(ok=False, message=message)
        return ActionResult(ok=True, message=message, entry=entry)

    return router
