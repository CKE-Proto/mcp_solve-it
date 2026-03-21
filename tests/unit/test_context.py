"""Unit tests for mcp_chassis.context — async logging and MCP notifications."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_chassis.config import (
    AuthConfig,
    DiagnosticSettings,
    ExtensionSettings,
    IOLimitConfig,
    RateLimitConfig,
    SanitizationConfig,
    SecurityConfig,
    ServerConfig,
    ServerSettings,
    ValidationConfig,
)
from mcp_chassis.context import HandlerContext


def _make_config() -> ServerConfig:
    """Build a minimal ServerConfig for context tests."""
    return ServerConfig(
        server=ServerSettings(name="test-server", version="0.1.0"),
        security=SecurityConfig(
            rate_limits=RateLimitConfig(enabled=False),
            io_limits=IOLimitConfig(),
            input_validation=ValidationConfig(enabled=False),
            input_sanitization=SanitizationConfig(enabled=False, level="permissive"),
            auth=AuthConfig(enabled=False, provider="none"),
        ),
        extensions=ExtensionSettings(auto_discover=False),
        diagnostics=DiagnosticSettings(health_check_enabled=False),
    )


def _make_context(*, session: Any = None) -> HandlerContext:
    """Build a HandlerContext, optionally with a mock session."""
    return HandlerContext(
        request_id="test-req-1",
        correlation_id="test-corr-1",
        server_config=_make_config(),
        _session=session,
    )


class TestAsyncLogMethods:
    """Verify log_* methods are async (awaitable)."""

    @pytest.mark.asyncio
    async def test_log_debug_is_awaitable(self) -> None:
        ctx = _make_context()
        await ctx.log_debug("debug message")

    @pytest.mark.asyncio
    async def test_log_info_is_awaitable(self) -> None:
        ctx = _make_context()
        await ctx.log_info("info message")

    @pytest.mark.asyncio
    async def test_log_warning_is_awaitable(self) -> None:
        ctx = _make_context()
        await ctx.log_warning("warning message")

    @pytest.mark.asyncio
    async def test_log_error_is_awaitable(self) -> None:
        ctx = _make_context()
        await ctx.log_error("error message")


class TestStderrLogging:
    """Verify log_* methods still write to stderr via the logging module."""

    @pytest.mark.asyncio
    async def test_log_info_writes_to_stderr_logger(self, caplog: Any) -> None:
        import logging

        ctx = _make_context()
        with caplog.at_level(logging.DEBUG, logger="mcp_chassis.handler"):
            await ctx.log_info("hello from handler")
        assert "hello from handler" in caplog.text

    @pytest.mark.asyncio
    async def test_log_debug_writes_to_stderr_logger(self, caplog: Any) -> None:
        import logging

        ctx = _make_context()
        with caplog.at_level(logging.DEBUG, logger="mcp_chassis.handler"):
            await ctx.log_debug("debug detail")
        assert "debug detail" in caplog.text

    @pytest.mark.asyncio
    async def test_log_warning_writes_to_stderr_logger(self, caplog: Any) -> None:
        import logging

        ctx = _make_context()
        with caplog.at_level(logging.WARNING, logger="mcp_chassis.handler"):
            await ctx.log_warning("something fishy")
        assert "something fishy" in caplog.text

    @pytest.mark.asyncio
    async def test_log_error_writes_to_stderr_logger(self, caplog: Any) -> None:
        import logging

        ctx = _make_context()
        with caplog.at_level(logging.ERROR, logger="mcp_chassis.handler"):
            await ctx.log_error("something broke")
        assert "something broke" in caplog.text

    @pytest.mark.asyncio
    async def test_log_info_formats_args(self, caplog: Any) -> None:
        import logging

        ctx = _make_context()
        with caplog.at_level(logging.INFO, logger="mcp_chassis.handler"):
            await ctx.log_info("item %s has %d hits", "abc", 5)
        assert "item abc has 5 hits" in caplog.text

    @pytest.mark.asyncio
    async def test_log_without_args_still_works(self, caplog: Any) -> None:
        import logging

        ctx = _make_context()
        with caplog.at_level(logging.INFO, logger="mcp_chassis.handler"):
            await ctx.log_info("plain message no args")
        assert "plain message no args" in caplog.text

    @pytest.mark.asyncio
    async def test_stderr_logging_works_without_session(self, caplog: Any) -> None:
        import logging

        ctx = _make_context(session=None)
        with caplog.at_level(logging.INFO, logger="mcp_chassis.handler"):
            await ctx.log_info("no session here")
        assert "no session here" in caplog.text


class TestMcpNotifications:
    """Verify log_* methods send MCP notifications when _session is present."""

    @pytest.mark.asyncio
    async def test_send_log_message_called_on_info(self) -> None:
        mock_session = MagicMock()
        mock_session.send_log_message = AsyncMock()

        ctx = _make_context(session=mock_session)
        await ctx.log_info("notify the client")

        mock_session.send_log_message.assert_awaited_once_with(
            level="info",
            data="notify the client",
            logger="mcp_chassis.handler",
        )

    @pytest.mark.asyncio
    async def test_send_log_message_called_on_debug(self) -> None:
        mock_session = MagicMock()
        mock_session.send_log_message = AsyncMock()

        ctx = _make_context(session=mock_session)
        await ctx.log_debug("debug notify")

        mock_session.send_log_message.assert_awaited_once_with(
            level="debug",
            data="debug notify",
            logger="mcp_chassis.handler",
        )

    @pytest.mark.asyncio
    async def test_send_log_message_called_on_warning(self) -> None:
        mock_session = MagicMock()
        mock_session.send_log_message = AsyncMock()

        ctx = _make_context(session=mock_session)
        await ctx.log_warning("warn notify")

        mock_session.send_log_message.assert_awaited_once_with(
            level="warning",
            data="warn notify",
            logger="mcp_chassis.handler",
        )

    @pytest.mark.asyncio
    async def test_send_log_message_called_on_error(self) -> None:
        mock_session = MagicMock()
        mock_session.send_log_message = AsyncMock()

        ctx = _make_context(session=mock_session)
        await ctx.log_error("error notify")

        mock_session.send_log_message.assert_awaited_once_with(
            level="error",
            data="error notify",
            logger="mcp_chassis.handler",
        )

    @pytest.mark.asyncio
    async def test_send_log_message_formats_args(self) -> None:
        mock_session = MagicMock()
        mock_session.send_log_message = AsyncMock()

        ctx = _make_context(session=mock_session)
        await ctx.log_info("hello %s, count=%d", "world", 42)

        mock_session.send_log_message.assert_awaited_once_with(
            level="info",
            data="hello world, count=42",
            logger="mcp_chassis.handler",
        )

    @pytest.mark.asyncio
    async def test_no_notification_when_session_is_none(self) -> None:
        ctx = _make_context(session=None)
        # Should not raise — just logs to stderr
        await ctx.log_info("no crash please")

    @pytest.mark.asyncio
    async def test_failed_notification_does_not_crash(self) -> None:
        mock_session = MagicMock()
        mock_session.send_log_message = AsyncMock(
            side_effect=RuntimeError("transport broken")
        )

        ctx = _make_context(session=mock_session)
        # Must not raise even though send_log_message fails
        await ctx.log_info("this should still work")
