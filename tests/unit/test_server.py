"""Unit tests for mcp_chassis.server module."""

from __future__ import annotations

import json
from typing import Any

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
from mcp_chassis.server import ChassisServer

# Re-use the shared test config builder from conftest (imported via pytest's
# conftest mechanism — the path must be relative to the tests root).
from tests.conftest import make_test_config


@pytest.fixture()
def server() -> ChassisServer:
    """Return a ChassisServer with minimal config (no health check, no discovery)."""
    return ChassisServer(make_test_config())


class TestServerRegistration:
    """Tests for register_tool, register_resource, register_prompt."""

    def test_register_tool(self, server: ChassisServer) -> None:
        async def handler(args: dict, ctx: HandlerContext) -> str:
            return "result"

        server.register_tool("my_tool", "desc", {"type": "object"}, handler)
        assert "my_tool" in server.list_tool_names()

    def test_register_resource(self, server: ChassisServer) -> None:
        async def handler(uri: str, ctx: HandlerContext) -> str:
            return "content"

        server.register_resource("template://test", handler, name="Test", mime_type="text/plain")
        assert "template://test" in server.list_resource_uris()

    def test_register_prompt(self, server: ChassisServer) -> None:
        async def handler(args: dict, ctx: HandlerContext) -> list:
            return []

        server.register_prompt("my_prompt", handler, description="A prompt")
        assert "my_prompt" in server.list_prompt_names()

    def test_duplicate_tool_raises(self, server: ChassisServer) -> None:
        async def h1(args: dict, ctx: HandlerContext) -> str:
            return "v1"

        async def h2(args: dict, ctx: HandlerContext) -> str:
            return "v2"

        server.register_tool("my_tool", "first", {"type": "object"}, h1)
        with pytest.raises(ValueError, match="my_tool"):
            server.register_tool("my_tool", "second", {"type": "object"}, h2)

    def test_duplicate_tool_allowed_with_overwrite(self, server: ChassisServer) -> None:
        async def h1(args: dict, ctx: HandlerContext) -> str:
            return "v1"

        async def h2(args: dict, ctx: HandlerContext) -> str:
            return "v2"

        server.register_tool("my_tool", "first", {"type": "object"}, h1)
        server.register_tool(
            "my_tool", "second", {"type": "object"}, h2, allow_overwrite=True
        )
        assert server._tools["my_tool"]["description"] == "second"

    def test_duplicate_resource_raises(self, server: ChassisServer) -> None:
        async def h1(uri: str, ctx: HandlerContext) -> str:
            return "v1"

        async def h2(uri: str, ctx: HandlerContext) -> str:
            return "v2"

        server.register_resource("template://test", h1)
        with pytest.raises(ValueError, match="template://test"):
            server.register_resource("template://test", h2)

    def test_duplicate_resource_allowed_with_overwrite(self, server: ChassisServer) -> None:
        async def h1(uri: str, ctx: HandlerContext) -> str:
            return "v1"

        async def h2(uri: str, ctx: HandlerContext) -> str:
            return "v2"

        server.register_resource("template://test", h1, name="First")
        server.register_resource(
            "template://test", h2, name="Second", allow_overwrite=True
        )
        assert server._resources["template://test"]["name"] == "Second"

    def test_duplicate_prompt_raises(self, server: ChassisServer) -> None:
        async def h1(args: dict, ctx: HandlerContext) -> list:
            return []

        async def h2(args: dict, ctx: HandlerContext) -> list:
            return []

        server.register_prompt("my_prompt", h1)
        with pytest.raises(ValueError, match="my_prompt"):
            server.register_prompt("my_prompt", h2)

    def test_duplicate_prompt_allowed_with_overwrite(self, server: ChassisServer) -> None:
        async def h1(args: dict, ctx: HandlerContext) -> list:
            return []

        async def h2(args: dict, ctx: HandlerContext) -> list:
            return []

        server.register_prompt("my_prompt", h1, description="First")
        server.register_prompt(
            "my_prompt", h2, description="Second", allow_overwrite=True
        )
        assert server._prompts["my_prompt"]["description"] == "Second"

    def test_register_tool_with_auth_scopes(self, server: ChassisServer) -> None:
        async def handler(args: dict, ctx: HandlerContext) -> str:
            return "ok"

        server.register_tool(
            "secure_tool", "desc", {"type": "object"}, handler, auth_scopes=["admin"]
        )
        assert server._tools["secure_tool"]["auth_scopes"] == ["admin"]

    def test_list_tool_names_empty_without_health(self, server: ChassisServer) -> None:
        assert server.list_tool_names() == []

    def test_list_resource_uris_empty(self, server: ChassisServer) -> None:
        assert server.list_resource_uris() == []

    def test_list_prompt_names_empty(self, server: ChassisServer) -> None:
        assert server.list_prompt_names() == []

    def test_multiple_tools(self, server: ChassisServer) -> None:
        async def h(args: dict, ctx: HandlerContext) -> str:
            return ""

        server.register_tool("t1", "d", {"type": "object"}, h)
        server.register_tool("t2", "d", {"type": "object"}, h)
        names = server.list_tool_names()
        assert "t1" in names
        assert "t2" in names


