"""测试夹具：每个用例独立的临时 SQLite 文件，互不污染。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture()
def database(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DATABASE_URL", db_path)
    monkeypatch.setenv("SEED_ON_START", "0")
    yield db_path
