"""SQLite 輕量欄位補齊（無 Alembic 時）。"""

import logging

from sqlalchemy import inspect, text

from app.database import engine

log = logging.getLogger(__name__)


def ensure_sqlite_columns() -> None:
    if "sqlite" not in str(engine.url).lower():
        return
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("queue_info")}
    if "uses_dynamic_travel" not in cols:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "ALTER TABLE queue_info ADD COLUMN uses_dynamic_travel "
                    "INTEGER NOT NULL DEFAULT 1"
                )
            )
            conn.commit()
        log.info("DB: 已新增 queue_info.uses_dynamic_travel")