class TestServerToolDispatch:
    """Tests for tool dispatch via _dispatch_tool."""

    @pytest.mark.asyncio
    async def test_tool_returns_string(self, server: ChassisServer) -> None:
        async def handler(args: dict, ctx: HandlerContext) -> str:
            return "hello world"

        server.register_tool("echo", "echo", {"type": "object"}, handler)
        result = await server._dispatch_tool("echo", {})
        assert not result.isError
        assert result.content[0].text == "hello world"  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_tool_returns_dict(self, server: ChassisServer) -> None:
        async def handler(args: dict, ctx: HandlerContext) -> dict:
            return {"status": "ok"}

        server.register_tool("info", "info", {"type": "object"}, handler)
        result = await server._dispatch_tool("info", {})
        assert not result.isError
        data = json.loads(result.content[0].text)  # type: ignore[union-attr]
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self, server: ChassisServer) -> None:
        result = await server._dispatch_tool("nonexistent", {})
        assert result.isError
        assert "TOOL_NOT_FOUND" in result.content[0].text  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_handler_exception_returns_error(self, server: ChassisServer) -> None:
        async def failing_handler(args: dict, ctx: HandlerContext) -> str:
            raise ValueError("something went wrong")

        server.register_tool("broken", "broken", {"type": "object"}, failing_handler)
        result = await server._dispatch_tool("broken", {})
        assert result.isError
        assert "HANDLER_ERROR" in result.content[0].text  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_handler_receives_arguments(self, server: ChassisServer) -> None:
        received: dict[str, Any] = {}

        async def capturing_handler(args: dict, ctx: HandlerContext) -> str:
            received.update(args)
            return "ok"

        server.register_tool(
            "capture",
            "capture",
            {"type": "object", "properties": {"x": {"type": "string"}}},
            capturing_handler,
        )
        await server._dispatch_tool("capture", {"x": "value"})
        assert received.get("x") == "value"

    @pytest.mark.asyncio
    async def test_handler_receives_context(self, server: ChassisServer) -> None:
        received_ctx: list[HandlerContext] = []

        async def ctx_capturing_handler(args: dict, ctx: HandlerContext) -> str:
            received_ctx.append(ctx)
            return "ok"

        server.register_tool("ctx_tool", "d", {"type": "object"}, ctx_capturing_handler)
        await server._dispatch_tool("ctx_tool", {})
        assert len(received_ctx) == 1
        assert received_ctx[0].server_config is server._config

    @pytest.mark.asyncio
    async def test_oversized_response_returns_error(self) -> None:
        config = make_test_config(io_response_limit=10)
        s = ChassisServer(config)

        async def big_handler(args: dict, ctx: HandlerContext) -> str:
            return "x" * 100

        s.register_tool("big", "big", {"type": "object"}, big_handler)
        result = await s._dispatch_tool("big", {})
        assert result.isError
        text = result.content[0].text  # type: ignore[union-attr]
        assert "IO_LIMIT_EXCEEDED" in text or "RESPONSE_TOO_LARGE" in text

    @pytest.mark.asyncio
    async def test_middleware_blocks_oversized_input(self) -> None:
        config = make_test_config(io_request_limit=10)
        s = ChassisServer(config)

        async def handler(args: dict, ctx: HandlerContext) -> str:
            return "ok"

        s.register_tool("t", "t", {"type": "object"}, handler)
        result = await s._dispatch_tool("t", {"data": "x" * 100})
        assert result.isError


