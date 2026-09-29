"""月台管理接口：维护装卸月台，覆盖分配作业、安排清洁、报修故障等动作。

口径（字段、状态序列、动作）统一来自 app.modules，实现见 routers/_factory.py。
"""
from __future__ import annotations

from app.modules import MODULE_BY_NAME
from app.routers._factory import build_router
from app.services.dock import DockService

# 向后兼容：历史代码若从本模块取常量，仍然可用。
LIST_FIELDS = list(MODULE_BY_NAME["dock"].list_fields)
STATUSES = list(MODULE_BY_NAME["dock"].statuses)

service = DockService()
router = build_router(MODULE_BY_NAME["dock"], service)
