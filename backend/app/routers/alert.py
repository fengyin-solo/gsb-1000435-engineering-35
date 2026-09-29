"""报警管理接口：维护报警记录，覆盖确认报警、开始处理、消除报警等动作。

口径（字段、状态序列、动作）统一来自 app.modules，实现见 routers/_factory.py。
"""
from __future__ import annotations

from app.modules import MODULE_BY_NAME
from app.routers._factory import build_router
from app.services.alert import AlertService

# 向后兼容：历史代码若从本模块取常量，仍然可用。
LIST_FIELDS = list(MODULE_BY_NAME["alert"].list_fields)
STATUSES = list(MODULE_BY_NAME["alert"].statuses)

service = AlertService()
router = build_router(MODULE_BY_NAME["alert"], service)