class TestNonSerializableHandlerReturn:
    """Tests for handler returning non-JSON-serializable objects."""

    @pytest.mark.asyncio
    async def test_non_serializable_return_produces_error(self, server: ChassisServer) -> None:
        from datetime import datetime

        async def handler(args: dict, ctx: HandlerContext) -> Any:
            return {"time": datetime.now()}

        server.register_tool("bad_return", "d", {"type": "object"}, handler)
        result = await server._dispatch_tool("bad_return", {})
        assert result.isError
        assert "HANDLER_ERROR" in result.content[0].text  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_set_return_produces_error(self, server: ChassisServer) -> None:
        async def handler(args: dict, ctx: HandlerContext) -> Any:
            return {"items": {1, 2, 3}}

        server.register_tool("set_return", "d", {"type": "object"}, handler)
        result = await server._dispatch_tool("set_return", {})
        assert result.isError


class TestDetailedErrors:
    """Tests for detailed_errors config controlling error verbosity."""

    @pytest.mark.asyncio
    async def test_detailed_errors_includes_message(self) -> None:
        config = make_test_config(io_response_limit=10)
        config = ServerConfig(
            server=config.server,
            security=SecurityConfig(
                rate_limits=config.security.rate_limits,
                io_limits=config.security.io_limits,
                input_validation=config.security.input_validation,
                input_sanitization=config.security.input_sanitization,
                auth=config.security.auth,
                detailed_errors=True,
            ),
            extensions=config.extensions,
            diagnostics=config.diagnostics,
        )
        s = ChassisServer(config)

        async def big_handler(args: dict, ctx: HandlerContext) -> str:
            return "x" * 100

        s.register_tool("big", "big", {"type": "object"}, big_handler)
        result = await s._dispatch_tool("big", {})
        assert result.isError
        text = result.content[0].text  # type: ignore[union-attr]
        # Detailed mode: message includes specifics like sizes
        assert "exceeds" in text.lower() or "100" in text or "10" in text

    @pytest.mark.asyncio
    async def test_generic_errors_hides_details(self) -> None:
        config = make_test_config(io_response_limit=10)
        # detailed_errors defaults to False
        s = ChassisServer(config)

        async def big_handler(args: dict, ctx: HandlerContext) -> str:
            return "x" * 100

        s.register_tool("big", "big", {"type": "object"}, big_handler)
        result = await s._dispatch_tool("big", {})
        assert result.isError
        text = result.content[0].text  # type: ignore[union-attr]
        # Generic mode: message says "Request failed", no size details
        assert "Request failed" in text
        assert "correlation_id=" in text
        assert "exceeds" not in text.lower()


class TestServerResourceDispatch:
    """Tests for resource dispatch via _dispatch_resource."""

    @pytest.mark.asyncio
    async def test_resource_returns_content(self, server: ChassisServer) -> None:
        async def handler(uri: str, ctx: HandlerContext) -> str:
            return '{"key": "value"}'

        server.register_resource("template://test", handler, mime_type="application/json")
        contents = await server._dispatch_resource("template://test")
        assert len(contents) == 1
        assert contents[0].content == '{"key": "value"}'

    @pytest.mark.asyncio
    async def test_unknown_resource_raises(self, server: ChassisServer) -> None:
        from mcp.shared.exceptions import McpError
        with pytest.raises(McpError):
            await server._dispatch_resource("template://unknown")

    @pytest.mark.asyncio
    async def test_resource_handler_exception_raises(self, server: ChassisServer) -> None:
        async def failing_handler(uri: str, ctx: HandlerContext) -> str:
            raise RuntimeError("resource error")

        server.register_resource("template://fail", failing_handler)
        from mcp.shared.exceptions import McpError
        with pytest.raises(McpError):
            await server._dispatch_resource("template://fail")


