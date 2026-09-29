"""制冷机组接口：维护制冷设备，覆盖停机检查、安排保养、复位故障等动作。

口径（字段、状态序列、动作）统一来自 app.modules，实现见 routers/_factory.py。
"""
from __future__ import annotations

from app.modules import MODULE_BY_NAME
from app.routers._factory import build_router
from app.services.reefer_unit import ReeferUnitService

# 向后兼容：历史代码若从本模块取常量，仍然可用。
LIST_FIELDS = list(MODULE_BY_NAME["reefer_unit"].list_fields)
STATUSES = list(MODULE_BY_NAME["reefer_unit"].statuses)

service = ReeferUnitService()
router = build_router(MODULE_BY_NAME["reefer_unit"], service)
