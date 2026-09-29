"""端到端接口：初始化 -> 概览 -> 明细 -> 动作 -> 概览重算，全链路对得上。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client(store):
    # lifespan 会触发 seed_if_needed；内存库已由 conftest 建好表
    with TestClient(app) as c:
        yield c


def test_health_reports_consistency(client):
    body = client.get("/api/health").json()
    assert body["ok"] is True
    assert body["modules"] == 18
    assert body["overview_consistent"] is True
    assert body["overview_ref_date"] == "2026-09-02"


def test_overview_payload_shape(client):
    body = client.get("/api/overview").json()
    assert body["ref_date"] == "2026-09-02"
    assert len(body["modules"]) == 18
    labels = [card["label"] for card in body["cards"]]
    assert labels == ["业务模块", "在册总量", "当日新增", "待处理", "异常量"]


def test_overview_detail_roundtrip(client):
    overview = client.get("/api/overview").json()
    for module_row in overview["modules"]:
        name = module_row["name"]
        detail = client.get(f"/api/{name}?size=200").json()
        assert detail["total"] == module_row["total"], name
        assert len(detail["items"]) == module_row["total"], name


def test_action_reflects_in_overview(client):
    before = client.get("/api/overview").json()
    before_fuel = next(m for m in before["modules"] if m["name"] == "fuel")

    resp = client.post(
        "/api/fuel/1/actions", json={"values": {"action": "驳回记录"}}
    )
    assert resp.json()["ok"] is True

    after = client.get("/api/overview").json()
    fuel = next(m for m in after["modules"] if m["name"] == "fuel")
    # 驳回记录：id=1 进入终态（待处理 -1）并标记异常（异常量 +1）
    assert fuel["abnormal"] == before_fuel["abnormal"] + 1
    assert fuel["pending"] == before_fuel["pending"] - 1


def test_create_entry_appears_in_detail_and_overview(client):
    resp = client.post(
        "/api/shipment", json={"values": {"运单编号": "SHIP-9999", "发货方": "甲", "收货方": "乙"}}
    )
    assert resp.json()["ok"] is True
    detail = client.get("/api/shipment?keyword=SHIP-9999").json()
    assert detail["total"] == 1

    overview = client.get("/api/overview").json()
    shipment = next(m for m in overview["modules"] if m["name"] == "shipment")
    assert shipment["total"] == 4


def test_missing_required_fields_returns_readable_message(client):
    resp = client.post("/api/shipment", json={"values": {"运单编号": "X"}})
    body = resp.json()
    assert body["ok"] is False
    assert "缺少必填字段" in body["message"]
