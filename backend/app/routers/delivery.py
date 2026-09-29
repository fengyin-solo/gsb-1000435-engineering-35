"""签收回单接口：维护签收记录，覆盖正常签收、标记异常、登记拒收等动作。

口径（字段、状态序列、动作）统一来自 app.modules，实现见 routers/_factory.py。
"""
from __future__ import annotations

from app.modules import MODULE_BY_NAME
from app.routers._factory import build_router
from app.services.delivery import DeliveryService

# 向后兼容：历史代码若从本模块取常量，仍然可用。
LIST_FIELDS = list(MODULE_BY_NAME["delivery"].list_fields)
STATUSES = list(MODULE_BY_NAME["delivery"].statuses)

service = DeliveryService()
router = build_router(MODULE_BY_NAME["delivery"], service)
