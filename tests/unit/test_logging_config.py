"""Unit tests for mcp_chassis.logging_config module."""

import logging

from mcp_chassis.logging_config import JSONFormatter


class TestJSONFormatterSafeMessage:
    """Tests for _safe_message newline handling."""

    def test_newlines_stripped_from_message(self) -> None:
        """Newlines in log messages should be replaced to ensure single-line JSON."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="line1\nline2\nline3",
            args=(),
            exc_info=None,
        )
        safe = formatter._safe_message(record)
        assert "\n" not in safe

    def test_tabs_preserved_in_message(self) -> None:
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="col1\tcol2",
            args=(),
            exc_info=None,
        )
        safe = formatter._safe_message(record)
        assert "\t" in safe

    def test_control_chars_stripped(self) -> None:
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello\x01\x02world",
            args=(),
            exc_info=None,
        )
        safe = formatter._safe_message(record)
        assert "\x01" not in safe
        assert "\x02" not in safe
        assert "helloworld" == safe
