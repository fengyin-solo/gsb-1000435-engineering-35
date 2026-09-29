"""业务服务公共基类：列表筛选、登记、状态流转的口径全部来自 registry 登记表。

各模块的 service 只声明模块名，具体规则（必填字段、状态序列、异常动作、
关键字段、日期字段）一律查 ModuleMeta，避免 18 份拷贝各自漂移。
"""
from __future__ import annotations

from typing import Any

from app.registry import MODULE_REGISTRY, ModuleMeta
from app.store import store


class CrudService:
    module: str = ""

    def __init__(self) -> None:
        self.meta: ModuleMeta = MODULE_REGISTRY[self.module]

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(self.module)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get(self.meta.code_field, ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(self.module, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in self.meta.required if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        entry: dict[str, Any] = {field: values.get(field) for field in self.meta.required}
        entry["status"] = self.meta.statuses[0]
        entry["pending"] = True
        entry["abnormal"] = False
        return store.insert(self.module, entry), []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(self.module, entry_id)
        if entry is None:
            return None, f"{self.meta.entity} {entry_id} 不存在或已归档"
        target = self.meta.actions.get(action)
        if target is None:
            return None, f"动作「{action}」不属于{self.meta.scope}可执行范围"
        if target not in self.meta.statuses:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        updated = store.update(
            self.module,
            entry_id,
            {
                "status": target,
                "pending": target != self.meta.terminal_status,
                "abnormal": action in self.meta.negatives,
            },
        )
        if updated is None:  # 并发下记录刚好被删：事务里读不到
            return None, f"{self.meta.entity} {entry_id} 不存在或已归档"
        return updated, f"{self.meta.entity}已{action}"
