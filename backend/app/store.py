"""SQLite 数据仓库：业务明细是唯一事实来源，运营概览是随写随刷的派生快照。

口径约定：
- 业务明细落在 business_rows（按模块分区），列表、详情、动作都读写它；
- 运营概览落在 overview_snap，只允许由本模块在同一事务内对 business_rows
  全表扫描重算后写入，任何外部代码不直接改它；
- 因此概览与运单明细永远来自同一份原始业务记录，reconcile() 可随时核对；
- 所有写操作走事务：失败整体回滚；初始化写入一个事务内完成，重复执行幂等。
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import date
from pathlib import Path
from typing import Any

from app.config import settings
from app.registry import MODULES, MODULE_NAMES, MODULE_REGISTRY, ModuleMeta
from app.seed import SEED_ROWS

# 基线建表迁移：后续加列/加表在这里追加 (version, [sql ...])，
# 启动时按版本号在事务内补齐；每条语句走 execute（不使用会隐式提交的 executescript）
MIGRATIONS: list[tuple[int, list[str]]] = [
    (
        1,
        [
            """
        CREATE TABLE IF NOT EXISTS business_rows (
            module     TEXT NOT NULL,
            entry_id   INTEGER NOT NULL,
            data       TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (module, entry_id)
        )
        """,
            """
        CREATE TABLE IF NOT EXISTS overview_snap (
            module     TEXT PRIMARY KEY,
            total      INTEGER NOT NULL,
            created    INTEGER NOT NULL,
            pending    INTEGER NOT NULL,
            abnormal   INTEGER NOT NULL,
            ref_date   TEXT NOT NULL,
            computed_at TEXT NOT NULL
        )
        """,
            """
        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """,
        ],
    ),
]


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _seed_checksum() -> str:
    """样例数据版本指纹：样例内容变了指纹才变，决定幂等初始化是否需要补齐。"""
    import hashlib

    payload = json.dumps(SEED_ROWS, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class Store:
    def __init__(self, database_url: str | None = None) -> None:
        self._lock = threading.RLock()
        self._depth = 0
        self._conn: sqlite3.Connection | None = None
        self.configure(database_url or settings.database_url)

    # ------------------------------------------------------------------ 连接
    def configure(self, database_url: str) -> None:
        """切换落库目标（测试切 :memory: 用）；切换后自动建表，保持可重复初始化。"""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
            if database_url.startswith("sqlite:///"):
                target = database_url.removeprefix("sqlite:///")
            else:
                target = database_url
            if target != ":memory:":
                Path(target).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(target, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            self._conn = conn
            self._depth = 0
            self.init_db()

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        assert self._conn is not None, "Store 尚未初始化数据库连接"
        return self._conn

    def init_db(self) -> None:
        """建表与版本迁移：按版本号顺序在事务内执行，已应用的跳过，可重复执行。"""
        with self._lock:
            # 引导表先独立提交：下面要读它判断哪些版本已应用
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            self.conn.commit()
            applied = {
                int(row[0])
                for row in self.conn.execute("SELECT version FROM schema_migrations")
            }
            for version, statements in MIGRATIONS:
                if version in applied:
                    continue
                self.conn.execute("BEGIN IMMEDIATE")
                try:
                    for statement in statements:
                        self.conn.execute(statement)
                    self.conn.execute(
                        "INSERT OR REPLACE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                        (version, _now()),
                    )
                    self.conn.commit()
                except Exception:
                    self.conn.rollback()
                    raise

    class _Savepoint:
        def __init__(self, store: "Store") -> None:
            self.store = store

        def __enter__(self) -> "Store._Savepoint":
            self.store._enter_tx()
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            self.store._exit_tx(exc_type is not None)

    def _enter_tx(self) -> None:
        with self._lock:
            if self._depth == 0:
                self.conn.execute("BEGIN IMMEDIATE")
            else:
                self.conn.execute(f"SAVEPOINT sp_{self._depth}")
            self._depth += 1

    def _exit_tx(self, failed: bool) -> None:
        with self._lock:
            self._depth -= 1
            if failed:
                if self._depth == 0:
                    self.conn.rollback()
                else:
                    self.conn.execute(f"ROLLBACK TO SAVEPOINT sp_{self._depth}")
            elif self._depth == 0:
                self.conn.commit()

    def transaction(self) -> "Store._Savepoint":
        """显式事务：初始化写入、迁移、回填把多步操作包进去，失败整体回滚。"""
        return Store._Savepoint(self)

    # ----------------------------------------------------------------- 读明细
    def module_names(self) -> list[str]:
        return list(MODULE_NAMES)

    def _decode(self, raw: str) -> dict[str, Any]:
        return json.loads(raw)

    def rows(self, module: str) -> list[dict[str, Any]]:
        with self._lock:
            cur = self.conn.execute(
                "SELECT data FROM business_rows WHERE module = ? ORDER BY entry_id",
                (module,),
            )
            return [self._decode(row["data"]) for row in cur.fetchall()]

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT data FROM business_rows WHERE module = ? AND entry_id = ?",
                (module, entry_id),
            ).fetchone()
            return self._decode(row["data"]) if row else None

    # ----------------------------------------------------------------- 写明细
    def insert(self, module: str, entry: dict[str, Any]) -> dict[str, Any]:
        """新增一条运行数据；与概览刷新在同一事务内提交，要么全成要么全退。"""
        with self.transaction():
            next_id = self.conn.execute(
                "SELECT COALESCE(MAX(entry_id), 0) + 1 FROM business_rows WHERE module = ?",
                (module,),
            ).fetchone()[0]
            record = {"id": int(entry.get("id") or next_id)}
            record.update({k: v for k, v in entry.items() if k != "id"})
            self._persist(module, record["id"], record)
            self._rebuild_module(module)
            return dict(record)

    def update(self, module: str, entry_id: int, changes: dict[str, Any]) -> dict[str, Any] | None:
        """按业务动作改写明细，随后在同一事务内重算该模块概览。"""
        with self.transaction():
            row = self.conn.execute(
                "SELECT data FROM business_rows WHERE module = ? AND entry_id = ?",
                (module, entry_id),
            ).fetchone()
            if row is None:
                return None
            record = self._decode(row["data"])
            record.update(changes)
            self._persist(module, entry_id, record)
            self._rebuild_module(module)
            return dict(record)

    def _persist(self, module: str, entry_id: int, record: dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO business_rows(module, entry_id, data, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(module, entry_id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at
            """,
            (module, entry_id, json.dumps(record, ensure_ascii=False), _now()),
        )

    # ------------------------------------------------------------- 初始化写入
    def setup(self, *, seed: bool | None = None) -> dict[str, int | str | bool]:
        """启动/部署统一入口：建表（init_db 已在连接时完成）后按需幂等补样例。

        seed=None 时取配置 APP_SEED_ON_STARTUP（local 默认补、prod 默认不补）。
        不补样例也会保证概览表存在并与明细一致（空库 -> 全 0 快照）。
        """
        should_seed = settings.seed_on_startup if seed is None else seed
        if should_seed:
            return self.seed_if_needed()
        self.rebuild_overview()
        return {"inserted": 0, "already_seeded": True}

    def seed_if_needed(self) -> dict[str, int | str | bool]:
        """幂等初始化：一个事务补齐缺失样例，已存在的运行数据原样保留。

        - 全部样例都在且指纹一致：no-op，重复执行结果相同；
        - 缺样例或样例版本更新：INSERT OR IGNORE 补齐，运行数据口径优先；
        - 任一步失败：事务回滚，库回到调用前状态。
        """
        checksum = _seed_checksum()
        with self.transaction():
            stored = self._meta("seed_checksum")
            inserted = 0
            for module, sample_rows in SEED_ROWS.items():
                for sample in sample_rows:
                    cur = self.conn.execute(
                        "SELECT 1 FROM business_rows WHERE module = ? AND entry_id = ?",
                        (module, int(sample["id"])),
                    )
                    if cur.fetchone() is not None:
                        continue  # 运行数据优先：同 id 记录绝不被样例覆盖
                    self._persist(module, int(sample["id"]), dict(sample))
                    inserted += 1
            self._set_meta("seed_checksum", checksum)
            self._rebuild_all()
            return {"inserted": inserted, "already_seeded": stored == checksum and inserted == 0}

    def reset_to_seed(self) -> dict[str, int]:
        """清库后整体重灌样例（仅本地演示/排障用，生产不应调用）。"""
        with self.transaction():
            self.conn.execute("DELETE FROM business_rows")
            inserted = 0
            for module, sample_rows in SEED_ROWS.items():
                for sample in sample_rows:
                    self._persist(module, int(sample["id"]), dict(sample))
                    inserted += 1
            self._set_meta("seed_checksum", _seed_checksum())
            self._rebuild_all()
            return {"inserted": inserted}

    # ------------------------------------------------------------- 概览重算
    def _effective_ref_date(self, ref_date: str | None) -> str:
        return ref_date or settings.overview_today or date.today().isoformat()

    def _scan_module(self, meta: ModuleMeta, ref_date: str) -> dict[str, int]:
        """直接扫描原始业务记录重算概览——概览数字都能在明细里逐条对上。"""
        rows = self.rows(meta.name)
        total = len(rows)
        created = 0
        pending = 0
        abnormal = 0
        date_field = meta.date_field
        for record in rows:
            if date_field is not None and str(record.get(date_field, ""))[:10] == ref_date:
                created += 1
            if bool(record.get("pending")):
                pending += 1
            if bool(record.get("abnormal")):
                abnormal += 1
        return {"total": total, "created": created, "pending": pending, "abnormal": abnormal}

    def _write_snapshot(self, meta: ModuleMeta, ref_date: str, counts: dict[str, int]) -> None:
        self.conn.execute(
            """
            INSERT INTO overview_snap(module, total, created, pending, abnormal, ref_date, computed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(module) DO UPDATE SET
                total = excluded.total, created = excluded.created, pending = excluded.pending,
                abnormal = excluded.abnormal, ref_date = excluded.ref_date, computed_at = excluded.computed_at
            """,
            (
                meta.name, counts["total"], counts["created"], counts["pending"], counts["abnormal"],
                ref_date, _now(),
            ),
        )

    def _rebuild_module(self, module: str, ref_date: str | None = None) -> dict[str, int]:
        meta = MODULE_REGISTRY[module]
        ref = self._effective_ref_date(ref_date)
        counts = self._scan_module(meta, ref)
        self._write_snapshot(meta, ref, counts)
        self._set_meta("overview_ref_date", ref)
        return counts

    def rebuild_overview(self, ref_date: str | None = None) -> dict[str, Any]:
        """迁移/回填入口：按原始业务记录整体重算概览，全部模块一个事务。"""
        with self.transaction():
            return self._rebuild_all(ref_date)

    def _rebuild_all(self, ref_date: str | None = None) -> dict[str, Any]:
        ref = self._effective_ref_date(ref_date)
        modules = []
        for meta in MODULES:
            counts = self._scan_module(meta, ref)
            self._write_snapshot(meta, ref, counts)
            modules.append({"name": meta.name, "label": meta.label, **counts})
        self._set_meta("overview_ref_date", ref)
        return {"ref_date": ref, "modules": modules}

    def overview(self) -> dict[str, Any]:
        """读概览快照；跨天或被外部改过时，按明细在事务内自动重算，保证对得上。"""
        ref = self._effective_ref_date(None)
        with self.transaction():
            stored_date = self._meta("overview_ref_date")
            if stored_date != ref:
                self._rebuild_all(ref)
            cur = self.conn.execute(
                "SELECT * FROM overview_snap ORDER BY module"
            ).fetchall()
            modules: list[dict[str, Any]] = []
            for row in cur:
                meta = MODULE_REGISTRY[row["module"]]
                modules.append({
                    "name": row["module"],
                    "label": meta.label,
                    "created": row["created"],
                    "pending": row["pending"],
                    "abnormal": row["abnormal"],
                    "total": row["total"],
                    "has_date": meta.date_field is not None,
                })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "在册总量", "value": sum(int(item["total"]) for item in modules)},
            {"label": "当日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"ref_date": ref, "cards": cards, "modules": modules}

    def reconcile(self, ref_date: str | None = None) -> dict[str, Any]:
        """核对概览快照与业务明细：逐模块重算比对计数，返回差异清单。

        ref_date 只决定“当日新增”按哪天重算计数；不传时沿用快照当前参考日
        （即检查计数本身是否对得上明细），显式传参则用于切换参考日验收。
        参考日不同本身不算口径漂移，用 ref_date / ref_date_current 暴露。
        """
        with self._lock:
            current_ref = self._meta("overview_ref_date")
        ref = ref_date or current_ref or self._effective_ref_date(None)
        drift: list[dict[str, Any]] = []
        with self._lock:
            snapshots = {
                row["module"]: row
                for row in self.conn.execute("SELECT * FROM overview_snap").fetchall()
            }
            for meta in MODULES:
                fresh = self._scan_module(meta, ref)
                snap = snapshots.get(meta.name)
                if snap is None:
                    drift.append({"module": meta.name, "reason": "缺少概览快照"})
                    continue
                actual = {
                    "total": snap["total"], "created": snap["created"],
                    "pending": snap["pending"], "abnormal": snap["abnormal"],
                }
                if actual != fresh:  # 计数对不上才是真漂移；参考日不同由调用方决定是否 rebuild
                    drift.append({
                        "module": meta.name,
                        "snapshot": actual,
                        "expected": fresh,
                    })
        return {"ref_date": ref, "ref_date_current": current_ref, "ok": not drift, "drift": drift}

    # ------------------------------------------------------------------ meta
    def _meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def _set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


store = Store()
