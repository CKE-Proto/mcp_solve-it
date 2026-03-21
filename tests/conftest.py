"""Shared test fixtures for mcp_chassis tests."""

from __future__ import annotations

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
from mcp_chassis.server import ChassisServer


def make_test_config(
    *,
    name: str = "test-server",
    version: str = "0.1.0",
    health_enabled: bool = False,
    auto_discover: bool = False,
    rate_limiting: bool = False,
    validation: bool = False,
    sanitization_enabled: bool = False,
    sanitization_level: str = "permissive",
    io_request_limit: int = 1_048_576,
    io_response_limit: int = 5_242_880,
    include_config_summary: bool = False,
    init_module: str = "",
    app: dict[str, Any] | None = None,
) -> ServerConfig:
    """Build a ServerConfig suitable for unit testing.

    Args:
        name: Server display name.
        version: Server version string.
        health_enabled: Whether to register the health check tool.
        auto_discover: Whether to run extension auto-discovery.
        rate_limiting: Whether to enable rate limiting.
        validation: Whether to enable input validation.
        sanitization_enabled: Whether to enable input sanitization.
        sanitization_level: Sanitization level string.
        io_request_limit: Maximum request size in bytes.
        io_response_limit: Maximum response size in bytes.
        include_config_summary: Whether health check includes config summary.
        init_module: Optional init hook module name.
        app: Fork-specific config dict.

    Returns:
        A minimal ServerConfig for testing.
    """
    return ServerConfig(
        server=ServerSettings(name=name, version=version),
        security=SecurityConfig(
            rate_limits=RateLimitConfig(enabled=rate_limiting),
            io_limits=IOLimitConfig(
                max_request_size=io_request_limit,
                max_response_size=io_response_limit,
            ),
            input_validation=ValidationConfig(enabled=validation),
            input_sanitization=SanitizationConfig(
                enabled=sanitization_enabled,
                level=sanitization_level,
            ),
            auth=AuthConfig(enabled=False, provider="none"),
        ),
        extensions=ExtensionSettings(
            auto_discover=auto_discover,
            init_module=init_module,
        ),
        diagnostics=DiagnosticSettings(
            health_check_enabled=health_enabled,
            include_config_summary=include_config_summary,
        ),
        app=app or {},
    )


@pytest.fixture()
def test_config() -> ServerConfig:
    """Return a minimal ServerConfig with no health check or discovery.

    Returns:
        ServerConfig for testing.
    """
    return make_test_config()


@pytest.fixture()
def create_test_server() -> ChassisServer:
    """Return a ChassisServer with minimal test configuration.

    Returns:
        ChassisServer configured for testing.
    """
    return ChassisServer(make_test_config())
