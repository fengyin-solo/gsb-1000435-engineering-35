"""冷库运营接口：维护冷库库区，覆盖开始除霜、安排检修、恢复运行等动作。

口径（字段、状态序列、动作）统一来自 app.modules，实现见 routers/_factory.py。
"""
from __future__ import annotations

from app.modules import MODULE_BY_NAME
from app.routers._factory import build_router
from app.services.cold_storage import ColdStorageService

# 向后兼容：历史代码若从本模块取常量，仍然可用。
LIST_FIELDS = list(MODULE_BY_NAME["cold_storage"].list_fields)
STATUSES = list(MODULE_BY_NAME["cold_storage"].statuses)

service = ColdStorageService()
router = build_router(MODULE_BY_NAME["cold_storage"], service)
