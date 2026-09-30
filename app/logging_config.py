"""Consistent UTC console logging without exception payloads or terminal controls."""

from __future__ import annotations

import copy
import json
import logging
import logging.config
import re
import time
import traceback
from pathlib import Path
from types import TracebackType


class ConsoleFormatter(logging.Formatter):
    converter = time.gmtime

    def format(self, record: logging.LogRecord) -> str:
        safe_record = copy.copy(record)
        safe_record.msg = re.sub(
            r"[\x00-\x1f\x7f]", lambda match: repr(match.group())[1:-1], record.getMessage()
        )
        safe_record.args = ()
        safe_record.exc_text = None
        return super().format(safe_record)

    def formatException(self, exc_info: tuple[type[BaseException], BaseException, TracebackType | None]) -> str:
        # Exception values can contain submitted passwords, URLs, or SQL parameters.
        frames = traceback.extract_tb(exc_info[2])
        lines = ["Traceback (most recent call last):"]
        lines.extend(f"  {Path(frame.filename).name}:{frame.lineno} in {frame.name}" for frame in frames)
        lines.append(f"Error type: {exc_info[0].__name__}")
        return "\n".join(lines)


def configure_logging() -> None:
    config_path = Path(__file__).with_name("logging.json")
    logging.config.dictConfig(json.loads(config_path.read_text(encoding="utf-8")))
