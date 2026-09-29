"""运行配置：端口、跨域、运行环境与数据口径开关。

所有可调项都从环境变量读取、按需求值（不缓存），带本地默认值，
保证克隆下来不改代码也能起，也让测试可以按用例切换 DATABASE_URL。
环境变量优先级高于代码默认值：命令行 / 容器注入 > 代码默认值。
"""
from __future__ import annotations

import os
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


class Settings:
    app_name_default = "冷链物流温控管理平台"
    allowed_origins_default = ["http://127.0.0.1:5173", "http://localhost:5173"]
    page_size_default = 20
    page_size_max = 200

    # 样例数据与运行数据的口径标识：
    #   sample  = 样例数据（SEED_ROWS，只补缺失，绝不覆盖运行中产生/改过的记录）
    #   runtime = 运行数据（records 表里由接口写入与流转产生的记录）
    # 读取概览/明细时只认 records 表（runtime 口径），样例仅在首次初始化时落库。
    data_source_seed = "sample"
    data_source_runtime = "runtime"

    @property
    def app_name(self) -> str:
        return os.getenv("APP_NAME", self.app_name_default)

    @property
    def env(self) -> str:
        return os.getenv("APP_ENV", "local")

    @property
    def port(self) -> int:
        return int(os.getenv("APP_PORT", "8000"))

    @property
    def allowed_origins(self) -> list[str]:
        return _env_list("APP_ALLOWED_ORIGINS", self.allowed_origins_default)

    @property
    def database_url(self) -> str:
        return os.getenv("DATABASE_URL", "")

    @property
    def migrate_on_start(self) -> bool:
        return _env_bool("MIGRATE_ON_START", True)

    @property
    def seed_on_start(self) -> bool:
        return _env_bool("SEED_ON_START", True)

    @property
    def db_path(self) -> str:
        return self.database_url or str(_BACKEND_DIR / "data" / "app.db")


settings = Settings()
