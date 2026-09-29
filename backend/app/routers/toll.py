"""通行费用接口：维护过路记录，覆盖确认费用、冲销费用等动作。

口径（字段、状态序列、动作）统一来自 app.modules，实现见 routers/_factory.py。
"""
from __future__ import annotations

from app.modules import MODULE_BY_NAME
from app.routers._factory import build_router
from app.services.toll import TollService

# 向后兼容：历史代码若从本模块取常量，仍然可用。
LIST_FIELDS = list(MODULE_BY_NAME["toll"].list_fields)
STATUSES = list(MODULE_BY_NAME["toll"].statuses)

service = TollService()
router = build_router(MODULE_BY_NAME["toll"], service)
