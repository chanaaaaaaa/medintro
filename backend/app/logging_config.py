"""應用程式 logging：確保 `app.*` 的紀錄出現在終端機（stderr），與 uvicorn 的 HTTP 200 不同。

HTTP access log「200 OK」只代表請求結束；寄信細節在 logger `app.services.mail`。
若只接到 root／uvicorn 的 handler，`app.*` 的 INFO 可能被吃掉，故強制將 `app` 綁到 stderr。
"""

from __future__ import annotations

import logging
import sys

from app.config import settings

_MED_MARK = "_medintro_app_stderr_handler"


def configure_logging() -> None:
    level_name = settings.log_level.upper().strip()
    level = getattr(logging, level_name, logging.INFO)

    app_log = logging.getLogger("app")
    app_log.setLevel(level)

    if not any(getattr(h, _MED_MARK, False) for h in app_log.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(level)
        fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S"))
        setattr(handler, _MED_MARK, True)
        app_log.addHandler(handler)

    app_log.propagate = False

    root = logging.getLogger()
    if not root.handlers:
        h = logging.StreamHandler(sys.stderr)
        h.setLevel(level)
        h.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root.addHandler(h)
        root.setLevel(level)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