class TestServerPromptDispatch:
    """Tests for prompt dispatch via _dispatch_prompt."""

    @pytest.mark.asyncio
    async def test_prompt_returns_messages(self, server: ChassisServer) -> None:
        async def handler(args: dict, ctx: HandlerContext) -> list:
            return [{"role": "user", "content": f"Hello {args.get('name', 'World')}"}]

        server.register_prompt(
            "greet",
            handler,
            description="A greeting",
            arguments=[{"name": "name", "required": True}],
        )
        result = await server._dispatch_prompt("greet", {"name": "Alice"})
        assert len(result.messages) == 1
        assert "Alice" in result.messages[0].content.text  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_unknown_prompt_raises(self, server: ChassisServer) -> None:
        from mcp.shared.exceptions import McpError
        with pytest.raises(McpError):
            await server._dispatch_prompt("nonexistent", {})

    @pytest.mark.asyncio
    async def test_prompt_handler_exception_raises(self, server: ChassisServer) -> None:
        async def failing_handler(args: dict, ctx: HandlerContext) -> list:
            raise ValueError("prompt error")

        server.register_prompt("broken", failing_handler)
        from mcp.shared.exceptions import McpError
        with pytest.raises(McpError):
            await server._dispatch_prompt("broken", {})

    @pytest.mark.asyncio
    async def test_build_prompt_list_includes_arguments(self, server: ChassisServer) -> None:
        async def handler(args: dict, ctx: HandlerContext) -> list:
            return []

        server.register_prompt(
            "with_args",
            handler,
            arguments=[
                {"name": "param1", "description": "First param", "required": True},
                {"name": "param2", "description": "Second param", "required": False},
            ],
        )
        prompts = await server._build_prompt_list()
        prompt = next(p for p in prompts if p.name == "with_args")
        assert prompt.arguments is not None
        assert len(prompt.arguments) == 2
        assert prompt.arguments[0].name == "param1"
        assert prompt.arguments[0].required


class TestServerHealthCheck:
    """Tests for health check integration with server."""

    def test_health_check_enabled_by_default(self) -> None:
        config = make_test_config(health_enabled=True)
        server = ChassisServer(config)
        assert "__health_check" in server.list_tool_names()

    def test_health_check_disabled(self) -> None:
        config = make_test_config(health_enabled=False)
        server = ChassisServer(config)
        assert "__health_check" not in server.list_tool_names()


class TestServerTransport:
    """Tests for transport selection in server.run()."""

    def test_invalid_transport_rejected_by_config(self, tmp_path: Any) -> None:
        """Unsupported transport names are rejected at config load time."""

        toml = tmp_path / "c.toml"
        toml.write_bytes(b"[server]\ntransport = 'sse'\n")
        with pytest.raises(ValueError, match="Invalid transport"):
            ServerConfig.load(toml)


def _make_auth_config(
    *, auth_enabled: bool = True, provider: str = "token", token: str = "test-secret"
) -> ServerConfig:
    """Build a ServerConfig with token auth for testing."""
    return ServerConfig(
        server=ServerSettings(),
        security=SecurityConfig(
            rate_limits=RateLimitConfig(enabled=False),
            io_limits=IOLimitConfig(),
            input_validation=ValidationConfig(enabled=False),
            input_sanitization=SanitizationConfig(enabled=False, level="permissive"),
            auth=AuthConfig(enabled=auth_enabled, provider=provider, token=token),
        ),
        extensions=ExtensionSettings(auto_discover=False),
        diagnostics=DiagnosticSettings(health_check_enabled=False),
    )


class TestTokenAuthOnStdio:
    """Tests that token auth is rejected on stdio transport (fail-closed)."""

    def test_token_auth_on_stdio_raises_at_startup(self) -> None:
        """Server refuses to start with token auth on stdio transport."""
        config = _make_auth_config(token="my-secret")
        with pytest.raises(ValueError, match="[Tt]oken auth.*stdio"):
            ChassisServer(config)

    def test_token_auth_no_token_on_stdio_raises(self) -> None:
        """Server refuses to start with token auth enabled but no token on stdio."""
        config = _make_auth_config(token="")
        with pytest.raises(ValueError, match="[Tt]oken auth.*stdio"):
            ChassisServer(config)

    @pytest.mark.asyncio
    async def test_no_auth_still_works(self) -> None:
        """Tool call succeeds when auth is disabled (NoAuthProvider)."""
        config = _make_auth_config(auth_enabled=False, provider="none", token="")
        s = ChassisServer(config)

        async def handler(args: dict, ctx: HandlerContext) -> str:
            return "fine"

        s.register_tool("t", "d", {"type": "object"}, handler)
        result = await s._dispatch_tool("t", {})
        assert not result.isError


