"""兼容层：历史代码按 ``from app.store import store`` 引用。

数据已经落到 SQLite（见 app/db.py），这里只保留只读的模块名查询，
不再持有任何进程内数据，避免出现「内存一份、库里一份」的双口径。
"""
from __future__ import annotations

from app import db
from app.modules import MODULE_NAMES


class _StoreCompat:
    def module_names(self) -> list[str]:
        return list(MODULE_NAMES)

    def overview(self) -> dict[str, object]:
        """实时聚合，保留给旧调用方；新代码请走 services.overview。"""
        from app.services import overview

        with db.session() as conn:
            return overview.compute_overview(conn)


store = _StoreCompat()
