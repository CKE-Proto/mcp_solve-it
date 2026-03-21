"""Unit tests for mcp_chassis.middleware.pipeline module."""

import pytest

from mcp_chassis.config import (
    AuthConfig,
    IOLimitConfig,
    RateLimitConfig,
    SanitizationConfig,
    SecurityConfig,
    ValidationConfig,
)
from mcp_chassis.middleware.pipeline import MiddlewarePipeline, MiddlewareResult


def _make_security_config(**overrides: object) -> SecurityConfig:
    """Build a SecurityConfig with sensible defaults, applying any overrides."""
    defaults = dict(
        rate_limits=RateLimitConfig(enabled=False),
        io_limits=IOLimitConfig(max_request_size=1_048_576, max_response_size=5_242_880),
        input_validation=ValidationConfig(enabled=True),
        input_sanitization=SanitizationConfig(enabled=True, level="strict"),
        auth=AuthConfig(enabled=False, provider="none"),
    )
    defaults.update(overrides)
    return SecurityConfig(**defaults)  # type: ignore[arg-type]


@pytest.fixture()
def permissive_config() -> SecurityConfig:
    """Return a permissive SecurityConfig with rate limiting and validation disabled."""
    return _make_security_config(
        rate_limits=RateLimitConfig(enabled=False),
        input_validation=ValidationConfig(enabled=False),
        input_sanitization=SanitizationConfig(enabled=False, level="permissive"),
    )


@pytest.fixture()
def strict_config() -> SecurityConfig:
    """Return a strict SecurityConfig with everything enabled."""
    return _make_security_config(
        rate_limits=RateLimitConfig(enabled=True, global_rpm=60, per_tool_rpm=30, burst_size=5),
        input_validation=ValidationConfig(enabled=True),
        input_sanitization=SanitizationConfig(enabled=True, level="strict"),
    )


class TestMiddlewareResult:
    """Tests for MiddlewareResult dataclass."""

    def test_ok_result(self) -> None:
        args = {"key": "value"}
        result = MiddlewareResult.ok(args)
        assert result.allowed
        assert result.sanitized_arguments == args
        assert result.error_code == ""
        assert result.error_message == ""

    def test_error_result_from_template_error(self) -> None:
        from mcp_chassis.errors import ValidationError

        exc = ValidationError("bad input")
        result = MiddlewareResult.error(exc)
        assert not result.allowed
        assert result.error_code == "VALIDATION_ERROR"
        assert result.correlation_id == exc.correlation_id
        assert "bad input" in result.error_message

    def test_error_result_from_rate_limit_error(self) -> None:
        from mcp_chassis.errors import RateLimitError

        exc = RateLimitError("too fast", retry_after=2.0)
        result = MiddlewareResult.error(exc)
        assert not result.allowed
        assert result.error_code == "RATE_LIMIT_EXCEEDED"


class TestMiddlewarePipelinePassthrough:
    """Tests for successful middleware pipeline pass-through."""

    @pytest.mark.asyncio
    async def test_valid_request_passes(self, permissive_config: SecurityConfig) -> None:
        pipeline = MiddlewarePipeline(permissive_config)
        schema = {"type": "object", "properties": {"msg": {"type": "string"}}}
        result = await pipeline.process_tool_request("test_tool", {"msg": "hello"}, schema, {})
        assert result.allowed
        assert result.sanitized_arguments == {"msg": "hello"}

    @pytest.mark.asyncio
    async def test_empty_arguments_passes(self, permissive_config: SecurityConfig) -> None:
        pipeline = MiddlewarePipeline(permissive_config)
        result = await pipeline.process_tool_request("tool", {}, {"type": "object"}, {})
        assert result.allowed

    @pytest.mark.asyncio
    async def test_sanitization_applied(self, strict_config: SecurityConfig) -> None:
        """Sanitization strips shell metacharacters in strict mode."""
        pipeline = MiddlewarePipeline(strict_config)
        schema = {"type": "object", "properties": {"cmd": {"type": "string"}}, "required": ["cmd"]}
        result = await pipeline.process_tool_request(
            "tool", {"cmd": "ls; rm -rf /"}, schema, {}
        )
        assert result.allowed
        # Shell metacharacters should be stripped
        assert result.sanitized_arguments is not None
        assert ";" not in result.sanitized_arguments["cmd"]