class TestResourceRegistrationWithScopes:
    """Tests for register_resource with auth_scopes."""

    def test_register_resource_with_auth_scopes(self, server: ChassisServer) -> None:
        async def handler(uri: str, ctx: HandlerContext) -> str:
            return "content"

        server.register_resource(
            "template://secure",
            handler,
            name="Secure",
            auth_scopes=["admin"],
        )
        assert server._resources["template://secure"]["auth_scopes"] == ["admin"]

    def test_register_resource_default_no_scopes(self, server: ChassisServer) -> None:
        async def handler(uri: str, ctx: HandlerContext) -> str:
            return "content"

        server.register_resource("template://open", handler)
        assert server._resources["template://open"]["auth_scopes"] == []


class TestPromptRegistrationWithScopes:
    """Tests for register_prompt with auth_scopes."""

    def test_register_prompt_with_auth_scopes(self, server: ChassisServer) -> None:
        async def handler(args: dict, ctx: HandlerContext) -> list:
            return []

        server.register_prompt("secure_prompt", handler, auth_scopes=["admin"])
        assert server._prompts["secure_prompt"]["auth_scopes"] == ["admin"]

    def test_register_prompt_default_no_scopes(self, server: ChassisServer) -> None:
        async def handler(args: dict, ctx: HandlerContext) -> list:
            return []

        server.register_prompt("open_prompt", handler)
        assert server._prompts["open_prompt"]["auth_scopes"] == []


class TestResourceDispatchMiddleware:
    """Tests for middleware enforcement on resource dispatch."""

    # Note: auth blocking is tested at the pipeline level (test_pipeline.py).
    # Token auth on stdio is rejected at startup, so server-level dispatch
    # tests use NoAuth (auth disabled).

    @pytest.mark.asyncio
    async def test_resource_blocked_by_rate_limit(self) -> None:
        config = ServerConfig(
            server=ServerSettings(),
            security=SecurityConfig(
                rate_limits=RateLimitConfig(
                    enabled=True, global_rpm=60, per_tool_rpm=30, burst_size=1,
                ),
                io_limits=IOLimitConfig(),
                input_validation=ValidationConfig(enabled=False),
                input_sanitization=SanitizationConfig(enabled=False, level="permissive"),
                auth=AuthConfig(enabled=False, provider="none"),
            ),
            extensions=ExtensionSettings(auto_discover=False),
            diagnostics=DiagnosticSettings(health_check_enabled=False),
        )
        s = ChassisServer(config)

        async def handler(uri: str, ctx: HandlerContext) -> str:
            return "content"

        s.register_resource("template://test", handler)

        # First request should pass (burst=1)
        result1 = await s._dispatch_resource("template://test")
        assert len(result1) == 1

        # Second should be rate limited
        from mcp.shared.exceptions import McpError
        with pytest.raises(McpError) as exc_info:
            await s._dispatch_resource("template://test")
        assert "RATE_LIMIT_EXCEEDED" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_resource_response_size_check(self) -> None:
        config = ServerConfig(
            server=ServerSettings(),
            security=SecurityConfig(
                rate_limits=RateLimitConfig(enabled=False),
                io_limits=IOLimitConfig(
                    max_request_size=1_048_576, max_response_size=10,
                ),
                input_validation=ValidationConfig(enabled=False),
                input_sanitization=SanitizationConfig(enabled=False, level="permissive"),
                auth=AuthConfig(enabled=False, provider="none"),
            ),
            extensions=ExtensionSettings(auto_discover=False),
            diagnostics=DiagnosticSettings(health_check_enabled=False),
        )
        s = ChassisServer(config)

        async def big_handler(uri: str, ctx: HandlerContext) -> str:
            return "x" * 1000

        s.register_resource("template://big", big_handler)
        from mcp.shared.exceptions import McpError
        with pytest.raises(McpError) as exc_info:
            await s._dispatch_resource("template://big")
        assert "RESPONSE_TOO_LARGE" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_resource_passes_all_middleware(self) -> None:
        config = _make_auth_config(auth_enabled=False, provider="none", token="")
        s = ChassisServer(config)

        async def handler(uri: str, ctx: HandlerContext) -> str:
            return "content"

        s.register_resource("template://test", handler)
        result = await s._dispatch_resource("template://test")
        assert len(result) == 1
        assert result[0].content == "content"


