"""概览重算与对账：概览必须和业务明细同源、同口径。"""
from __future__ import annotations

import pytest

from app import db
from app.seed import seed_transaction
from app.services import overview
from app.services.fuel import FuelService
from app.services.shipment import ShipmentService


def _setup(database):
    db.run_migrations()
    with db.session() as conn:
        seed_transaction(conn)
        overview.recompute_snapshots(conn)


def test_overview_matches_detail_lists(database):
    _setup(database)
    shipment = ShipmentService()
    with db.session() as conn:
        ov = overview.compute_overview(conn)
    modules = {item["name"]: item for item in ov["modules"]}
    for service, name in ((shipment, "shipment"), (FuelService(), "fuel")):
        items, total = service.list_entries(page=1, size=10000)
        agg = modules[name]
        assert agg["created"] == total
        assert agg["pending"] == sum(1 for row in items if row["pending"])
        assert agg["abnormal"] == sum(1 for row in items if row["abnormal"])


def test_recompute_rolls_back_with_outer_transaction(database):
    _setup(database)
    # 回填与其他写入同事务时，外层失败必须连带撤销本次重算，旧快照原样保留。
    with db.session() as conn:
        before = {row["module"]: (row["total_count"],) for row in
                  conn.execute("SELECT module, total_count FROM overview_snapshots")}
    with pytest.raises(RuntimeError):
        with db.session() as conn:
            conn.execute(
                "INSERT INTO records(id, module, ref_no, status, pending, abnormal, data, source)"
                " VALUES (99, 'shipment', 'SHIP-TX', '在途', 1, 0, '{}', 'runtime')"
            )
            overview.recompute_snapshots(conn)
            raise RuntimeError("外层事务失败")
    with db.session() as conn:
        after = {row["module"]: (row["total_count"],) for row in
                 conn.execute("SELECT module, total_count FROM overview_snapshots")}
        record_count = conn.execute(
            "SELECT COUNT(*) FROM records WHERE id = 99 AND module='shipment'"
        ).fetchone()[0]
    assert before == after
    assert record_count == 0


def test_reconcile_detects_stale_snapshot_and_recompute_fixes_it(database):
    _setup(database)
    # 模拟迁移/回填前的遗留原始记录：直接写库，不刷新快照。
    with db.session() as conn:
        conn.execute(
            "INSERT INTO records(id, module, ref_no, status, pending, abnormal, data, source)"
            " VALUES (98, 'shipment', 'SHIP-LEGACY', '待发运', 1, 0, '{}', 'runtime')"
        )
    with db.session() as conn:
        result = overview.reconcile(conn)
    assert result["ok"] is False
    module_diffs = [d for d in result["diffs"] if d["module"] == "shipment"]
    assert len(module_diffs) == 1
    assert module_diffs[0]["detail"][0] == module_diffs[0]["snapshot"][0] + 1

    with db.session() as conn:
        overview.recompute_snapshots(conn)
        fixed = overview.reconcile(conn)
    assert fixed["ok"] is True


def test_backfill_uses_original_records_not_flags_from_seed(database):
    """迁移/回填口径：直接重算原始记录，结果与明细列表一致。"""
    _setup(database)
    ShipmentService().run_action(1, "确认发运")
    FuelService().run_action(2, "驳回记录")
    with db.session() as conn:
        overview.recompute_snapshots(conn)
        result = overview.reconcile(conn)
        live = overview.compute_overview(conn)
    assert result["ok"] is True
    fuel = [m for m in live["modules"] if m["name"] == "fuel"][0]
    assert fuel["abnormal"] >= 1
