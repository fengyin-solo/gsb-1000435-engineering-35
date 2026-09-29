"""运营概览：数字必须能逐条回到原始业务记录，回填重算按同一口径。"""
from __future__ import annotations

from app.registry import MODULE_REGISTRY
from app.store import store


def _detail_counts(module: str, ref_date: str) -> dict[str, int]:
    meta = MODULE_REGISTRY[module]
    rows = store.rows(module)
    return {
        "total": len(rows),
        "created": sum(
            1 for row in rows
            if meta.date_field is not None and str(row.get(meta.date_field, ""))[:10] == ref_date
        ),
        "pending": sum(1 for row in rows if row.get("pending")),
        "abnormal": sum(1 for row in rows if row.get("abnormal")),
    }


def test_overview_matches_every_module_detail(store):
    ref = "2026-09-02"
    payload = store.overview()
    assert payload["ref_date"] == ref
    for module_row in payload["modules"]:
        name = module_row["name"]
        expected = _detail_counts(name, ref)
        for key in ("total", "created", "pending", "abnormal"):
            assert module_row[key] == expected[key], (name, key, module_row, expected)


def test_reconcile_clean_after_seed(store):
    check = store.reconcile("2026-09-02")
    assert check["ok"] is True and check["drift"] == []


def test_rebuild_recomputes_from_original_records(store):
    # 直接把快照改花，模拟历史脏数据；rebuild 必须按明细恢复
    with store.transaction():
        store.conn.execute("UPDATE overview_snap SET pending = 999, abnormal = 999 WHERE module = 'shipment'")
    assert store.reconcile("2026-09-02")["ok"] is False

    store.rebuild_overview("2026-09-02")
    check = store.reconcile("2026-09-02")
    assert check["ok"] is True


def test_created_counts_only_reference_date(store):
    # 样例里每个有日期字段的模块 2026-09-02 各 1 条
    payload = store.overview()
    dated = {m["name"]: m for m in payload["modules"] if m["has_date"]}
    assert len(dated) == 11
    assert all(m["created"] == 1 for m in dated.values())
    undated = {m["name"]: m for m in payload["modules"] if not m["has_date"]}
    assert len(undated) == 7
    assert all(m["created"] == 0 for m in undated.values())


def test_card_totals_equal_module_sum(store):
    payload = store.overview()
    cards = {c["label"]: c["value"] for c in payload["cards"]}
    assert cards["在册总量"] == sum(m["total"] for m in payload["modules"])
    assert cards["当日新增"] == sum(m["created"] for m in payload["modules"])
    assert cards["待处理"] == sum(m["pending"] for m in payload["modules"])
    assert cards["异常量"] == sum(m["abnormal"] for m in payload["modules"])


def test_action_then_overview_still_consistent(store):
    from app.services.shipment import ShipmentService

    ShipmentService().run_action(1, "确认到达")
    assert store.reconcile("2026-09-02")["ok"]
    shipment = [m for m in store.overview()["modules"] if m["name"] == "shipment"][0]
    # 已到达不是终态（后面还有签收/退回），id=1 仍待处理；id=2 同样待处理
    assert shipment["pending"] == 2