class TestPromptDispatchMiddleware:
    """Tests for middleware enforcement on prompt dispatch."""

    # Note: auth blocking is tested at the pipeline level (test_pipeline.py).
    # Token auth on stdio is rejected at startup.

    @pytest.mark.asyncio
    async def test_prompt_blocked_by_rate_limit(self) -> None:
        config = ServerConfig(
            server=ServerSettings(),
            security=SecurityConfig(
                rate_limits=RateLimitConfig(
                    enabled=True, global_rpm=60, per_tool_rpm=30, burst_size=1,
                ),
                io_limits=IOLimitConfig(),
                input_validation=ValidationConfig(enabled=False),
                input_sanitization=SanitizationConfig(enabled=False, level="permissive"),
                auth=AuthConfig(enabled=False, provider="none"),
            ),
            extensions=ExtensionSettings(auto_discover=False),
            diagnostics=DiagnosticSettings(health_check_enabled=False),
        )
        s = ChassisServer(config)

        async def handler(args: dict, ctx: HandlerContext) -> list:
            return [{"role": "user", "content": "hi"}]

        s.register_prompt("greet", handler)

        # First passes (burst=1)
        result1 = await s._dispatch_prompt("greet", {})
        assert len(result1.messages) == 1

        # Second rate limited
        from mcp.shared.exceptions import McpError
        with pytest.raises(McpError) as exc_info:
            await s._dispatch_prompt("greet", {})
        assert "RATE_LIMIT_EXCEEDED" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_prompt_sanitizes_arguments(self) -> None:
        config = ServerConfig(
            server=ServerSettings(),
            security=SecurityConfig(
                rate_limits=RateLimitConfig(enabled=False),
                io_limits=IOLimitConfig(),
                input_validation=ValidationConfig(enabled=False),
                input_sanitization=SanitizationConfig(enabled=True, level="strict"),
                auth=AuthConfig(enabled=False, provider="none"),
            ),
            extensions=ExtensionSettings(auto_discover=False),
            diagnostics=DiagnosticSettings(health_check_enabled=False),
        )
        s = ChassisServer(config)

        received_args: dict[str, Any] = {}

        async def capturing_handler(args: dict, ctx: HandlerContext) -> list:
            received_args.update(args)
            return [{"role": "user", "content": "hi"}]

        s.register_prompt("greet", capturing_handler)
        await s._dispatch_prompt("greet", {"topic": "hello; rm -rf /"})
        # Shell metacharacters should be sanitized before reaching handler
        assert ";" not in received_args.get("topic", "")

    @pytest.mark.asyncio
    async def test_prompt_oversized_args_blocked(self) -> None:
        config = ServerConfig(
            server=ServerSettings(),
            security=SecurityConfig(
                rate_limits=RateLimitConfig(enabled=False),
                io_limits=IOLimitConfig(max_request_size=10, max_response_size=5_242_880),
                input_validation=ValidationConfig(enabled=False),
                input_sanitization=SanitizationConfig(enabled=False, level="permissive"),
                auth=AuthConfig(enabled=False, provider="none"),
            ),
            extensions=ExtensionSettings(auto_discover=False),
            diagnostics=DiagnosticSettings(health_check_enabled=False),
        )
        s = ChassisServer(config)

        async def handler(args: dict, ctx: HandlerContext) -> list:
            return [{"role": "user", "content": "hi"}]

        s.register_prompt("greet", handler)
        from mcp.shared.exceptions import McpError
        with pytest.raises(McpError) as exc_info:
            await s._dispatch_prompt("greet", {"data": "x" * 100})
        assert "REQUEST_TOO_LARGE" in str(exc_info.value) or "IO_LIMIT" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_prompt_oversized_response_blocked(self) -> None:
        """Prompt handler returning oversized content should be rejected."""
        config = ServerConfig(
            server=ServerSettings(),
            security=SecurityConfig(
                rate_limits=RateLimitConfig(enabled=False),
                io_limits=IOLimitConfig(max_request_size=1_048_576, max_response_size=50),
                input_validation=ValidationConfig(enabled=False),
                input_sanitization=SanitizationConfig(enabled=False, level="permissive"),
                auth=AuthConfig(enabled=False, provider="none"),
            ),
            extensions=ExtensionSettings(auto_discover=False),
            diagnostics=DiagnosticSettings(health_check_enabled=False),
        )
        s = ChassisServer(config)

        async def big_handler(args: dict, ctx: HandlerContext) -> list:
            return [{"role": "user", "content": "x" * 1000}]

        s.register_prompt("big", big_handler)
        from mcp.shared.exceptions import McpError

        with pytest.raises(McpError) as exc_info:
            await s._dispatch_prompt("big", {})
        assert "RESPONSE_TOO_LARGE" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_prompt_passes_all_middleware(self) -> None:
        config = _make_auth_config(auth_enabled=False, provider="none", token="")
        s = ChassisServer(config)

        async def handler(args: dict, ctx: HandlerContext) -> list:
            return [{"role": "user", "content": f"hello {args.get('name', '')}"}]

        s.register_prompt("greet", handler)
        result = await s._dispatch_prompt("greet", {"name": "Alice"})
        assert len(result.messages) == 1
        assert "Alice" in result.messages[0].content.text  # type: ignore[union-attr]


