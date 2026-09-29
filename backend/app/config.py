"""运行配置：全部来自环境变量，本地/容器/部署走同一套读取口径。

读取优先级：进程环境变量 > .env 文件 > 代码默认值。
配置只读一次（进程启动时），运行期不被样例数据或业务写操作改变。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # python-dotenv 在 requirements 里（uvicorn[standard] 传递依赖），缺失时退回纯环境变量
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - 兜底分支
    def load_dotenv(*_args: object, **_kwargs: object) -> bool:
        return False


BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = field(default_factory=lambda: os.environ.get("APP_NAME", "冷链物流温控管理平台"))
    env: str = field(default_factory=lambda: os.environ.get("APP_ENV", "local"))
    host: str = field(default_factory=lambda: os.environ.get("APP_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.environ.get("APP_PORT", "8000")))
    allowed_origins: list[str] = field(
        default_factory=lambda: [
            item.strip()
            for item in os.environ.get(
                "APP_CORS_ORIGINS",
                "http://127.0.0.1:5173,http://localhost:5173",
            ).split(",")
            if item.strip()
        ]
    )
    page_size_default: int = 20
    page_size_max: int = field(
        default_factory=lambda: int(os.environ.get("APP_PAGE_SIZE_MAX", "200"))
    )
    # 样例数据口径：local（本地开发）自动写入并幂等；prod 默认不写
    seed_on_startup: bool = field(
        default_factory=lambda: _env_bool("APP_SEED_ON_STARTUP", os.environ.get("APP_ENV", "local") != "prod")
    )
    # SQLite 落库文件；:memory: 为进程内内存库（测试用）
    database_url: str = field(
        default_factory=lambda: os.environ.get("APP_DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'data' / 'app.db'}")
    )
    # 概览口径：created 只统计发生在该自然日的业务记录，而不是全表行数
    overview_today: str = field(
        default_factory=lambda: os.environ.get("APP_OVERVIEW_TODAY", "")
    )


settings = Settings()
