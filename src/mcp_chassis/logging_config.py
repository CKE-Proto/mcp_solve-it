"""Logging configuration for the MCP Chassis server.

All log output goes to stderr; stdout is reserved for MCP JSON-RPC messages.
Uses a custom JSONFormatter for structured, machine-parseable output.
"""

import json
import logging
import sys
import time


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects.

    Output fields: timestamp (ISO 8601), level, logger, message,
    and any extras including correlation_id.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON string.

        Args:
            record: The log record to format.

        Returns:
            A single-line JSON string.
        """
        log_obj: dict[str, object] = {
            "timestamp": self._format_time(record),
            "level": record.levelname,
            "logger": record.name,
            "message": self._safe_message(record),
        }

        # Include correlation_id if present
        if hasattr(record, "correlation_id"):
            log_obj["correlation_id"] = record.correlation_id

        # Include exc_info if present
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj, ensure_ascii=False)

    def _format_time(self, record: logging.LogRecord) -> str:
        """Return ISO 8601 timestamp string.

        Args:
            record: The log record with created timestamp.

        Returns:
            ISO 8601 formatted timestamp.
        """
        ct = time.gmtime(record.created)
        return time.strftime("%Y-%m-%dT%H:%M:%S", ct) + f".{int(record.msecs):03d}Z"

    def _safe_message(self, record: logging.LogRecord) -> str:
        """Return the formatted message, stripping ASCII control characters.

        Args:
            record: The log record.

        Returns:
            Message string safe for JSON embedding.
        """
        msg = record.getMessage()
        # Strip ASCII control characters (including newlines) to ensure
        # single-line JSON output and prevent log injection.
        return "".join(
            ch for ch in msg if ch == "\t" or ord(ch) >= 32
        )


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger for structured JSON output to stderr.

    Replaces any existing handlers on the root logger. All subsequent
    logging calls will emit single-line JSON to stderr. stdout is never
    written to by this configuration.

    Args:
        level: Log level name (DEBUG, INFO, WARNING, ERROR, CRITICAL).
            Case-insensitive.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JSONFormatter())
    handler.setLevel(numeric_level)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(numeric_level)
