"""pytest 公共夹具：每个用例用独立内存库，避免文件库互相污染。"""
from __future__ import annotations

import os

import pytest

# 必须在导入 app.config / app.store 之前定好口径
os.environ["APP_DATABASE_URL"] = "sqlite:///:memory:"
os.environ["APP_SEED_ON_STARTUP"] = "false"
os.environ["APP_OVERVIEW_TODAY"] = "2026-09-02"

from app.store import store as _store  # noqa: E402


@pytest.fixture()
def store():
    """每个用例重建内存库并幂等写入样例。"""
    _store.configure("sqlite:///:memory:")
    result = _store.seed_if_needed()
    assert result["inserted"] == 54
    yield _store
    _store.close()
