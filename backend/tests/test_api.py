"""API 层：兼容历史出入参契约，并保证概览与明细对得上。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app
from app.seed import seed_transaction


@pytest.fixture()
def client(database):
    db.run_migrations()
    with db.session() as conn:
        seed_transaction(conn)
    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    body = client.get("/api/health").json()
    assert body["ok"] is True
    assert body["modules"] == 18
    assert body["data_source"] == "runtime"


def test_list_shape_and_filtering(client):
    body = client.get("/api/shipment").json()
    assert set(body) == {"items", "total", "page", "size"}
    assert body["total"] == 3

    assert client.get("/api/shipment", params={"keyword": "SHIP-0001"}).json()["total"] == 1
    assert client.get("/api/shipment", params={"status": "在途"}).json()["total"] == 1
    assert client.get("/api/shipment", params={"status": "不存在"}).json()["total"] == 0
    assert client.get("/api/shipment", params={"size": 201}).status_code == 400


def test_create_and_action_flow(client):
    created = client.post("/api/shipment", json={
        "values": {"运单编号": "SHIP-1001", "发货方": "甲", "收货方": "乙"}
    }).json()
    assert created["ok"] is True
    entry_id = created["entry"]["id"]
    assert created["entry"]["status"] == "待发运"

    moved = client.post(f"/api/shipment/{entry_id}/actions",
                        json={"values": {"action": "确认发运"}}).json()
    assert moved["entry"]["status"] == "在途"
    assert moved["entry"]["pending"] is True

    missing = client.post("/api/shipment", json={"values": {"运单编号": "X"}}).json()
    assert missing["ok"] is False
    assert "缺少必填字段" in missing["message"]

    bad = client.post("/api/shipment/1/actions", json={"values": {"action": "非法"}}).json()
    assert bad["ok"] is False

    assert client.get("/api/shipment/9999").status_code == 404


def test_overview_live_reflects_detail_tables(client):
    overview = client.get("/api/overview").json()
    assert overview["source"] == "runtime"
    cards = {card["label"]: card["value"] for card in overview["cards"]}
    assert cards["业务模块"] == 18
    assert cards["记录总数"] == 54

    for module in overview["modules"]:
        items = client.get(f"/api/{module['name']}").json()
        assert module["created"] == items["total"], module["name"]
        assert module["pending"] == sum(1 for row in items["items"] if row["pending"])
        assert module["abnormal"] == sum(1 for row in items["items"] if row["abnormal"])


def test_reconcile_and_recompute_endpoints(client):
    # 模拟「迁移前的旧数据」：绕过服务层直接落一条原始记录，快照暂时落后。
    with db.session() as conn:
        conn.execute(
            "INSERT INTO records(id, module, ref_no, status, pending, abnormal, data, source)"
            " VALUES (99, 'shipment', 'SHIP-LEGACY', '在途', 1, 0,"
            " '{\"运单编号\": \"SHIP-LEGACY\"}', 'runtime')"
        )
    stale = client.get("/api/admin/reconcile").json()
    assert stale["ok"] is False

    fixed = client.post("/api/admin/recompute-overview").json()
    assert fixed["ok"] is True
    assert fixed["reconcile"]["ok"] is True
    assert client.get("/api/admin/reconcile").json()["ok"] is True


def test_snapshot_refreshes_in_same_transaction_as_writes(client):
    # 走正常写接口时，快照与明细在同一事务内刷新，无需人工回填。
    client.post("/api/shipment", json={
        "values": {"运单编号": "SHIP-2002", "发货方": "甲", "收货方": "乙"}
    })
    assert client.get("/api/admin/reconcile").json()["ok"] is True
    snap = client.get("/api/overview", params={"view": "snapshot"}).json()
    live = client.get("/api/overview").json()
    assert snap["modules"] == live["modules"]


def test_export_endpoint(client):
    body = client.get("/api/shipment/export").json()
    assert body["module"] == "shipment"
    assert body["total"] == 3
    assert len(body["items"]) == 3