class TestCorrelationIdInLogs:
    """Tests that ChassisError log entries include the context's correlation_id."""

    @pytest.mark.asyncio
    async def test_template_error_log_includes_context_correlation_id(
        self, server: ChassisServer, caplog: Any
    ) -> None:
        """When a handler raises ChassisError, the log should include both IDs."""
        from mcp_chassis.errors import ValidationError

        async def failing_handler(args: dict, ctx: HandlerContext) -> str:
            raise ValidationError("bad input")

        server.register_tool("fail", "d", {"type": "object"}, failing_handler)
        import logging

        with caplog.at_level(logging.ERROR, logger="mcp_chassis.server"):
            await server._dispatch_tool("fail", {})
        # Log entry should contain "request_correlation_id=" with context's ID
        assert "request_correlation_id=" in caplog.text


class TestInitHook:
    """Tests for the extensions.init_module lifecycle hook."""

    def test_init_hook_called_when_configured(self, tmp_path: Any) -> None:
        """on_init(server) is called when init_module is set."""
        # Create a temp module that sets an attribute on the server
        init_file = tmp_path / "test_init_hook.py"
        init_file.write_text(
            "def on_init(server):\n"
            "    server._test_init_called = True\n"
        )
        import sys
        sys.path.insert(0, str(tmp_path))
        try:
            config = make_test_config(init_module="test_init_hook")
            server = ChassisServer(config)
            assert server._test_init_called is True
        finally:
            sys.path.pop(0)
            sys.modules.pop("test_init_hook", None)

    def test_no_init_hook_when_not_configured(self) -> None:
        """No hook runs when init_module is empty (default)."""
        config = make_test_config()
        server = ChassisServer(config)
        assert not hasattr(server, "_test_init_called")

    def test_init_hook_bad_module_logs_error(self, caplog: Any) -> None:
        """A nonexistent init_module logs an error but doesn't crash the server."""
        import logging
        config = make_test_config(init_module="nonexistent_module_xyz")
        with caplog.at_level(logging.ERROR, logger="mcp_chassis.server"):
            ChassisServer(config)
        assert "nonexistent_module_xyz" in caplog.text

    def test_init_hook_runs_before_extension_discovery(self, tmp_path: Any) -> None:
        """The init hook runs before extensions are discovered."""
        init_file = tmp_path / "test_init_order.py"
        init_file.write_text(
            "def on_init(server):\n"
            "    server._init_hook_ran = True\n"
        )
        import sys
        sys.path.insert(0, str(tmp_path))
        try:
            config = make_test_config(
                init_module="test_init_order",
                auto_discover=True,
            )
            server = ChassisServer(config)
            # If the hook ran before discovery, extensions can access
            # the attribute set by the hook
            assert server._init_hook_ran is True
        finally:
            sys.path.pop(0)
            sys.modules.pop("test_init_order", None)


class TestTransportConfig:
    """Tests for transport initialization."""

    def test_stdio_transport_uses_default_line_limit(self) -> None:
        """StdioTransport should use its own default, not max_request_size."""
        from mcp_chassis.transport.stdio import _DEFAULT_MAX_LINE_BYTES

        config = make_test_config(io_request_limit=50_000_000)  # 50 MB
        ChassisServer(config)  # Ensure config is valid

        # The transport limit is independent of max_request_size.
        assert _DEFAULT_MAX_LINE_BYTES == 1_048_576
        assert config.security.io_limits.max_request_size == 50_000_000
        assert _DEFAULT_MAX_LINE_BYTES != config.security.io_limits.max_request_size
