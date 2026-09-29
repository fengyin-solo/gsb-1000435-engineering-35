"""SQLite 数据访问层。

只依赖标准库 sqlite3，克隆即可用。约束：

- 每个请求/CLI 动作通过 ``session()`` 开一个连接，写操作包在事务里，
  抛异常整体回滚，正常结束统一提交；
- 迁移走 schema_migrations 版本表，已执行的迁移重复运行自动跳过；
- records 是唯一的运行数据表，概览与明细都从它取数（单一事实来源）。
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from app.config import settings

# 迁移 1：基础表结构。后续结构变更按版本号往 MIGRATIONS 里追加，禁止改动已发布的旧迁移。
MIGRATION_001 = """
CREATE TABLE IF NOT EXISTS records (
    id          INTEGER NOT NULL,
    module      TEXT NOT NULL,
    ref_no      TEXT NOT NULL,
    status      TEXT NOT NULL,
    pending     INTEGER NOT NULL,
    abnormal    INTEGER NOT NULL,
    data        TEXT NOT NULL,
    source      TEXT NOT NULL DEFAULT 'sample',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (module, id)
);
CREATE INDEX IF NOT EXISTS idx_records_module ON records(module);
CREATE INDEX IF NOT EXISTS idx_records_ref ON records(module, ref_no);

CREATE TABLE IF NOT EXISTS overview_snapshots (
    module       TEXT PRIMARY KEY,
    total_count  INTEGER NOT NULL,
    pending_count INTEGER NOT NULL,
    abnormal_count INTEGER NOT NULL,
    generated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS seed_meta (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

MIGRATIONS: dict[int, str] = {
    1: MIGRATION_001,
}


def _connect(database: str | None = None) -> sqlite3.Connection:
    target = database if database is not None else settings.db_path
    if target != ":memory:":
        Path(target).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def session(database: str | None = None) -> Iterator[sqlite3.Connection]:
    """开一个读写事务：异常回滚，成功提交。

    业务层只在这个上下文里写库；不要自己 commit，避免半成品数据落库。
    """
    conn = _connect(database)
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def run_migrations(database: str | None = None) -> list[int]:
    """执行尚未应用的迁移。每个迁移各自一个事务，失败整体回滚。

    返回本次新执行的版本号列表；重复执行返回空列表（幂等）。
    """
    applied: list[int] = []
    with session(database) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
        )
        done = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
        for version in sorted(MIGRATIONS):
            if version in done:
                continue
            conn.executescript(MIGRATIONS[version])
            conn.execute("INSERT INTO schema_migrations(version) VALUES (?)", (version,))
            applied.append(version)
    return applied


# --- records 表的序列化辅助：业务行 <-> 表行 ---------------------------------

def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = json.loads(row["data"])
    return {
        "id": row["id"],
        "status": row["status"],
        "pending": bool(row["pending"]),
        "abnormal": bool(row["abnormal"]),
        "source": row["source"],
        **data,
    }


def list_records(
    conn: sqlite3.Connection,
    module: str,
    *,
    keyword: str | None = None,
    keyword_field: str | None = None,
    status: str | None = None,
    page: int = 1,
    size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """按与明细列表完全相同的过滤口径取业务记录。"""
    where = "WHERE module = ?"
    params: list[Any] = [module]
    if status:
        where += " AND status = ?"
        params.append(status)
    total = conn.execute(f"SELECT COUNT(*) FROM records {where}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM records {where} ORDER BY id", params
    ).fetchall()
    items = [_decode(row) for row in rows]
    if keyword and keyword_field:
        items = [row for row in items if keyword in str(row.get(keyword_field, ""))]
    start = max(page - 1, 0) * size
    return items[start:start + size], len(items)


def all_records(conn: sqlite3.Connection, module: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM records WHERE module = ? ORDER BY id", (module,)
    ).fetchall()
    return [_decode(row) for row in rows]


def get_record(conn: sqlite3.Connection, module: str, entry_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM records WHERE module = ? AND id = ?", (module, entry_id)
    ).fetchone()
    return _decode(row)


def next_record_id(conn: sqlite3.Connection, module: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(id), 0) FROM records WHERE module = ?", (module,)
    ).fetchone()
    return int(row[0]) + 1


def insert_record(
    conn: sqlite3.Connection,
    *,
    module: str,
    entry_id: int,
    ref_no: str,
    status: str,
    pending: bool,
    abnormal: bool,
    data: dict[str, Any],
    source: str,
) -> int:
    payload = {key: value for key, value in data.items() if key != "id"}
    cur = conn.execute(
        "INSERT INTO records(id, module, ref_no, status, pending, abnormal, data, source)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            entry_id, module, ref_no, status,
            1 if pending else 0, 1 if abnormal else 0,
            json.dumps(payload, ensure_ascii=False), source,
        ),
    )
    return int(cur.lastrowid)


def update_record(
    conn: sqlite3.Connection,
    *,
    module: str,
    entry_id: int,
    status: str,
    pending: bool,
    abnormal: bool,
    data: dict[str, Any],
) -> None:
    payload = {key: value for key, value in data.items() if key != "id"}
    conn.execute(
        "UPDATE records SET status = ?, pending = ?, abnormal = ?, data = ?,"
        " updated_at = datetime('now') WHERE module = ? AND id = ?",
        (
            status, 1 if pending else 0, 1 if abnormal else 0,
            json.dumps(payload, ensure_ascii=False), module, entry_id,
        ),
    )


def count_records(
    conn: sqlite3.Connection, module: str
) -> tuple[int, int, int]:
    """原始业务记录口径的（总数, 待处理, 异常）。概览与对账共用。"""
    row = conn.execute(
        "SELECT COUNT(*),"
        " COALESCE(SUM(CASE WHEN pending = 1 THEN 1 ELSE 0 END), 0),"
        " COALESCE(SUM(CASE WHEN abnormal = 1 THEN 1 ELSE 0 END), 0)"
        " FROM records WHERE module = ?",
        (module,),
    ).fetchone()
    return int(row[0]), int(row[1]), int(row[2])


def record_exists(conn: sqlite3.Connection, module: str, entry_id: int) -> bool:
    return conn.execute(
        "SELECT 1 FROM records WHERE module = ? AND id = ?", (module, entry_id)
    ).fetchone() is not None


def delete_module_records(conn: sqlite3.Connection, module: str) -> int:
    cur = conn.execute("DELETE FROM records WHERE module = ?", (module,))
    return cur.rowcount
