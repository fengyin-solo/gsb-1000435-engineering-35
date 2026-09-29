"""断链追溯业务规则：状态流转、字段校验与筛选口径统一在 registry 登记，本类只绑定模块名。"""
from __future__ import annotations

from app.services.base import CrudService

MODULE = "break_chain"


class BreakChainService(CrudService):
    module = MODULE
