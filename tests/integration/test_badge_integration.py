"""Stdio integration tests for the SOLVE-IT badge tools.

Starts the full server with a copy of ``config/default.toml`` pointing at a
local SOLVE-IT checkout (see ``tests/_solveit_kb.py``) and a temporary badge
output directory. Skipped when the data or ``resvg_py`` is unavailable.
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
import struct
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest

from tests._solveit_kb import solveit_path

from .conftest import _CONFIG_PATH, _STARTUP_TIMEOUT, MCPTestClient

pytest.importorskip("resvg_py")


@pytest.fixture()
async def badge_client(tmp_path: Path) -> AsyncGenerator[tuple[MCPTestClient, Path], None]:
    """Start a server whose config points at local SOLVE-IT data."""
    data = solveit_path()
    if data is None:
        pytest.skip("SOLVE-IT data not available")
    out_dir = tmp_path / "badges"
    text = _CONFIG_PATH.read_text(encoding="utf-8")
    text = re.sub(
        r"^solveit_data_path = .*$",
        lambda _m: f"solveit_data_path = {json.dumps(str(data))}",
        text, count=1, flags=re.MULTILINE,
    )
    text = re.sub(
        r'^output_dir = ""$',
        lambda _m: f"output_dir = {json.dumps(str(out_dir))}",
        text, count=1, flags=re.MULTILINE,
    )
    config = tmp_path / "config.toml"
    config.write_text(text, encoding="utf-8")

    client = MCPTestClient(config)
    await client.start()
    response = await asyncio.wait_for(
        client.send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "badge-test", "version": "1.0"},
            },
        ),
        timeout=_STARTUP_TIMEOUT,
    )
    assert "result" in response, f"initialize failed: {response}"
    await client.send_notification("notifications/initialized")
    yield client, out_dir
    await client.stop()


@pytest.mark.asyncio
class TestBadgeStdio:
    """Badge tools over the MCP protocol."""

    async def test_get_badge_returns_png_image(
        self, badge_client: tuple[MCPTestClient, Path]
    ) -> None:
        client, _ = badge_client
        response = await client.send_request(
            "tools/call",
            {"name": "solveit_get_badge", "arguments": {"item_id": "DFT-1001", "scale": 2}},
        )
        result = response["result"]
        assert result.get("isError") is not True, result
        image, info_block = result["content"]
        assert image["type"] == "image" and image["mimeType"] == "image/png"
        png = base64.b64decode(image["data"])
        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        assert png[37:41] == b"pHYs"
        info = json.loads(info_block["text"])
        assert struct.unpack(">II", png[16:24]) == (info["width_px"], info["height_px"])
        assert info["id"] == "DFT-1001" and info["type"] == "technique"

    async def test_save_badge_writes_file(
        self, badge_client: tuple[MCPTestClient, Path]
    ) -> None:
        client, out_dir = badge_client
        response = await client.send_request(
            "tools/call",
            {"name": "solveit_save_badge", "arguments": {"item_id": "DFW-1001"}},
        )
        result = response["result"]
        assert result.get("isError") is not True, result
        info = json.loads(result["content"][0]["text"])
        path = Path(info["path"])
        assert path == out_dir.resolve() / "DFW-1001.png"
        assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
