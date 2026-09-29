"""温控监测接口：维护温度记录，覆盖标记预警、确认超温、数据补录等动作。

口径（字段、状态序列、动作）统一来自 app.modules，实现见 routers/_factory.py。
"""
from __future__ import annotations

from app.modules import MODULE_BY_NAME
from app.routers._factory import build_router
from app.services.temp_monitor import TempMonitorService

# 向后兼容：历史代码若从本模块取常量，仍然可用。
LIST_FIELDS = list(MODULE_BY_NAME["temp_monitor"].list_fields)
STATUSES = list(MODULE_BY_NAME["temp_monitor"].statuses)

service = TempMonitorService()
router = build_router(MODULE_BY_NAME["temp_monitor"], service)
