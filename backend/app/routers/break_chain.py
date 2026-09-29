"""断链追溯接口：维护断链事件，覆盖发起调查、判定责任、关闭事件等动作。

口径（字段、状态序列、动作）统一来自 app.modules，实现见 routers/_factory.py。
"""
from __future__ import annotations

from app.modules import MODULE_BY_NAME
from app.routers._factory import build_router
from app.services.break_chain import BreakChainService

# 向后兼容：历史代码若从本模块取常量，仍然可用。
LIST_FIELDS = list(MODULE_BY_NAME["break_chain"].list_fields)
STATUSES = list(MODULE_BY_NAME["break_chain"].statuses)

service = BreakChainService()
router = build_router(MODULE_BY_NAME["break_chain"], service)
