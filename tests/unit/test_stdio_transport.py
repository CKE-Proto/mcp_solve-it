"""Unit tests for StdioTransport streaming-bounded stdin reader."""

from __future__ import annotations

import pytest

from mcp_chassis.transport.stdio import StdioTransport


class FakeAsyncReader:
    """Simulates an async binary file reader that yields chunks.

    Args:
        chunks: List of bytes objects to yield in order.
    """

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks
        self._index = 0

    async def read(self, n: int) -> bytes:
        """Read the next pre-loaded chunk (ignores n).

        Args:
            n: Requested read size (ignored — returns the next chunk as-is).

        Returns:
            The next chunk, or b"" at EOF.
        """
        if self._index >= len(self._chunks):
            return b""
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk


async def _collect_lines(transport: StdioTransport, reader: FakeAsyncReader) -> list[bytes]:
    """Collect all lines yielded by the bounded reader.

    Args:
        transport: StdioTransport instance with configured max_line_bytes.
        reader: Fake async reader providing chunk data.

    Returns:
        List of complete line byte strings.
    """
    lines: list[bytes] = []
    async for line in transport._read_lines_bounded(reader):
        lines.append(line)
    return lines


class TestReadLinesBounded:
    """Tests for StdioTransport._read_lines_bounded()."""

    async def test_normal_line_within_limits(self) -> None:
        """A single line under the limit is yielded intact."""
        transport = StdioTransport(max_line_bytes=1024)
        message = b'{"jsonrpc":"2.0","id":1,"method":"test"}\n'
        reader = FakeAsyncReader([message])

        lines = await _collect_lines(transport, reader)

        assert lines == [b'{"jsonrpc":"2.0","id":1,"method":"test"}']

    async def test_line_exactly_at_limit(self) -> None:
        """A line whose byte length equals max_line_bytes is accepted."""
        transport = StdioTransport(max_line_bytes=20)
        # 19 content bytes + newline = line content is exactly 19 bytes
        # but the limit applies to the content (without newline), so make content = 20 bytes
        content = b"a" * 20
        reader = FakeAsyncReader([content + b"\n"])

        lines = await _collect_lines(transport, reader)

        assert lines == [content]

    async def test_oversized_line_discarded(self) -> None:
        """A line exceeding the limit is discarded and logged."""
        transport = StdioTransport(max_line_bytes=10)
        # 20 bytes of content + newline — exceeds 10 byte limit.
        reader = FakeAsyncReader([b"a" * 20 + b"\n"])

        lines = await _collect_lines(transport, reader)

        assert lines == []

    async def test_oversized_line_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """Discarding an oversized line emits an ERROR log."""
        transport = StdioTransport(max_line_bytes=10)
        reader = FakeAsyncReader([b"a" * 20 + b"\n"])

        with caplog.at_level("ERROR", logger="mcp_chassis.transport.stdio"):
            await _collect_lines(transport, reader)

        assert any("Oversized stdin message dropped" in r.message for r in caplog.records)

    async def test_oversized_then_normal(self) -> None:
        """After an oversized line is discarded, the next normal line is processed."""
        transport = StdioTransport(max_line_bytes=10)
        data = b"a" * 20 + b"\n" + b"ok\n"
        reader = FakeAsyncReader([data])

        lines = await _collect_lines(transport, reader)

        assert lines == [b"ok"]

    async def test_oversized_spanning_multiple_chunks(self) -> None:
        """An oversized line spread across multiple chunks is discarded."""
        transport = StdioTransport(max_line_bytes=10)
        # First chunk: 8 bytes (under limit). Second: 8 more (now 16, over limit).
        # Third: newline ends the oversized line, then a normal line.
        reader = FakeAsyncReader([b"a" * 8, b"a" * 8, b"\nok\n"])

        lines = await _collect_lines(transport, reader)

        assert lines == [b"ok"]

    async def test_multiple_lines_in_single_chunk(self) -> None:
        """Multiple newline-terminated lines in one chunk are all yielded."""
        transport = StdioTransport(max_line_bytes=1024)
        reader = FakeAsyncReader([b"line1\nline2\nline3\n"])

        lines = await _collect_lines(transport, reader)

        assert lines == [b"line1", b"line2", b"line3"]

    async def test_line_split_across_chunks(self) -> None:
        """A line split across two chunks is reassembled correctly."""
        transport = StdioTransport(max_line_bytes=1024)
        reader = FakeAsyncReader([b"hel", b"lo\n"])

        lines = await _collect_lines(transport, reader)

        assert lines == [b"hello"]

    async def test_empty_input_eof(self) -> None:
        """EOF immediately yields no lines."""
        transport = StdioTransport(max_line_bytes=1024)
        reader = FakeAsyncReader([])

        lines = await _collect_lines(transport, reader)

        assert lines == []

    async def test_partial_final_line_without_newline(self) -> None:
        """A final line without a trailing newline is still processed."""
        transport = StdioTransport(max_line_bytes=1024)
        reader = FakeAsyncReader([b"no-newline"])

        lines = await _collect_lines(transport, reader)

        assert lines == [b"no-newline"]

    async def test_empty_lines_yielded(self) -> None:
        """Empty lines (consecutive newlines) are yielded as empty bytes."""
        transport = StdioTransport(max_line_bytes=1024)
        reader = FakeAsyncReader([b"\n\n"])

        lines = await _collect_lines(transport, reader)

        assert lines == [b"", b""]

    async def test_oversize_mid_chunk_resets_at_newline(self) -> None:
        """Oversize flag resets at the newline boundary within the same chunk."""
        transport = StdioTransport(max_line_bytes=5)
        # "toolong" is 7 bytes (over 5 limit), then newline, then "ok" (under limit)
        reader = FakeAsyncReader([b"toolong\nok\n"])

        lines = await _collect_lines(transport, reader)

        assert lines == [b"ok"]

    async def test_multibyte_utf8_within_chunk(self) -> None:
        """Multi-byte UTF-8 characters within a single chunk are preserved."""
        transport = StdioTransport(max_line_bytes=1024)
        # "hello" in Japanese: こんにちは (15 bytes in UTF-8)
        content = "こんにちは".encode()
        reader = FakeAsyncReader([content + b"\n"])

        lines = await _collect_lines(transport, reader)

        assert lines == [content]

    async def test_multibyte_utf8_split_across_chunks(self) -> None:
        """A multi-byte UTF-8 character split at a chunk boundary is handled."""
        transport = StdioTransport(max_line_bytes=1024)
        # "é" is b'\xc3\xa9' in UTF-8 (2 bytes). Split it across chunks.
        reader = FakeAsyncReader([b"caf\xc3", b"\xa9\n"])

        lines = await _collect_lines(transport, reader)

        # _read_lines_bounded yields raw bytes; UTF-8 integrity is preserved
        assert lines == ["café".encode()]

    async def test_invalid_utf8_does_not_crash(self) -> None:
        """Invalid UTF-8 bytes are yielded as-is (decoder handles them later)."""
        transport = StdioTransport(max_line_bytes=1024)
        # 0xFF 0xFE is not valid UTF-8
        reader = FakeAsyncReader([b"\xff\xfe hello\n"])

        lines = await _collect_lines(transport, reader)

        # The raw bytes are yielded; the JSON parser will reject them downstream
        assert lines == [b"\xff\xfe hello"]

    async def test_decoder_state_does_not_leak_between_lines(self) -> None:
        """Each line is independent — no decoder state leaks across lines."""
        transport = StdioTransport(max_line_bytes=1024)
        # Line 1: complete UTF-8. Line 2: also complete UTF-8.
        line1 = "café".encode() + b"\n"
        line2 = "naïve".encode() + b"\n"
        reader = FakeAsyncReader([line1 + line2])

        lines = await _collect_lines(transport, reader)

        assert lines == ["café".encode(), "naïve".encode()]
