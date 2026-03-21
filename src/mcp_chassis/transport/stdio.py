"""Stdio transport implementation for the MCP Chassis server.

Wraps the MCP SDK's stdio_server() with size-bounded stdin reading
to prevent memory exhaustion from oversized messages (D-006).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import anyio
import anyio.lowlevel
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp import types
from mcp.shared.message import SessionMessage

from mcp_chassis.transport.base import TransportBase

if TYPE_CHECKING:
    from mcp_chassis.server import ChassisServer

logger = logging.getLogger(__name__)

# Default maximum bytes per stdin line (1 MB). Prevents memory exhaustion.
_DEFAULT_MAX_LINE_BYTES = 1_048_576


class StdioTransport(TransportBase):
    """Stdio transport using the MCP SDK's stdio machinery.

    Wraps stdin with size-bounded reading per D-006: lines exceeding
    max_line_bytes are dropped with an error logged, protecting the server
    from memory exhaustion via oversized JSON-RPC messages.

    Args:
        max_line_bytes: Maximum allowed bytes for a single stdin line.
    """

    def __init__(self, max_line_bytes: int = _DEFAULT_MAX_LINE_BYTES) -> None:
        """Initialize the StdioTransport.

        Args:
            max_line_bytes: Maximum bytes allowed per stdin line.
        """
        self._max_line_bytes = max_line_bytes
        self._cancel_scope: anyio.CancelScope | None = None

    async def _read_lines_bounded(
        self, reader: object
    ) -> AsyncIterator[bytes]:
        """Read lines from a binary stream, enforcing a per-line byte limit.

        Reads in fixed-size chunks and assembles lines delimited by b'\\n'.
        Lines exceeding max_line_bytes are discarded mid-stream (only the
        bytes up to the next newline are skipped — no unbounded buffering).

        Args:
            reader: Any object with an async ``read(n) -> bytes`` method
                (e.g. ``anyio.wrap_file(sys.stdin.buffer.raw)``).

        Yields:
            Complete lines as bytes, without the trailing newline.
        """
        buf = bytearray()
        oversize = False

        while True:
            chunk = await reader.read(8192)  # type: ignore[attr-defined]
            if not chunk:
                # EOF — flush any remaining partial line.
                if buf and not oversize:
                    yield bytes(buf)
                break

            pos = 0
            while pos < len(chunk):
                nl = chunk.find(b"\n", pos)
                if nl == -1:
                    # No newline in remaining chunk.
                    if not oversize:
                        buf.extend(chunk[pos:])
                        if len(buf) > self._max_line_bytes:
                            logger.error(
                                "Oversized stdin message dropped: %d bytes (limit %d)",
                                len(buf),
                                self._max_line_bytes,
                            )
                            buf.clear()
                            oversize = True
                    break

                # Found a newline at position nl.
                segment = chunk[pos:nl]
                pos = nl + 1  # advance past the newline

                if oversize:
                    # This newline ends the oversized line. Reset state.
                    oversize = False
                    buf.clear()
                    continue

                buf.extend(segment)
                if len(buf) > self._max_line_bytes:
                    logger.error(
                        "Oversized stdin message dropped: %d bytes (limit %d)",
                        len(buf),
                        self._max_line_bytes,
                    )
                    buf.clear()
                    # oversize stays False because the line is already complete
                    # (we found its newline) — just skip it.
                    continue

                yield bytes(buf)
                buf.clear()

    async def start(self, server: ChassisServer) -> None:
        """Run the server over stdio.

        Reads JSON-RPC messages from stdin (with size bounding) and writes
        responses to stdout. Runs until stdin is closed or shutdown() is called.

        Args:
            server: The ChassisServer instance to dispatch requests to.
        """
        import sys

        # Stdout stays text-mode for JSON-RPC response writing.
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        stdout_wrapped = anyio.wrap_file(sys.stdout)

        # Stdin: use the raw FileIO (sys.stdin.buffer.raw) for chunk-based
        # bounded reading. We bypass both TextIOWrapper (which buffers entire
        # lines) and BufferedReader (which tries to fill its buffer on
        # non-interactive streams like pipes). FileIO.read(n) returns as soon
        # as any data is available, up to n bytes. See AUDIT.md item #4.
        stdin_raw = anyio.wrap_file(sys.stdin.buffer.raw)  # type: ignore[union-attr]

        read_stream_writer: MemoryObjectSendStream[SessionMessage | Exception]
        read_stream: MemoryObjectReceiveStream[SessionMessage | Exception]
        write_stream: MemoryObjectSendStream[SessionMessage]
        write_stream_reader: MemoryObjectReceiveStream[SessionMessage]

        read_stream_writer, read_stream = anyio.create_memory_object_stream(0)
        write_stream, write_stream_reader = anyio.create_memory_object_stream(0)

        async def stdin_reader() -> None:
            """Read lines from stdin with streaming size bound."""
            try:
                async with read_stream_writer:
                    async for line_bytes in self._read_lines_bounded(stdin_raw):
                        try:
                            message = types.JSONRPCMessage.model_validate_json(
                                line_bytes
                            )
                        except Exception as exc:
                            await read_stream_writer.send(exc)
                            continue
                        session_message = SessionMessage(message)
                        await read_stream_writer.send(session_message)
            except anyio.ClosedResourceError:
                await anyio.lowlevel.checkpoint()
            except (ValueError, OSError):
                logger.debug("Stdin closed, reader exiting")

        async def stdout_writer() -> None:
            """Write JSON-RPC responses to stdout."""
            try:
                async with write_stream_reader:
                    async for session_message in write_stream_reader:
                        json_str = session_message.message.model_dump_json(
                            by_alias=True, exclude_unset=True
                        )
                        await stdout_wrapped.write(json_str + "\n")
                        await stdout_wrapped.flush()
            except anyio.ClosedResourceError:
                await anyio.lowlevel.checkpoint()

        logger.info("Starting stdio transport (max_line_bytes=%d)", self._max_line_bytes)
        async with anyio.create_task_group() as tg:
            self._cancel_scope = tg.cancel_scope
            tg.start_soon(stdin_reader)
            tg.start_soon(stdout_writer)
            await server.run_on_streams(read_stream, write_stream)

    async def shutdown(self) -> None:
        """Signal the stdio transport to shut down.

        Cancels the transport's task group, causing the stdin reader and
        stdout writer to exit cleanly.
        """
        logger.info("Stdio transport shutdown requested")
        if self._cancel_scope is not None:
            self._cancel_scope.cancel()
