"""各业务模块 service 的通用基类。

明细筛选、创建、状态流转的实现都在这里，具体模块只提供 ModuleSpec。
概览重算与本类共用 records 表和同一份 pending/abnormal 口径。
所有写操作各自开启一个事务，业务校验不通过时抛 ValueError，由路由层转成失败结果，
此时不会执行任何写语句，天然整体回滚。
"""
from __future__ import annotations

from typing import Any

from app import db
from app.modules import ModuleSpec
from app.services import overview


class ModuleService:
    def __init__(self, spec: ModuleSpec) -> None:
        self.spec = spec

    # -- 读 ------------------------------------------------------------------

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
        database: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        with db.session(database) as conn:
            return db.list_records(
                conn,
                self.spec.name,
                keyword=keyword,
                keyword_field=self.spec.keyword_field,
                status=status,
                page=page,
                size=size,
            )

    def get_entry(self, entry_id: int, *, database: str | None = None) -> dict[str, Any] | None:
        with db.session(database) as conn:
            return db.get_record(conn, self.spec.name, entry_id)

    # -- 写（事务） -----------------------------------------------------------

    def create_entry(
        self, values: dict[str, Any], *, database: str | None = None
    ) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [
            field for field in self.spec.required_fields
            if not str(values.get(field) or "").strip()
        ]
        if missing:
            return None, missing
        with db.session(database) as conn:
            entry_id = db.next_record_id(conn, self.spec.name)
            entry = {"id": entry_id}
            entry.update({field: values.get(field) for field in self.spec.required_fields})
            status = self.spec.initial_status
            pending, abnormal = True, False
            ref_no = str(entry.get(self.spec.keyword_field, ""))
            db.insert_record(
                conn,
                module=self.spec.name,
                entry_id=entry_id,
                ref_no=ref_no,
                status=status,
                pending=pending,
                abnormal=abnormal,
                data=entry,
                source="runtime",
            )
            # 与写入同一事务内刷新概览快照：失败一起回滚，快照永不出现半成品。
            overview.recompute_snapshots(conn)
            entry["status"] = status
            entry["pending"] = pending
            entry["abnormal"] = abnormal
            entry["source"] = "runtime"
            return entry, []

    def run_action(
        self, entry_id: int, action: str, *, database: str | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        if action not in self.spec.action_rules:
            return None, f"动作「{action}」不属于{self.spec.label}可执行范围"
        target = self.spec.action_rules[action]
        if target not in self.spec.statuses:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        with db.session(database) as conn:
            entry = db.get_record(conn, self.spec.name, entry_id)
            if entry is None:
                return None, f"{self.spec.entity} {entry_id} 不存在或已归档"
            # pending/abnormal 仍由状态机推导，保证与概览口径一致。
            entry["status"] = target
            entry["pending"] = target != self.spec.terminal_status
            entry["abnormal"] = action in self.spec.negative_actions
            db.update_record(
                conn,
                module=self.spec.name,
                entry_id=entry_id,
                status=entry["status"],
                pending=entry["pending"],
                abnormal=entry["abnormal"],
                data=entry,
            )
            overview.recompute_snapshots(conn)
            return entry, f"{self.spec.entity}已{action}"
