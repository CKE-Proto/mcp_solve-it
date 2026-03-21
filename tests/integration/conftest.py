"""Shared fixtures for integration tests."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest

# Path to the config file for subprocess tests
_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "default.toml"

# Timeout for subprocess startup and response (seconds)
_STARTUP_TIMEOUT = 15.0
_RESPONSE_TIMEOUT = 10.0


class MCPTestClient:
    """Async test client that communicates with an MCP server subprocess over stdio.

    Manages a subprocess running python -m mcp_chassis and exposes
    send/receive primitives that follow the JSON-RPC protocol.

    Args:
        config_path: Path to the config TOML file for the server.
    """

    def __init__(self, config_path: Path) -> None:
        """Initialize the client with a config path.

        Args:
            config_path: Path to the server config TOML file.
        """
        self._config_path = config_path
        self._process: asyncio.subprocess.Process | None = None
        self._next_id = 1

    async def start(self) -> None:
        """Start the server subprocess.

        Raises:
            RuntimeError: If the process fails to start.
        """
        self._process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "mcp_chassis",
            "--config",
            str(self._config_path),
            "--log-level",
            "ERROR",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def stop(self) -> None:
        """Terminate the server subprocess gracefully."""
        if self._process is None:
            return
        if self._process.stdin and not self._process.stdin.is_closing():
            self._process.stdin.close()
        try:
            await asyncio.wait_for(self._process.wait(), timeout=5.0)
        except TimeoutError:
            self._process.kill()
            await self._process.wait()

    async def send_request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a JSON-RPC request and return the response.

        Args:
            method: The JSON-RPC method name.
            params: Optional method parameters.

        Returns:
            The parsed JSON-RPC response dict.

        Raises:
            RuntimeError: If no process is running.
            asyncio.TimeoutError: If no response arrives within timeout.
        """
        request_id = self._next_id
        self._next_id += 1
        return await self._send_and_receive(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}},
            request_id,
        )

    async def send_notification(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        """Send a JSON-RPC notification (no response expected).

        Args:
            method: The JSON-RPC method name.
            params: Optional notification parameters.

        Raises:
            RuntimeError: If no process is running.
        """
        if self._process is None or self._process.stdin is None:
            raise RuntimeError("Process not started")
        msg = json.dumps({"jsonrpc": "2.0", "method": method, "params": params or {}})
        self._process.stdin.write((msg + "\n").encode())
        await self._process.stdin.drain()

    async def _send_and_receive(
        self, message: dict[str, Any], expected_id: int
    ) -> dict[str, Any]:
        """Send a message and read the response with the matching ID."""
        if self._process is None or self._process.stdin is None or self._process.stdout is None:
            raise RuntimeError("Process not started")

        line = json.dumps(message) + "\n"
        self._process.stdin.write(line.encode())
        await self._process.stdin.drain()

        return await asyncio.wait_for(
            self._read_response(expected_id),
            timeout=_RESPONSE_TIMEOUT,
        )

    async def _read_response(self, expected_id: int) -> dict[str, Any]:
        """Read stdout lines until we find a response with the expected ID."""
        if self._process is None or self._process.stdout is None:
            raise RuntimeError("Process not started")

        while True:
            raw = await self._process.stdout.readline()
            if not raw:
                raise RuntimeError("Server stdout closed unexpectedly")
            line = raw.decode().strip()
            if not line:
                continue
            try:
                response = json.loads(line)
            except json.JSONDecodeError:
                continue
            if response.get("id") == expected_id:
                return response


@pytest.fixture()
async def mcp_client() -> AsyncGenerator[MCPTestClient, None]:
    """Provide an initialized MCP test client connected to a live server.

    Performs the MCP initialize handshake before yielding and stops
    the subprocess after the test.

    Yields:
        An MCPTestClient ready to send requests.
    """
    client = MCPTestClient(_CONFIG_PATH)
    await client.start()

    response = await asyncio.wait_for(
        client.send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "integration-test", "version": "1.0"},
            },
        ),
        timeout=_STARTUP_TIMEOUT,
    )
    assert "result" in response, f"initialize failed: {response}"

    await client.send_notification("notifications/initialized")

    yield client

    await client.stop()
