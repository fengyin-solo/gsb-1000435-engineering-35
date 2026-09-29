"""承运合同接口：维护运输合同，覆盖签订合同、到期提醒、终止合同等动作。

口径（字段、状态序列、动作）统一来自 app.modules，实现见 routers/_factory.py。
"""
from __future__ import annotations

from app.modules import MODULE_BY_NAME
from app.routers._factory import build_router
from app.services.contract import ContractService

# 向后兼容：历史代码若从本模块取常量，仍然可用。
LIST_FIELDS = list(MODULE_BY_NAME["contract"].list_fields)
STATUSES = list(MODULE_BY_NAME["contract"].statuses)

service = ContractService()
router = build_router(MODULE_BY_NAME["contract"], service)
