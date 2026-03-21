"""Abstract base class for MCP transports.

Transport implementations handle the low-level I/O and connect the MCP
SDK's session handling to our ChassisServer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_chassis.server import ChassisServer


class TransportBase(ABC):
    """Abstract base for MCP transport implementations.

    A transport is responsible for:
    - Accepting incoming connections (or stdin for stdio).
    - Providing read/write streams to the MCP SDK's Server.run().
    - Handling graceful shutdown.
    """

    @abstractmethod
    async def start(self, server: ChassisServer) -> None:
        """Start the transport and begin serving requests.

        This method runs until shutdown is requested. It should set up
        the underlying I/O mechanism and call server.run_on_streams().

        Args:
            server: The ChassisServer instance to serve requests for.
        """

    @abstractmethod
    async def shutdown(self) -> None:
        """Gracefully shut down the transport.

        Should signal the transport to stop accepting new connections
        and allow in-progress requests to complete.
        """
