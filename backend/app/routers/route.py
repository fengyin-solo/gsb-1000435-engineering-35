"""线路规划接口：维护运输线路，覆盖启用线路、临时封闭、废弃线路等动作。

口径（字段、状态序列、动作）统一来自 app.modules，实现见 routers/_factory.py。
"""
from __future__ import annotations

from app.modules import MODULE_BY_NAME
from app.routers._factory import build_router
from app.services.route import RouteService

# 向后兼容：历史代码若从本模块取常量，仍然可用。
LIST_FIELDS = list(MODULE_BY_NAME["route"].list_fields)
STATUSES = list(MODULE_BY_NAME["route"].statuses)

service = RouteService()
router = build_router(MODULE_BY_NAME["route"], service)
