"""运营概览：从原始业务记录重算，不允许有第二份口径。

设计要点：

- ``compute_overview`` 直接扫 records 表聚合，和各模块明细列表是同一张表、
  同一套 pending/abnormal 标志（写入时由状态机推导）；
- ``recompute_snapshots`` 在单个事务内整批替换 overview_snapshots，
  迁移 / 回填时调用，失败整体回滚；
- ``reconcile`` 用明细同口径重算并与快照逐模块比对，任何不一致都显式报出。
"""
from __future__ import annotations

import sqlite3

from app import db
from app.config import settings
from app.modules import MODULES


def compute_overview(conn: sqlite3.Connection) -> dict[str, object]:
    """按原始业务记录实时聚合概览。"""
    modules: list[dict[str, object]] = []
    for spec in MODULES:
        total, pending, abnormal = db.count_records(conn, spec.name)
        modules.append({
            "name": spec.name,
            "label": spec.label,
            "created": total,
            "pending": pending,
            "abnormal": abnormal,
        })
    cards = [
        {"label": "业务模块", "value": len(modules)},
        {"label": "记录总数", "value": sum(int(item["created"]) for item in modules)},
        {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
        {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
    ]
    return {
        "cards": cards,
        "modules": modules,
        "source": settings.data_source_runtime,
        "snapshot_at": None,
    }


def _snapshot_rows(conn: sqlite3.Connection) -> dict[str, tuple[int, int, int]]:
    rows = conn.execute(
        "SELECT module, total_count, pending_count, abnormal_count FROM overview_snapshots"
    ).fetchall()
    return {
        row["module"]: (int(row["total_count"]), int(row["pending_count"]), int(row["abnormal_count"]))
        for row in rows
    }


def get_overview(conn: sqlite3.Connection, *, prefer_snapshot: bool = False) -> dict[str, object]:
    """读取概览。

    默认实时口径（records 是单一事实来源）；prefer_snapshot=True 时返回快照
    并标注 snapshot_at，便于排查迁移/回填结果。
    """
    live = compute_overview(conn)
    if not prefer_snapshot:
        return live
    snap = _snapshot_rows(conn)
    generated = conn.execute(
        "SELECT MAX(generated_at) AS at FROM overview_snapshots"
    ).fetchone()["at"]
    modules = []
    for item in live["modules"]:
        name = str(item["name"])
        total, pending, abnormal = snap.get(name, (0, 0, 0))
        modules.append({**item, "created": total, "pending": pending, "abnormal": abnormal})
    return {
        "cards": [
            {"label": "业务模块", "value": len(modules)},
            {"label": "记录总数", "value": sum(int(m["created"]) for m in modules)},
            {"label": "待处理", "value": sum(int(m["pending"]) for m in modules)},
            {"label": "异常量", "value": sum(int(m["abnormal"]) for m in modules)},
        ],
        "modules": modules,
        "source": "snapshot",
        "snapshot_at": generated,
    }


def recompute_snapshots(conn: sqlite3.Connection) -> int:
    """在调用方事务内，按原始业务记录重算并整批替换概览快照。

    迁移或回填都走这里：先清空再写入，全部成功才随外层事务一起提交。
    """
    conn.execute("DELETE FROM overview_snapshots")
    written = 0
    for spec in MODULES:
        total, pending, abnormal = db.count_records(conn, spec.name)
        conn.execute(
            "INSERT INTO overview_snapshots"
            "(module, total_count, pending_count, abnormal_count)"
            " VALUES (?, ?, ?, ?)",
            (spec.name, total, pending, abnormal),
        )
        written += 1
    return written


def reconcile(conn: sqlite3.Connection) -> dict[str, object]:
    """对账：快照口径 vs 明细（records）口径，逐模块比对。

    返回 ok 与差异明细；ok=False 时应触发重算（recompute-overview）。
    """
    snap = _snapshot_rows(conn)
    diffs: list[dict[str, object]] = []
    for spec in MODULES:
        live = db.count_records(conn, spec.name)
        saved = snap.get(spec.name)
        if saved is None:
            diffs.append({"module": spec.name, "label": spec.label,
                          "reason": "缺少快照", "snapshot": None, "detail": live})
        elif saved != live:
            diffs.append({"module": spec.name, "label": spec.label,
                          "reason": "快照与明细不一致", "snapshot": saved, "detail": live})
    extra = sorted(set(snap) - {spec.name for spec in MODULES})
    for name in extra:
        diffs.append({"module": name, "label": name, "reason": "存在已下线模块的快照",
                      "snapshot": snap[name], "detail": None})
    return {"ok": not diffs, "diffs": diffs}
