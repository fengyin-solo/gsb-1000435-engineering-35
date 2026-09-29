"""初始化写入：事务、回滚、幂等、运行数据优先。"""
from __future__ import annotations

import pytest

from app.seed import SEED_ROWS
from app.store import Store


def test_seed_writes_all_modules_once(store):
    total = sum(len(rows) for rows in SEED_ROWS.values())
    assert sum(len(store.rows(name)) for name in SEED_ROWS) == total


def test_seed_is_idempotent(store):
    first = store.seed_if_needed()
    second = store.seed_if_needed()
    assert first["inserted"] == 0  # fixture 已初始化
    assert second == {"inserted": 0, "already_seeded": True}


def test_seed_never_overwrites_runtime_data(store):
    store.update("shipment", 1, {"发货方": "真实客户"})
    store.seed_if_needed()
    assert store.find("shipment", 1)["发货方"] == "真实客户"


def test_seed_rollback_on_failure(monkeypatch):
    fresh = Store("sqlite:///:memory:")
    fresh.seed_if_needed()
    before = len(fresh.rows("shipment"))

    # 让初始化在写 meta 之前炸掉，整体回滚
    def boom(*_args, **_kwargs):
        raise RuntimeError("模拟写入失败")

    monkeypatch.setattr(fresh, "_set_meta", boom)
    with pytest.raises(RuntimeError):
        fresh.seed_if_needed()

    assert len(fresh.rows("shipment")) == before
    assert fresh.reconcile()["ok"]
    fresh.close()


def test_seed_runs_in_single_transaction_and_refreshes_overview(store):
    assert store.reconcile()["ok"]


def test_reset_works_in_local(store):
    # 先制造运行期改动，reset 后回到纯样例
    store.insert("shipment", {"运单编号": "X", "发货方": "a", "收货方": "b",
                              "status": "待发运", "pending": True, "abnormal": False})
    result = store.reset_to_seed()
    assert result["inserted"] == 54
    assert len(store.rows("shipment")) == 3


def test_reset_refuses_in_prod(monkeypatch):
    from types import SimpleNamespace
    from app import cli

    monkeypatch.setattr(cli, "settings", SimpleNamespace(env="prod"))
    assert cli.reset_cmd() == 3
