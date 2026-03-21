"""Unit tests for mcp_chassis.diagnostics.health module."""

import json

import pytest

from mcp_chassis.config import DiagnosticSettings, ExtensionSettings, ServerConfig, ServerSettings
from mcp_chassis.context import HandlerContext
from mcp_chassis.diagnostics.health import _HEALTH_TOOL_NAME, register_health_check
from mcp_chassis.server import ChassisServer


def _make_config(
    include_config_summary: bool = False,
    health_check_enabled: bool = True,
) -> ServerConfig:
    """Build a ServerConfig with specified diagnostic settings.

    Args:
        include_config_summary: Whether health check includes config summary.
        health_check_enabled: Whether health check is registered.

    Returns:
        ServerConfig instance.
    """
    return ServerConfig(
        server=ServerSettings(name="test-server", version="1.2.3"),
        diagnostics=DiagnosticSettings(
            health_check_enabled=health_check_enabled,
            include_config_summary=include_config_summary,
        ),
        extensions=ExtensionSettings(auto_discover=False),
    )


class TestRegisterHealthCheck:
    """Tests for register_health_check()."""

    def test_health_tool_is_registered(self) -> None:
        config = _make_config()
        server = ChassisServer(config)
        assert _HEALTH_TOOL_NAME in server.list_tool_names()

    def test_health_tool_not_registered_when_disabled(self) -> None:
        config = _make_config(health_check_enabled=False)
        server = ChassisServer(config)
        assert _HEALTH_TOOL_NAME not in server.list_tool_names()

    def test_only_one_health_tool_registered(self) -> None:
        """Calling register_health_check twice replaces (doesn't duplicate) the tool."""
        config = _make_config()
        server = ChassisServer(config)
        initial_count = server.list_tool_names().count(_HEALTH_TOOL_NAME)
        register_health_check(server)
        assert server.list_tool_names().count(_HEALTH_TOOL_NAME) == initial_count


class TestHealthCheckOutput:
    """Tests for the health check tool handler output."""

    def _make_context(self, config: ServerConfig) -> HandlerContext:
        return HandlerContext(
            request_id="req-001",
            correlation_id="corr-001",
            server_config=config,
        )

    @pytest.mark.asyncio
    async def test_health_check_returns_json(self) -> None:
        config = _make_config()
        server = ChassisServer(config)
        ctx = self._make_context(config)

        # Get the handler directly
        handler = server._tools[_HEALTH_TOOL_NAME]["handler"]
        result = await handler({}, ctx)

        # Must be valid JSON
        data = json.loads(result)
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_health_check_contains_server_name(self) -> None:
        config = _make_config()
        server = ChassisServer(config)
        ctx = self._make_context(config)
        handler = server._tools[_HEALTH_TOOL_NAME]["handler"]
        data = json.loads(await handler({}, ctx))
        assert data["server_name"] == "test-server"

    @pytest.mark.asyncio
    async def test_health_check_contains_version(self) -> None:
        config = _make_config()
        server = ChassisServer(config)
        ctx = self._make_context(config)
        handler = server._tools[_HEALTH_TOOL_NAME]["handler"]
        data = json.loads(await handler({}, ctx))
        assert data["server_version"] == "1.2.3"

    @pytest.mark.asyncio
    async def test_health_check_contains_tools_loaded(self) -> None:
        config = _make_config()
        server = ChassisServer(config)

        # Register an additional tool
        async def dummy_handler(args: dict, ctx: HandlerContext) -> str:
            return "ok"

        server.register_tool("my_tool", "A tool", {"type": "object"}, dummy_handler)
        ctx = self._make_context(config)
        handler = server._tools[_HEALTH_TOOL_NAME]["handler"]
        data = json.loads(await handler({}, ctx))
        assert _HEALTH_TOOL_NAME in data["tools_loaded"]
        assert "my_tool" in data["tools_loaded"]

    @pytest.mark.asyncio
    async def test_health_check_contains_uptime(self) -> None:
        config = _make_config()
        server = ChassisServer(config)
        ctx = self._make_context(config)
        handler = server._tools[_HEALTH_TOOL_NAME]["handler"]
        data = json.loads(await handler({}, ctx))
        assert "uptime_seconds" in data
        assert data["uptime_seconds"] >= 0.0

    @pytest.mark.asyncio
    async def test_health_check_contains_security_profile(self) -> None:
        config = _make_config()
        server = ChassisServer(config)
        ctx = self._make_context(config)
        handler = server._tools[_HEALTH_TOOL_NAME]["handler"]
        data = json.loads(await handler({}, ctx))
        assert "security_profile" in data
        assert data["security_profile"] == "strict"

    @pytest.mark.asyncio
    async def test_health_check_no_config_summary_by_default(self) -> None:
        config = _make_config(include_config_summary=False)
        server = ChassisServer(config)
        ctx = self._make_context(config)
        handler = server._tools[_HEALTH_TOOL_NAME]["handler"]
        data = json.loads(await handler({}, ctx))
        assert "config_summary" not in data

    @pytest.mark.asyncio
    async def test_health_check_with_config_summary(self) -> None:
        config = _make_config(include_config_summary=True)
        server = ChassisServer(config)
        ctx = self._make_context(config)
        handler = server._tools[_HEALTH_TOOL_NAME]["handler"]
        data = json.loads(await handler({}, ctx))
        assert "config_summary" in data
        summary = data["config_summary"]
        assert "transport" in summary
        assert "rate_limiting" in summary
        assert "auth_enabled" in summary
        assert "log_level" in summary

    @pytest.mark.asyncio
    async def test_health_check_contains_python_version(self) -> None:
        config = _make_config()
        server = ChassisServer(config)
        ctx = self._make_context(config)
        handler = server._tools[_HEALTH_TOOL_NAME]["handler"]
        data = json.loads(await handler({}, ctx))
        assert "python_version" in data

    @pytest.mark.asyncio
    async def test_health_check_contains_chassis_version(self) -> None:
        config = _make_config()
        server = ChassisServer(config)
        ctx = self._make_context(config)
        handler = server._tools[_HEALTH_TOOL_NAME]["handler"]
        data = json.loads(await handler({}, ctx))
        assert "chassis_version" in data
        import mcp_chassis
        assert data["chassis_version"] == mcp_chassis.__version__

    @pytest.mark.asyncio
    async def test_health_check_resources_and_prompts_empty(self) -> None:
        config = _make_config()
        server = ChassisServer(config)
        ctx = self._make_context(config)
        handler = server._tools[_HEALTH_TOOL_NAME]["handler"]
        data = json.loads(await handler({}, ctx))
        assert "resources_loaded" in data
        assert "prompts_loaded" in data
        assert data["resources_loaded"] == []
        assert data["prompts_loaded"] == []
