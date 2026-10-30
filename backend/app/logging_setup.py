"""统一应用日志：可读业务日志，默认不刷 SQL DEBUG。"""

from __future__ import annotations

import logging
import re
import sys

_configured = False


def redact_log_text(value: str) -> str:
    """Remove capability URLs, credentials and mailboxes, including exception text."""
    value = re.sub(r"(?i)\b(?:redis|rediss|postgres|postgresql)(?:\+[a-z0-9]+)?://[^\s<>\"']+", "[dsn-redacted]", value)
    value = re.sub(r"https?://[^\s<>\"']+", "[url-redacted]", value, flags=re.I)
    value = re.sub(r"(?:/[^\s?<>\"']*)?\?[^\s<>\"']+", "[query-redacted]", value)
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email-redacted]", value)
    value = re.sub(r"(?i)(authorization[=: ]+)(?:bearer\s+)?[^\s,;]+", r"\1[redacted]", value)
    return value


class RedactingFormatter(logging.Formatter):
    """Redact after rendering so exception traceback messages are covered too."""

    def __init__(self, delegate: logging.Formatter):
        super().__init__()
        self.delegate = delegate

    def format(self, record: logging.LogRecord) -> str:
        return redact_log_text(self.delegate.format(record))


def configure_logging(*, level: str = "INFO", sql_echo: bool = False) -> None:
    # 配置根日志；可重复调用以刷新级别（reload 后仍可生效）
    global _configured

    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        root.addHandler(handler)

    # Uvicorn has non-propagating access/error handlers as well as root handlers.
    for target in (root, logging.getLogger("uvicorn"), logging.getLogger("uvicorn.access"),
                   logging.getLogger("uvicorn.error")):
        for handler in target.handlers:
            if not isinstance(handler.formatter, RedactingFormatter):
                handler.setFormatter(RedactingFormatter(handler.formatter or logging.Formatter()))

    # 根级别用 INFO：DEBUG=true 也不刷第三方库
    root.setLevel(logging.INFO)
    logging.getLogger("app").setLevel(getattr(logging, level.upper(), logging.INFO))

    # SQLAlchemy 驱动默认关闭
    for name in (
        "sqlalchemy",
        "sqlalchemy.engine",
        "sqlalchemy.pool",
        "sqlalchemy.dialects",
        "asyncpg",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)

    if sql_echo:
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
    else:
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    # 其他噪音
    for name in ("uvicorn.access", "httpx", "httpcore", "asyncio", "multipart"):
        logging.getLogger(name).setLevel(
            logging.INFO if name == "uvicorn.access" else logging.WARNING
        )

    if not _configured:
        logging.getLogger("app").info(
            "日志已配置 app_level=%s sql_echo=%s（已关闭 SQL DEBUG）",
            level,
            sql_echo,
        )
    _configured = True
