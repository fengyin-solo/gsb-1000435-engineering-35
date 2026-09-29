"""迁移与样例初始化：事务、回滚、幂等、运行数据优先。"""
from __future__ import annotations

import pytest

from app import db
from app.modules import MODULES
from app.seed import SEED_ROWS, SeedRow, seed_transaction
from app.services.shipment import ShipmentService


def test_migrate_idempotent(database):
    first = db.run_migrations()
    second = db.run_migrations()
    assert first == [1]
    assert second == []
    with db.session() as conn:
        versions = [row[0] for row in conn.execute("SELECT version FROM schema_migrations")]
    assert versions == [1]


def test_seed_inserts_all_modules(database):
    db.run_migrations()
    with db.session() as conn:
        result = seed_transaction(conn)
    assert result["inserted"] == len(SEED_ROWS)
    assert result["skipped"] == 0
    # 每个模块 3 条样例。
    with db.session() as conn:
        for spec in MODULES:
            total, _, _ = db.count_records(conn, spec.name)
            assert total == 3


def test_seed_is_idempotent_and_never_overwrites_runtime(database):
    db.run_migrations()
    with db.session() as conn:
        seed_transaction(conn)

    # 运行侧把发运单 1 从「待发运」流转到「在途」。
    ShipmentService().run_action(1, "确认发运")

    # 再跑一次初始化：全部跳过，运行数据原样保留。
    with db.session() as conn:
        result = seed_transaction(conn)
    assert result["inserted"] == 0
    assert result["skipped"] == len(SEED_ROWS)
    entry = ShipmentService().get_entry(1)
    assert entry["status"] == "在途"
    assert entry["pending"] is True


def test_seed_rolls_back_as_a_single_transaction_on_failure(database):
    db.run_migrations()
    good = SEED_ROWS[0]
    bad = SeedRow(module="shipment", entry_id=2, status="不存在的状态", fields={"运单编号": "SHIP-BAD"})
    with pytest.raises(ValueError):
        with db.session() as conn:
            seed_transaction(conn, rows=[good, bad])
    # 第一条也必须随事务回滚，不留半成品。
    with db.session() as conn:
        total, _, _ = db.count_records(conn, "shipment")
    assert total == 0


def test_flags_follow_state_machine_not_seed_inputs(database):
    db.run_migrations()
    with db.session() as conn:
        seed_transaction(conn)
    with db.session() as conn:
        for spec in MODULES:
            for row in db.all_records(conn, spec.name):
                assert row["pending"] == (row["status"] != spec.terminal_status)
                abnormal_targets = {spec.action_rules[a] for a in spec.negative_actions}
                assert row["abnormal"] == (row["status"] in abnormal_targets)


def test_seed_rows_marked_as_sample_runtime_writes_marked_runtime(database):
    db.run_migrations()
    with db.session() as conn:
        seed_transaction(conn)
    with db.session() as conn:
        sources = {row["source"] for row in conn.execute("SELECT DISTINCT source FROM records")}
    assert sources == {"sample"}

    ShipmentService().create_entry({"运单编号": "SHIP-X", "发货方": "甲", "收货方": "乙"})
    with db.session() as conn:
        row = conn.execute(
            "SELECT source FROM records WHERE module='shipment' AND ref_no='SHIP-X'"
        ).fetchone()
    assert row["source"] == "runtime"
