"""报警管理业务规则：状态流转、字段校验与筛选口径统一收在 ModuleSpec 注册表。

本模块只做薄封装，通用实现见 services/base.py；口径（字段、状态、动作）见 app/modules.py。
"""
from __future__ import annotations

from app.modules import MODULE_BY_NAME
from app.services.base import ModuleService

SPEC = MODULE_BY_NAME["alert"]

# 向后兼容：保留历史常量名，外部若按模块导入仍可用，取值与注册表完全一致。
MODULE = SPEC.name
REQUIRED_FIELDS = list(SPEC.required_fields)
STATUS_ORDER = list(SPEC.statuses)
ACTION_RULES = dict(SPEC.action_rules)
NEGATIVE_ACTIONS = list(SPEC.negative_actions)


class AlertService(ModuleService):
    def __init__(self) -> None:
        super().__init__(SPEC)
