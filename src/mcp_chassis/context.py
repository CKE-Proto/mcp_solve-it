"""Handler context provided to extension tool/resource/prompt handlers.

Abstracts away MCP SDK internals so extension code does not import from mcp.*
directly. This allows SDK version migration without touching extension code.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server.session import ServerSession

    from mcp_chassis.config import ServerConfig

_LOGGER_NAME = "mcp_chassis.handler"


@dataclass
class HandlerContext:
    """Context object passed to all extension handlers.

    Provides request identification, logging helpers, and access to server
    configuration without exposing SDK internals.

    Attributes:
        request_id: Unique ID for the current MCP request.
        correlation_id: Correlation ID for cross-log tracing.
        server_config: The running server's configuration.
        lifespan_state: User-defined state from lifespan hooks.
    """

    request_id: str
    correlation_id: str
    server_config: ServerConfig
    lifespan_state: Any = field(default=None)
    _session: ServerSession | None = field(default=None, repr=False)

    async def log_debug(self, message: str, *args: object) -> None:
        """Emit a DEBUG log message with correlation context.

        Args:
            message: The message (or format string) to log.
            *args: Optional format arguments (%-style), e.g.
                ``await context.log_debug("loaded %d items", count)``.
        """
        await self._log("debug", logging.DEBUG, message, *args)

    async def log_info(self, message: str, *args: object) -> None:
        """Emit an INFO log message with correlation context.

        Args:
            message: The message (or format string) to log.
            *args: Optional format arguments (%-style), e.g.
                ``await context.log_info("processing %s", name)``.
        """
        await self._log("info", logging.INFO, message, *args)

    async def log_warning(self, message: str, *args: object) -> None:
        """Emit a WARNING log message with correlation context.

        Args:
            message: The message (or format string) to log.
            *args: Optional format arguments (%-style), e.g.
                ``await context.log_warning("retry %d of %d", attempt, max_retries)``.
        """
        await self._log("warning", logging.WARNING, message, *args)

    async def log_error(self, message: str, *args: object) -> None:
        """Emit an ERROR log message with correlation context.

        Args:
            message: The message (or format string) to log.
            *args: Optional format arguments (%-style), e.g.
                ``await context.log_error("failed to process %s: %s", name, err)``.
        """
        await self._log("error", logging.ERROR, message, *args)

    async def report_progress(
        self, progress: float, total: float, message: str = ""
    ) -> None:
        """Log a progress update (stub — full MCP progress in future).

        Args:
            progress: Current progress value.
            total: Total expected value.
            message: Optional descriptive message.
        """
        _log = logging.getLogger(_LOGGER_NAME)
        pct = (progress / total * 100) if total > 0 else 0.0
        _log.debug(
            "Progress: %.1f%% %s",
            pct,
            message,
            extra={"correlation_id": self.correlation_id},
        )

    async def _log(
        self, mcp_level: str, py_level: int, message: str, *args: object
    ) -> None:
        """Write to stderr logger and optionally send an MCP notification.

        Args:
            mcp_level: MCP log level string (debug, info, warning, error).
            py_level: Python logging level constant.
            message: The message (or format string) to log.
            *args: Optional %-style format arguments for *message*.
        """
        _log = logging.getLogger(_LOGGER_NAME)
        _log.log(py_level, message, *args, extra={"correlation_id": self.correlation_id})

        if self._session is not None:
            formatted = message % args if args else message
            try:
                await self._session.send_log_message(
                    level=mcp_level,
                    data=formatted,
                    logger=_LOGGER_NAME,
                )
            except Exception:
                _log.debug(
                    "Failed to send MCP log notification",
                    extra={"correlation_id": self.correlation_id},
                )
