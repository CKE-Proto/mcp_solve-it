"""Health check tool for the MCP Chassis server.

Registers a built-in '__health_check' tool that reports server metadata,
loaded extensions, and configuration summary (without secrets).
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import TYPE_CHECKING, Any

import mcp_chassis

if TYPE_CHECKING:
    from mcp_chassis.context import HandlerContext
    from mcp_chassis.server import ChassisServer

logger = logging.getLogger(__name__)

_HEALTH_TOOL_NAME = "__health_check"
_HEALTH_TOOL_DESCRIPTION = (
    "Returns server health status, loaded extensions, and configuration summary."
)
_HEALTH_TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "required": [],
}


def register_health_check(server: ChassisServer) -> None:
    """Register the built-in health check tool with the server.

    The health check tool is registered as '__health_check' and returns
    server metadata, loaded tool/resource/prompt names, and a configuration
    summary (without secrets like auth tokens).

    Args:
        server: The ChassisServer to register the health check on.
    """
    start_time = time.monotonic()

    async def _handle_health_check(
        arguments: dict[str, Any], context: HandlerContext
    ) -> str:
        """Handle the health check tool call.

        Args:
            arguments: Ignored (health check takes no arguments).
            context: Handler context providing server config.

        Returns:
            JSON string with health status report.
        """
        uptime = time.monotonic() - start_time
        config = context.server_config
        tool_names = list(server.list_tool_names())
        resource_uris = list(server.list_resource_uris())
        prompt_names = list(server.list_prompt_names())

        report: dict[str, Any] = {
            "server_name": config.server.name,
            "server_version": config.server.version,
            "chassis_version": mcp_chassis.__version__,
            "python_version": (
                f"{sys.version_info.major}.{sys.version_info.minor}"
                f".{sys.version_info.micro}"
            ),
            "uptime_seconds": round(uptime, 2),
            "tools_loaded": tool_names,
            "resources_loaded": resource_uris,
            "prompts_loaded": prompt_names,
            "security_profile": config.security.profile,
        }

        if config.diagnostics.include_config_summary:
            report["config_summary"] = {
                "transport": config.server.transport,
                "rate_limiting": config.security.rate_limits.enabled,
                "auth_enabled": config.security.auth.enabled,
                "log_level": config.server.log_level,
            }

        return json.dumps(report, indent=2)

    server.register_tool(
        name=_HEALTH_TOOL_NAME,
        description=_HEALTH_TOOL_DESCRIPTION,
        input_schema=_HEALTH_TOOL_SCHEMA,
        handler=_handle_health_check,
        allow_overwrite=True,
    )
    logger.debug("Registered built-in health check tool '%s'", _HEALTH_TOOL_NAME)
