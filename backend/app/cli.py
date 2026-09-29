"""命令行运维入口：本地开发、容器初始化、部署后回填都走这一条命令。

用法：
    python -m app.cli init               建表 + 按环境口径初始化（失败整体回滚，可重复执行）
    python -m app.cli init --seed        强制幂等写入样例（忽略 APP_ENV）
    python -m app.cli init --no-seed     只建表刷概览，不写样例
    python -m app.cli rebuild            按原始业务记录整体重算运营概览（迁移/回填口径）
    python -m app.cli reconcile          核对概览快照与业务明细是否一致（只读）
    python -m app.cli reset              清库重灌样例（仅本地演示，prod 环境拒绝执行）
"""
from __future__ import annotations

import json
import sys

from app.config import settings
from app.store import store


def _emit(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def init_cmd() -> int:
    # 尊重 APP_SEED_ON_STARTUP / APP_ENV 口径；也可用 --seed / --no-seed 显式覆盖
    force_seed: bool | None = None
    if "--seed" in sys.argv[1:]:
        force_seed = True
    if "--no-seed" in sys.argv[1:]:
        force_seed = False
    result = store.setup(seed=force_seed)
    check = store.reconcile()
    _emit({"env": settings.env, "database": settings.database_url, "seed": result, "reconcile": check})
    if not check["ok"]:
        print("初始化完成但概览核对发现差异，请执行 rebuild", file=sys.stderr)
        return 1
    return 0


def rebuild_cmd() -> int:
    result = store.rebuild_overview()
    check = store.reconcile(result["ref_date"])
    _emit({"rebuilt_modules": len(result["modules"]), "ref_date": result["ref_date"], "reconcile": check})
    return 0 if check["ok"] else 1


def reconcile_cmd() -> int:
    check = store.reconcile()
    _emit(check)
    return 0 if check["ok"] else 2


def reset_cmd() -> int:
    if settings.env == "prod":
        print("拒绝在 prod 环境执行 reset：会清掉全部运行数据", file=sys.stderr)
        return 3
    result = store.reset_to_seed()
    check = store.reconcile()
    _emit({"reset": result, "reconcile": check})
    return 0 if check["ok"] else 1


COMMANDS = {
    "init": init_cmd,
    "rebuild": rebuild_cmd,
    "reconcile": reconcile_cmd,
    "reset": reset_cmd,
}


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args or args[0] not in COMMANDS:
        print(__doc__)
        return 64
    try:
        return COMMANDS[args[0]]()
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