class TestMiddlewarePipelineIOLimits:
    """Tests for I/O limit enforcement."""

    @pytest.mark.asyncio
    async def test_oversized_request_blocked(self) -> None:
        config = _make_security_config(
            io_limits=IOLimitConfig(max_request_size=10, max_response_size=5_242_880),
        )
        pipeline = MiddlewarePipeline(config)
        result = await pipeline.process_tool_request(
            "tool", {"data": "x" * 100}, {"type": "object"}, {}
        )
        assert not result.allowed
        assert result.error_code in ("REQUEST_TOO_LARGE", "IO_LIMIT_EXCEEDED")

    def test_oversized_response_raises(self) -> None:
        config = _make_security_config(
            io_limits=IOLimitConfig(max_request_size=1_048_576, max_response_size=10),
        )
        pipeline = MiddlewarePipeline(config)
        from mcp_chassis.errors import IOLimitError
        with pytest.raises(IOLimitError):
            pipeline.check_response_size("x" * 100)

    def test_response_within_limit_passes(self) -> None:
        config = _make_security_config(
            io_limits=IOLimitConfig(max_request_size=1_048_576, max_response_size=1_048_576),
        )
        pipeline = MiddlewarePipeline(config)
        # Should not raise
        pipeline.check_response_size("ok")


class TestMiddlewarePipelineValidation:
    """Tests for input validation in the pipeline."""

    @pytest.mark.asyncio
    async def test_missing_required_field_blocked(self) -> None:
        config = _make_security_config(
            input_validation=ValidationConfig(enabled=True),
            input_sanitization=SanitizationConfig(enabled=False, level="permissive"),
        )
        pipeline = MiddlewarePipeline(config)
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        result = await pipeline.process_tool_request("tool", {}, schema, {})
        assert not result.allowed
        assert result.error_code == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_wrong_type_blocked(self) -> None:
        config = _make_security_config(
            input_validation=ValidationConfig(enabled=True),
            input_sanitization=SanitizationConfig(enabled=False, level="permissive"),
        )
        pipeline = MiddlewarePipeline(config)
        schema = {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
        }
        result = await pipeline.process_tool_request("tool", {"count": "not-a-number"}, schema, {})
        assert not result.allowed
        assert result.error_code == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_validation_disabled_allows_invalid(self) -> None:
        config = _make_security_config(
            input_validation=ValidationConfig(enabled=False),
            input_sanitization=SanitizationConfig(enabled=False, level="permissive"),
        )
        pipeline = MiddlewarePipeline(config)
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        # Missing required field but validation is disabled
        result = await pipeline.process_tool_request("tool", {}, schema, {})
        assert result.allowed


class TestMiddlewarePipelineRateLimit:
    """Tests for rate limiting in the pipeline."""

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_excess_requests(self) -> None:
        config = _make_security_config(
            rate_limits=RateLimitConfig(enabled=True, global_rpm=60, per_tool_rpm=30, burst_size=1),
            input_validation=ValidationConfig(enabled=False),
            input_sanitization=SanitizationConfig(enabled=False, level="permissive"),
        )
        pipeline = MiddlewarePipeline(config)

        # First request should pass (burst allows 1)
        r1 = await pipeline.process_tool_request("tool", {}, {"type": "object"}, {})
        assert r1.allowed

        # Second request should be rate limited
        r2 = await pipeline.process_tool_request("tool", {}, {"type": "object"}, {})
        assert not r2.allowed
        assert r2.error_code == "RATE_LIMIT_EXCEEDED"

    @pytest.mark.asyncio
    async def test_rate_limit_disabled_allows_all(self) -> None:
        config = _make_security_config(
            rate_limits=RateLimitConfig(enabled=False),
            input_validation=ValidationConfig(enabled=False),
            input_sanitization=SanitizationConfig(enabled=False, level="permissive"),
        )
        pipeline = MiddlewarePipeline(config)

        for _ in range(10):
            result = await pipeline.process_tool_request("tool", {}, {"type": "object"}, {})
            assert result.allowed


class TestMiddlewarePipelineAuth:
    """Tests for auth middleware in the pipeline."""

    @pytest.mark.asyncio
    async def test_no_auth_always_passes(self, permissive_config: SecurityConfig) -> None:
        pipeline = MiddlewarePipeline(permissive_config)
        result = await pipeline.process_tool_request("tool", {}, {"type": "object"}, {})
        assert result.allowed

    @pytest.mark.asyncio
    async def test_token_auth_with_correct_token(self) -> None:
        config = _make_security_config(
            auth=AuthConfig(enabled=True, provider="token", token="secret"),
            rate_limits=RateLimitConfig(enabled=False),
            input_validation=ValidationConfig(enabled=False),
            input_sanitization=SanitizationConfig(enabled=False, level="permissive"),
        )
        pipeline = MiddlewarePipeline(config)
        result = await pipeline.process_tool_request(
            "tool", {}, {"type": "object"}, {"token": "secret"}
        )
        assert result.allowed

    @pytest.mark.asyncio
    async def test_token_auth_with_wrong_token(self) -> None:
        config = _make_security_config(
            auth=AuthConfig(enabled=True, provider="token", token="secret"),
            rate_limits=RateLimitConfig(enabled=False),
            input_validation=ValidationConfig(enabled=False),
            input_sanitization=SanitizationConfig(enabled=False, level="permissive"),
        )
        pipeline = MiddlewarePipeline(config)
        result = await pipeline.process_tool_request(
            "tool", {}, {"type": "object"}, {"token": "wrong"}
        )
        assert not result.allowed
        assert result.error_code == "AUTH_ERROR"


