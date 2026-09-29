"""样例数据定义与初始化写入。

口径约定（重要）：

- 样例数据只描述「原始业务记录」：编号字段 + 业务字段 + status；
- pending / abnormal 不允许样例自带，由加载器按 app.modules 的状态机统一推导，
  这样样例、接口流转、概览重算三处口径永远一致；
- 初始化写入在单个事务内完成，任意一条失败整体回滚；
- 已存在的 (module, id) 一律跳过，绝不覆盖运行中新增/改过的数据——
  运行数据口径优先于样例数据；重复执行保持幂等。
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from app import db
from app.config import settings
from app.modules import MODULES, ModuleSpec

# 每个模块第 1、2 条记录的状态；第 3 条统一取终态。
# 第 2 条保持非终态即可命中 pending，abnormal 只由负向动作产生（见下）。
_SECOND_STATUS: dict[str, str] = {
    "shipment": "在途",
    "temp_monitor": "接近临界",
    "vehicle": "已派单",
    "driver": "出车中",
    "cold_storage": "温度偏高",
    "loading": "装卸中",
    "alert": "已确认",
    "route": "临时管制",
    "reefer_unit": "怠速",
    # 油料管理的终态「已驳回」是负向动作目标，样例第 3 条落在该状态以展示异常。
    "fuel": "已录入",
    "delivery": "已签收",
    "break_chain": "调查中",
    "dock": "作业中",
    "package": "使用中",
    "toll": "已确认",
    "sanitation": "已消杀",
    "contract": "已签约",
    "insurance": "已投保",
}


# 编号前缀沿用历史样例的四位英文编码。
_REF_PREFIX: dict[str, str] = {
    "shipment": "SHIP", "temp_monitor": "TEMP", "vehicle": "VEHI",
    "driver": "DRIV", "cold_storage": "COLD", "loading": "LOAD",
    "alert": "ALER", "route": "ROUT", "reefer_unit": "REEF",
    "fuel": "FUEL", "delivery": "DELI", "break_chain": "BREA",
    "dock": "DOCK", "package": "PACK", "toll": "TOLL",
    "sanitation": "SANI", "contract": "CONT", "insurance": "INSU",
}


@dataclass(frozen=True)
class SeedRow:
    module: str
    entry_id: int
    status: str
    fields: dict[str, Any]


def _build_rows() -> list[SeedRow]:
    rows: list[SeedRow] = []
    for spec in MODULES:
        prefix = _REF_PREFIX[spec.name]
        statuses = (spec.initial_status, _SECOND_STATUS[spec.name], spec.terminal_status)
        date_fields = {"发运日期", "记录时间", "巡检时间", "开始时间", "触发时间", "加油日期",
                       "签收时间", "合同期限", "通行日期", "消杀日期", "起保日期", "止保日期"}
        for index, status in enumerate(statuses, start=1):
            fields: dict[str, Any] = {}
            for field_name in spec.list_fields:
                if field_name in date_fields:
                    fields[field_name] = f"2026-09-{index:02d}"
                elif field_name == spec.keyword_field:
                    fields[field_name] = f"{prefix}-{index:04d}"
                elif field_name in {"联系手机"}:
                    fields[field_name] = f"1380000{index:02d}"
                elif field_name in {"加油金额", "收费金额", "保额金额"}:
                    fields[field_name] = 12.5 * index
                else:
                    fields[field_name] = f"{spec.label}样例{index}"
            rows.append(SeedRow(spec.name, index, status, fields))
    return rows


SEED_ROWS: list[SeedRow] = _build_rows()


def derive_flags(spec: ModuleSpec, status: str) -> tuple[bool, bool]:
    """状态机唯一口径：非终态即待处理；负向动作的目标状态即异常。"""
    pending = status != spec.terminal_status
    abnormal_targets = {spec.action_rules[name] for name in spec.negative_actions}
    abnormal = status in abnormal_targets
    return pending, abnormal


def seed_transaction(
    conn: sqlite3.Connection,
    *,
    rows: list[SeedRow] | None = None,
    source: str = settings.data_source_seed,
) -> dict[str, int]:
    """在调用方给定的事务内写入样例。

    跳过任何已存在的 (module, id)，因此可与其他写入放在同一个事务里，
    也可被外层失败一起回滚。返回 inserted/skipped 计数。
    """
    rows = SEED_ROWS if rows is None else rows
    inserted = skipped = 0
    for row in rows:
        spec = next(item for item in MODULES if item.name == row.module)
        if row.status not in spec.statuses:
            raise ValueError(f"样例状态「{row.status}」不在 {spec.label} 的状态序列内")
        if db.record_exists(conn, row.module, row.entry_id):
            skipped += 1
            continue
        pending, abnormal = derive_flags(spec, row.status)
        ref_no = str(row.fields.get(spec.keyword_field, ""))
        db.insert_record(
            conn,
            module=row.module,
            entry_id=row.entry_id,
            ref_no=ref_no,
            status=row.status,
            pending=pending,
            abnormal=abnormal,
            data=row.fields,
            source=source,
        )
        inserted += 1
    return {"inserted": inserted, "skipped": skipped}


def seed_database(database: str | None = None) -> dict[str, int]:
    """对外入口：建表（幂等迁移）+ 单事务样例写入，失败整体回滚。"""
    db.run_migrations(database)
    with db.session(database) as conn:
        result = seed_transaction(conn)
        conn.execute(
            "INSERT INTO seed_meta(key, value) VALUES ('seed_version', '1')"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')"
        )
    return result
