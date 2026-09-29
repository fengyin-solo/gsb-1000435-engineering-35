"""命令行运维入口：迁移、播种、概览回填、对账、重置。

用法（在 backend/ 目录下）：

    .venv/bin/python -m app.cli migrate             # 建表 / 升级结构（幂等）
    .venv/bin/python -m app.cli seed                # 事务内补写样例（不覆盖运行数据，幂等）
    .venv/bin/python -m app.cli recompute-overview  # 按原始业务记录重算概览快照
    .venv/bin/python -m app.cli reconcile           # 概览 vs 明细对账，不一致退出码 1
    .venv/bin/python -m app.cli init                # migrate + seed + recompute（启动同款流程）
    .venv/bin/python -m app.cli reset [--seed]      # 清空全部运行数据（危险，需确认）

环境变量 DATABASE_URL 可指定库文件；测试可用 :memory:（仅在同进程内有效）。
"""
from __future__ import annotations

import argparse
import sys

from app import db
from app.seed import seed_database, seed_transaction
from app.services import overview


def _cmd_migrate(_: argparse.Namespace) -> int:
    applied = db.run_migrations()
    if applied:
        print(f"已执行迁移版本：{', '.join(str(v) for v in applied)}")
    else:
        print("迁移已是最新，无需执行")
    return 0


def _cmd_seed(_: argparse.Namespace) -> int:
    result = seed_database()
    print(f"样例写入完成：新增 {result['inserted']} 条，跳过已存在 {result['skipped']} 条")
    print("口径：只补缺失，运行数据优先，重复执行幂等")
    return 0


def _cmd_recompute(_: argparse.Namespace) -> int:
    db.run_migrations()
    with db.session() as conn:
        written = overview.recompute_snapshots(conn)
    print(f"已按原始业务记录重算概览快照，覆盖 {written} 个模块")
    return 0


def _cmd_reconcile(_: argparse.Namespace) -> int:
    db.run_migrations()
    with db.session() as conn:
        result = overview.reconcile(conn)
    if result["ok"]:
        print("对账通过：概览快照与业务明细完全一致")
        return 0
    print("对账发现差异：", file=sys.stderr)
    for diff in result["diffs"]:
        print(f"  - [{diff['label']}] {diff['reason']}："
              f"快照={diff['snapshot']} 明细={diff['detail']}", file=sys.stderr)
    print("可执行 python -m app.cli recompute-overview 回填修复", file=sys.stderr)
    return 1


def _cmd_init(_: argparse.Namespace) -> int:
    applied = db.run_migrations()
    with db.session() as conn:
        result = seed_transaction(conn)
        written = overview.recompute_snapshots(conn)
    print(f"初始化完成：迁移 {len(applied)} 个版本，"
          f"样例新增 {result['inserted']} / 跳过 {result['skipped']}，"
          f"概览回填 {written} 个模块")
    return 0


def _cmd_reset(args: argparse.Namespace) -> int:
    if not args.yes:
        print("这会清空所有运行数据，且不可恢复。确认请加 --yes", file=sys.stderr)
        return 2
    db.run_migrations()
    with db.session() as conn:
        deleted = conn.execute("DELETE FROM records").rowcount
        conn.execute("DELETE FROM overview_snapshots")
        conn.execute("DELETE FROM seed_meta")
        inserted = 0
        if args.seed:
            inserted = seed_transaction(conn)["inserted"]
        # 播种之后再按原始记录重算，保证重置完快照与明细立即一致。
        overview.recompute_snapshots(conn)
    print(f"已清空运行数据 {deleted} 条")
    if args.seed:
        print(f"已重新补写样例：新增 {inserted} 条")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="app.cli", description="冷链平台后端运维命令")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("migrate", help="执行数据库迁移（幂等）").set_defaults(func=_cmd_migrate)
    sub.add_parser("seed", help="事务内补写样例数据（不覆盖运行数据）").set_defaults(func=_cmd_seed)
    sub.add_parser("recompute-overview", help="按原始业务记录重算概览快照").set_defaults(func=_cmd_recompute)
    sub.add_parser("reconcile", help="概览与明细对账").set_defaults(func=_cmd_reconcile)
    sub.add_parser("init", help="迁移 + 播种 + 概览回填").set_defaults(func=_cmd_init)

    reset = sub.add_parser("reset", help="清空全部运行数据")
    reset.add_argument("--yes", action="store_true", help="确认执行（必须显式提供）")
    reset.add_argument("--seed", action="store_true", help="清空后重新补写样例")
    reset.set_defaults(func=_cmd_reset)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