class TestProcessResourceRequest:
    """Tests for process_resource_request middleware pipeline."""

    @pytest.mark.asyncio
    async def test_resource_passes_with_no_auth(self) -> None:
        config = _make_security_config(
            rate_limits=RateLimitConfig(enabled=False),
            auth=AuthConfig(enabled=False, provider="none"),
        )
        pipeline = MiddlewarePipeline(config)
        result = await pipeline.process_resource_request("template://test", {})
        assert result.allowed

    @pytest.mark.asyncio
    async def test_resource_blocked_by_auth(self) -> None:
        config = _make_security_config(
            auth=AuthConfig(enabled=True, provider="token", token="secret"),
            rate_limits=RateLimitConfig(enabled=False),
        )
        pipeline = MiddlewarePipeline(config)
        result = await pipeline.process_resource_request(
            "template://test", {"token": "wrong"}
        )
        assert not result.allowed
        assert result.error_code == "AUTH_ERROR"

    @pytest.mark.asyncio
    async def test_resource_passes_auth_with_correct_token(self) -> None:
        config = _make_security_config(
            auth=AuthConfig(enabled=True, provider="token", token="secret"),
            rate_limits=RateLimitConfig(enabled=False),
        )
        pipeline = MiddlewarePipeline(config)
        result = await pipeline.process_resource_request(
            "template://test", {"token": "secret"}
        )
        assert result.allowed

    @pytest.mark.asyncio
    async def test_resource_blocked_by_missing_token(self) -> None:
        config = _make_security_config(
            auth=AuthConfig(enabled=True, provider="token", token="secret"),
            rate_limits=RateLimitConfig(enabled=False),
        )
        pipeline = MiddlewarePipeline(config)
        result = await pipeline.process_resource_request(
            "template://test",
            {},  # no token provided
        )
        assert not result.allowed
        assert result.error_code == "AUTH_ERROR"

    @pytest.mark.asyncio
    async def test_resource_blocked_by_rate_limit(self) -> None:
        config = _make_security_config(
            rate_limits=RateLimitConfig(enabled=True, global_rpm=60, per_tool_rpm=30, burst_size=1),
            auth=AuthConfig(enabled=False, provider="none"),
        )
        pipeline = MiddlewarePipeline(config)

        r1 = await pipeline.process_resource_request("template://test", {})
        assert r1.allowed

        r2 = await pipeline.process_resource_request("template://test", {})
        assert not r2.allowed
        assert r2.error_code == "RATE_LIMIT_EXCEEDED"

    @pytest.mark.asyncio
    async def test_resource_rate_limit_disabled_allows_all(self) -> None:
        config = _make_security_config(
            rate_limits=RateLimitConfig(enabled=False),
            auth=AuthConfig(enabled=False, provider="none"),
        )
        pipeline = MiddlewarePipeline(config)
        for _ in range(10):
            result = await pipeline.process_resource_request("template://test", {})
            assert result.allowed


