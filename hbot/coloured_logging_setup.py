# SPDX-License-Identifier: Apache-2.0
#
# Copyright 2025 Firdaus Hakimi <hakimifirdaus944@gmail.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import json
import logging
import logging.config
import os
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from typing import Any


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


class _DropHttpxNoise(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not (record.name.startswith("httpx") and record.levelno <= logging.INFO)


class _ColorFormatter(logging.Formatter):
    _reset = "\x1b[0m"
    _colors = {
        logging.DEBUG: "\x1b[0;34m",
        logging.INFO: "\x1b[0;32m",
        logging.WARNING: "\x1b[33;20m",
        logging.ERROR: "\x1b[31;20m",
        logging.CRITICAL: "\x1b[31;1m",
    }

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        color = self._colors.get(record.levelno)
        if not color:
            return base
        return f"{color}{base}{self._reset}"


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    # Backwards-compat: existing env var
    debug = _env_bool("TGBOT_DEBUG")

    level = os.getenv("HBOT_LOG_LEVEL", "DEBUG" if debug else "INFO").upper()

    raw_log_file = os.getenv("HBOT_LOG_FILE")
    if raw_log_file is None:
        log_file: str | None = "bot.log"
    else:
        raw_log_file = raw_log_file.strip()
        if raw_log_file.lower() in {"", "0", "false", "off", "none"}:
            log_file = None
        else:
            log_file = raw_log_file

    max_bytes = _env_int("HBOT_LOG_MAX_BYTES", 5 * 1024 * 1024)
    backups = _env_int("HBOT_LOG_BACKUPS", 3)

    use_color = _env_bool("HBOT_LOG_COLOR", default=True) and os.getenv("NO_COLOR") is None

    root_handlers: list[str] = ["console"]
    handlers: dict[str, Any] = {
        "console": {
            "class": "logging.StreamHandler",
            "level": level,
            "formatter": "color" if use_color else "plain",
            "filters": ["drop_httpx"],
        }
    }

    if log_file:
        handlers["file"] = {
            "()": RotatingFileHandler,
            "filename": log_file,
            "maxBytes": max_bytes,
            "backupCount": backups,
            "encoding": "utf-8",
            "level": level,
            "formatter": "json",
            "filters": ["drop_httpx"],
        }
        root_handlers.append("file")

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {"drop_httpx": {"()": _DropHttpxNoise}},
            "formatters": {
                "plain": {"format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"},
                "color": {
                    "()": _ColorFormatter,
                    "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                },
                "json": {"()": _JsonFormatter},
            },
            "handlers": handlers,
            "root": {"level": level, "handlers": root_handlers},
            "loggers": {
                # Reduce ultra-noisy libs without hiding warnings/errors.
                "pyrogram": {"level": "INFO" if not debug else "DEBUG"},
                "asyncio": {"level": "WARNING"},
            },
        }
    )

    logging.getLogger(__name__).info("Logging initialized (level=%s, file=%s)", level, log_file or "disabled")


configure_logging()
