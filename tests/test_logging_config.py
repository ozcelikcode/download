"""Console diagnostics preserve error locations without submitted secret values."""

import logging
import subprocess
import sys

from app.logging_config import ConsoleFormatter


def test_console_exception_hides_payload_and_preserves_error_location():
    try:
        raise ValueError("private-password https://example.com/?token=private-token")
    except ValueError:
        record = logging.LogRecord("app.test", logging.ERROR, __file__, 1, "Request failed", (), sys.exc_info())
    result = ConsoleFormatter("%(levelname)s | %(message)s").format(record)
    assert "private-password" not in result
    assert "private-token" not in result
    assert "ValueError" in result
    assert "test_logging_config.py:" in result


def test_console_message_cannot_inject_terminal_controls_or_extra_lines():
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "Content\nforged log\x1b[31m", (), None)
    result = ConsoleFormatter("%(message)s").format(record)
    assert "\n" not in result
    assert "\x1b" not in result


def test_watcher_noise_is_hidden_but_real_diagnostics_remain_visible():
    result = subprocess.run(
        [sys.executable, "-c", "\n".join([
            "import logging",
            "from app.logging_config import configure_logging",
            "configure_logging()",
            "logging.getLogger('watchfiles.main').info('4 changes detected')",
            "logging.getLogger('watchfiles.main').warning('Watcher warning')",
            "logging.getLogger('uvicorn.error').warning('Reloading application')",
            "logging.getLogger('app.main').info('Application started')",
        ])],
        capture_output=True, text=True, check=True,
    )
    assert "changes detected" not in result.stderr
    assert "Watcher warning" in result.stderr
    assert "Reloading application" in result.stderr
    assert "Application started" in result.stderr
