"""Stubs for future HTTP transports.

These classes document the planned interfaces for SSE and Streamable HTTP
transports. They raise NotImplementedError if instantiated.

See MIGRATION_NOTES.md for implementation guidance when HTTP transport
is added in a future version.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp_chassis.transport.base import TransportBase

if TYPE_CHECKING:
    from mcp_chassis.server import ChassisServer


class SSETransport(TransportBase):
    """Stub for the future SSE (Server-Sent Events) transport.

    When implemented, this transport will:
    - Serve GET /sse for server-to-client events.
    - Accept POST /messages/ for client-to-server messages.
    - Require DNS rebinding protection on localhost.
    - Require per-session rate limiting.
    """

    async def start(self, server: ChassisServer) -> None:
        """Not implemented.

        Args:
            server: Unused.

        Raises:
            NotImplementedError: Always raised.
        """
        raise NotImplementedError(
            "SSE transport is not yet implemented. "
            "See MIGRATION_NOTES.md for planned HTTP transport support."
        )

    async def shutdown(self) -> None:
        """Not implemented.

        Raises:
            NotImplementedError: Always raised.
        """
        raise NotImplementedError(
            "SSE transport is not yet implemented. "
            "See MIGRATION_NOTES.md for planned HTTP transport support."
        )


class StreamableHTTPTransport(TransportBase):
    """Stub for the future Streamable HTTP transport.

    When implemented, this transport will:
    - Accept POST /mcp for bidirectional JSON-RPC communication.
    - Support optional SSE streaming in responses.
    - Require DNS rebinding protection on localhost.
    - Integrate with MCP SDK's StreamableHTTP session manager.
    """

    async def start(self, server: ChassisServer) -> None:
        """Not implemented.

        Args:
            server: Unused.

        Raises:
            NotImplementedError: Always raised.
        """
        raise NotImplementedError(
            "Streamable HTTP transport is not yet implemented. "
            "See MIGRATION_NOTES.md for planned HTTP transport support."
        )

    async def shutdown(self) -> None:
        """Not implemented.

        Raises:
            NotImplementedError: Always raised.
        """
        raise NotImplementedError(
            "Streamable HTTP transport is not yet implemented. "
            "See MIGRATION_NOTES.md for planned HTTP transport support."
        )
