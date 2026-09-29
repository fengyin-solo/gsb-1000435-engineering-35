"""车辆调度接口：维护冷藏车辆，覆盖派发出车、收车归队、报修车辆等动作。

口径（字段、状态序列、动作）统一来自 app.modules，实现见 routers/_factory.py。
"""
from __future__ import annotations

from app.modules import MODULE_BY_NAME
from app.routers._factory import build_router
from app.services.vehicle import VehicleService

# 向后兼容：历史代码若从本模块取常量，仍然可用。
LIST_FIELDS = list(MODULE_BY_NAME["vehicle"].list_fields)
STATUSES = list(MODULE_BY_NAME["vehicle"].statuses)

service = VehicleService()
router = build_router(MODULE_BY_NAME["vehicle"], service)