class TestProcessPromptRequest:
    """Tests for process_prompt_request middleware pipeline."""

    @pytest.mark.asyncio
    async def test_prompt_passes_with_no_auth(self) -> None:
        config = _make_security_config(
            rate_limits=RateLimitConfig(enabled=False),
            auth=AuthConfig(enabled=False, provider="none"),
            input_sanitization=SanitizationConfig(enabled=False, level="permissive"),
        )
        pipeline = MiddlewarePipeline(config)
        result = await pipeline.process_prompt_request("greet", {"name": "Alice"}, {})
        assert result.allowed
        assert result.sanitized_arguments == {"name": "Alice"}

    @pytest.mark.asyncio
    async def test_prompt_blocked_by_auth(self) -> None:
        config = _make_security_config(
            auth=AuthConfig(enabled=True, provider="token", token="secret"),
            rate_limits=RateLimitConfig(enabled=False),
            input_sanitization=SanitizationConfig(enabled=False, level="permissive"),
        )
        pipeline = MiddlewarePipeline(config)
        result = await pipeline.process_prompt_request(
            "greet", {"name": "Alice"}, {"token": "wrong"}
        )
        assert not result.allowed
        assert result.error_code == "AUTH_ERROR"

    @pytest.mark.asyncio
    async def test_prompt_passes_auth_with_correct_token(self) -> None:
        config = _make_security_config(
            auth=AuthConfig(enabled=True, provider="token", token="secret"),
            rate_limits=RateLimitConfig(enabled=False),
            input_sanitization=SanitizationConfig(enabled=False, level="permissive"),
        )
        pipeline = MiddlewarePipeline(config)
        result = await pipeline.process_prompt_request(
            "greet", {"name": "Alice"}, {"token": "secret"}
        )
        assert result.allowed

    @pytest.mark.asyncio
    async def test_prompt_blocked_by_missing_token(self) -> None:
        config = _make_security_config(
            auth=AuthConfig(enabled=True, provider="token", token="secret"),
            rate_limits=RateLimitConfig(enabled=False),
            input_sanitization=SanitizationConfig(enabled=False, level="permissive"),
        )
        pipeline = MiddlewarePipeline(config)
        result = await pipeline.process_prompt_request(
            "greet",
            {"name": "Alice"},
            {},  # no token provided
        )
        assert not result.allowed
        assert result.error_code == "AUTH_ERROR"

    @pytest.mark.asyncio
    async def test_prompt_blocked_by_rate_limit(self) -> None:
        config = _make_security_config(
            rate_limits=RateLimitConfig(enabled=True, global_rpm=60, per_tool_rpm=30, burst_size=1),
            auth=AuthConfig(enabled=False, provider="none"),
            input_sanitization=SanitizationConfig(enabled=False, level="permissive"),
        )
        pipeline = MiddlewarePipeline(config)

        r1 = await pipeline.process_prompt_request("greet", {}, {})
        assert r1.allowed

        r2 = await pipeline.process_prompt_request("greet", {}, {})
        assert not r2.allowed
        assert r2.error_code == "RATE_LIMIT_EXCEEDED"

    @pytest.mark.asyncio
    async def test_prompt_oversized_arguments_blocked(self) -> None:
        config = _make_security_config(
            io_limits=IOLimitConfig(max_request_size=10, max_response_size=5_242_880),
            rate_limits=RateLimitConfig(enabled=False),
            auth=AuthConfig(enabled=False, provider="none"),
            input_sanitization=SanitizationConfig(enabled=False, level="permissive"),
        )
        pipeline = MiddlewarePipeline(config)
        result = await pipeline.process_prompt_request("greet", {"data": "x" * 100}, {})
        assert not result.allowed
        assert result.error_code in ("REQUEST_TOO_LARGE", "IO_LIMIT_EXCEEDED")

    @pytest.mark.asyncio
    async def test_prompt_sanitization_applied(self) -> None:
        config = _make_security_config(
            rate_limits=RateLimitConfig(enabled=False),
            auth=AuthConfig(enabled=False, provider="none"),
            input_sanitization=SanitizationConfig(enabled=True, level="strict"),
        )
        pipeline = MiddlewarePipeline(config)
        result = await pipeline.process_prompt_request("greet", {"cmd": "ls; rm -rf /"}, {})
        assert result.allowed
        assert result.sanitized_arguments is not None
        assert ";" not in result.sanitized_arguments["cmd"]

    @pytest.mark.asyncio
    async def test_prompt_sanitization_disabled_passes_through(self) -> None:
        config = _make_security_config(
            rate_limits=RateLimitConfig(enabled=False),
            auth=AuthConfig(enabled=False, provider="none"),
            input_sanitization=SanitizationConfig(enabled=False, level="permissive"),
        )
        pipeline = MiddlewarePipeline(config)
        result = await pipeline.process_prompt_request("greet", {"cmd": "ls; rm"}, {})
        assert result.allowed
        assert result.sanitized_arguments == {"cmd": "ls; rm"}


class TestSanitizationErrorHandling:
    """Tests that SanitizationError is caught and returned as MiddlewareResult."""

    @pytest.mark.asyncio
    async def test_tool_key_collision_returns_error(self) -> None:
        config = _make_security_config(
            rate_limits=RateLimitConfig(enabled=False),
            auth=AuthConfig(enabled=False, provider="none"),
            input_sanitization=SanitizationConfig(enabled=True, level="strict"),
            input_validation=ValidationConfig(enabled=False),
        )
        pipeline = MiddlewarePipeline(config)
        schema = {"type": "object"}
        result = await pipeline.process_tool_request(
            "tool", {"path../a": "v1", "patha": "v2"}, schema, {}
        )
        assert not result.allowed
        assert result.error_code == "KEY_COLLISION"

    @pytest.mark.asyncio
    async def test_prompt_key_collision_returns_error(self) -> None:
        config = _make_security_config(
            rate_limits=RateLimitConfig(enabled=False),
            auth=AuthConfig(enabled=False, provider="none"),
            input_sanitization=SanitizationConfig(enabled=True, level="strict"),
        )
        pipeline = MiddlewarePipeline(config)
        result = await pipeline.process_prompt_request(
            "greet", {"path../a": "v1", "patha": "v2"}, {}
        )
        assert not result.allowed
        assert result.error_code == "KEY_COLLISION"
