"""Tests for the SOLVE-IT badge tools and their config."""

from __future__ import annotations

import base64
import json
import os
import stat
import struct
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from mcp import types

from mcp_chassis.extensions.badges.guidance import usage_guidance
from mcp_chassis.extensions.solveit_init import (
    BadgesConfig,
    SolveItAppConfig,
    _apply_env_overrides,
)
from mcp_chassis.extensions.tools import badge_tools
from mcp_chassis.server import ChassisServer
from tests._solveit_kb import load_kb
from tests.conftest import make_test_config

_LONG = (
    "Do not generate hypotheses that are overly narrow and may increase the risk of "
    "over-specificity or confirmation bias. For instance, refer to a class (wiping tool, "
    "Trojan horse program) rather than a member of class (e.g., Eraser.exe, "
    "Backdoor.exe) to avoid narrowly focusing on a specific detail"
)


class FakeKB:
    """Minimal KB with one item of each type."""

    _items = {
        "DFT-1001": {"id": "DFT-1001", "name": "Triage devices or media"},
        "DFW-1001": {"id": "DFW-1001", "name": "Excluding a device that contains data"},
        "DFM-1307": {"id": "DFM-1307", "name": _LONG},
    }

    _objectives = [
        {"id": "DFO-1015", "name": "Prepare for a digital investigation"},
        {"name": "No id objective"},
    ]

    def list_objectives(self) -> list[dict[str, Any]]:
        return [o.copy() for o in self._objectives]

    def get_technique(self, item_id: str) -> dict[str, Any] | None:
        return self._items.get(item_id) if item_id.startswith("DFT-") else None

    def get_weakness(self, item_id: str) -> dict[str, Any] | None:
        return self._items.get(item_id) if item_id.startswith("DFW-") else None

    def get_mitigation(self, item_id: str) -> dict[str, Any] | None:
        return self._items.get(item_id) if item_id.startswith("DFM-") else None


def _server(
    badges: dict[str, Any] | None = None,
    kb: Any = None,
    response_limit: int = 5_242_880,
) -> ChassisServer:
    """Build a real ChassisServer with the badge tools registered."""
    config = make_test_config(io_response_limit=response_limit)
    config = replace(config, security=replace(config.security, detailed_errors=True))
    server = ChassisServer(config)
    server._kb = kb if kb is not None else FakeKB()  # type: ignore[attr-defined]
    server._app_config = SolveItAppConfig.from_raw(  # type: ignore[attr-defined]
        {"badges": badges or {}}
    )
    badge_tools.register(server)
    return server


def _png_size(data: bytes) -> tuple[int, int]:
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def _text(result: types.CallToolResult, index: int = 0) -> str:
    block = result.content[index]
    assert isinstance(block, types.TextContent)
    return block.text


@pytest.fixture()
def out_dir(tmp_path: Path) -> Path:
    return tmp_path / "badges"


class TestConfig:
    """Tests for BadgesConfig and its env override."""

    def test_defaults(self) -> None:
        cfg = SolveItAppConfig.from_raw({}).badges
        assert cfg == BadgesConfig(enabled=True, output_dir="", enable_save=True, max_scale=8)

    def test_from_raw(self) -> None:
        cfg = SolveItAppConfig.from_raw(
            {"badges": {"output_dir": "/x", "enable_save": False, "max_scale": 4}}
        ).badges
        assert cfg.output_dir == "/x" and not cfg.enable_save and cfg.max_scale == 4

    def test_invalid_max_scale_falls_back(self, caplog: Any) -> None:
        cfg = BadgesConfig.from_raw({"max_scale": 16})
        assert cfg.max_scale == 8
        assert "max_scale" in caplog.text

    def test_unknown_key_warns(self, caplog: Any) -> None:
        BadgesConfig.from_raw({"outptu_dir": "/x"})
        assert "outptu_dir" in caplog.text

    def test_env_override_output_dir(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("MCP_APP_BADGES_OUTPUT_DIR", "/env/badges")
        raw: dict[str, Any] = {"badges": {"output_dir": "/toml", "max_scale": 4}}
        _apply_env_overrides(raw)
        cfg = SolveItAppConfig.from_raw(raw).badges
        assert cfg.output_dir == "/env/badges" and cfg.max_scale == 4

    def test_env_override_creates_section(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("MCP_APP_BADGES_OUTPUT_DIR", "/env/badges")
        raw: dict[str, Any] = {}
        _apply_env_overrides(raw)
        assert raw["badges"] == {"output_dir": "/env/badges"}


class TestRegistration:
    """Tests for config-gated registration."""

    def test_both_tools_registered(self) -> None:
        names = _server().list_tool_names()
        assert "solveit_get_badge" in names and "solveit_save_badge" in names

    def test_enable_save_false(self) -> None:
        names = _server({"enable_save": False}).list_tool_names()
        assert "solveit_get_badge" in names and "solveit_save_badge" not in names

    def test_disabled(self) -> None:
        names = _server({"enabled": False}).list_tool_names()
        assert "solveit_get_badge" not in names and "solveit_save_badge" not in names

    def test_no_kb(self) -> None:
        server = ChassisServer(make_test_config())
        server._kb = None  # type: ignore[attr-defined]
        badge_tools.register(server)
        assert "solveit_get_badge" not in server.list_tool_names()

    def test_scale_schema(self) -> None:
        schema = _server()._tools["solveit_get_badge"]["input_schema"]
        assert schema["properties"]["scale"] == {
            "type": "integer",
            "enum": [2, 4, 8],
            "description": schema["properties"]["scale"]["description"],
        }
        assert schema["required"] == ["item_id"]

    def test_scale_schema_respects_max_scale(self) -> None:
        schema = _server({"max_scale": 4})._tools["solveit_get_badge"]["input_schema"]
        assert schema["properties"]["scale"]["enum"] == [2, 4]


class TestGetBadge:
    """Tests for solveit_get_badge."""

    @pytest.mark.asyncio
    async def test_png_image_content(self) -> None:
        pytest.importorskip("resvg_py")
        result = await _server()._dispatch_tool("solveit_get_badge", {"item_id": "DFT-1001"})
        assert not result.isError, result.content
        image = result.content[0]
        assert isinstance(image, types.ImageContent) and image.mimeType == "image/png"
        png = base64.b64decode(image.data)
        info = json.loads(_text(result, 1))
        assert _png_size(png) == (info["width_px"], info["height_px"]) == (1773, 661)
        assert info["id"] == "DFT-1001" and info["type"] == "technique"
        assert info["variant"] == "small" and info["scale"] == 4 and info["dpi"] == 288

    @pytest.mark.asyncio
    async def test_svg_text_content(self) -> None:
        result = await _server()._dispatch_tool(
            "solveit_get_badge", {"item_id": "DFW-1001", "format": "svg", "size": "wide"}
        )
        assert not result.isError
        svg = _text(result, 0)
        assert svg.startswith("<svg ") and "SOLVE-IT WEAKNESS" in svg
        info = json.loads(_text(result, 1))
        assert info["variant"] == "wide" and info["format"] == "svg" and "scale" not in info

    @pytest.mark.asyncio
    @pytest.mark.parametrize("raw_id", ["  dft-1001 ", "DFT-1001", "Dft-1001"])
    async def test_id_normalised(self, raw_id: str) -> None:
        result = await _server()._dispatch_tool(
            "solveit_get_badge", {"item_id": raw_id, "format": "svg"}
        )
        assert not result.isError
        assert json.loads(_text(result, 1))["id"] == "DFT-1001"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("raw_id", ["DFT-9999", "DFX-1001", "1001", "", "   "])
    async def test_unknown_id(self, raw_id: str) -> None:
        result = await _server()._dispatch_tool(
            "solveit_get_badge", {"item_id": raw_id, "format": "svg"}
        )
        assert result.isError
        assert "BADGE_" in _text(result)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "args",
        [
            {"size": "huge"},
            {"scale": 3},
            {"scale": True},
            {"scale": "4"},
            {"format": "jpeg"},
        ],
    )
    async def test_invalid_options(self, args: dict[str, Any]) -> None:
        result = await _server()._dispatch_tool(
            "solveit_get_badge", {"item_id": "DFT-1001", **args}
        )
        assert result.isError
        assert "BADGE_INVALID_ARGUMENT" in _text(result)

    @pytest.mark.asyncio
    async def test_scale_above_max_rejected(self) -> None:
        result = await _server({"max_scale": 4})._dispatch_tool(
            "solveit_get_badge", {"item_id": "DFT-1001", "scale": 8}
        )
        assert result.isError

    @pytest.mark.asyncio
    async def test_scale_8_longest_name_under_strict_cap(self) -> None:
        pytest.importorskip("resvg_py")
        # 5 MB is the strict profile's max_response_size.
        server = _server(response_limit=5_242_880)
        result = await server._dispatch_tool(
            "solveit_get_badge", {"item_id": "DFM-1307", "scale": 8}
        )
        assert not result.isError, result.content
        image = result.content[0]
        assert isinstance(image, types.ImageContent)
        assert len(image.data) < 5_242_880
        info = json.loads(_text(result, 1))
        assert _png_size(base64.b64decode(image.data)) == (info["width_px"], info["height_px"])

    @pytest.mark.asyncio
    async def test_size_limit_applies_to_image(self) -> None:
        pytest.importorskip("resvg_py")
        server = _server(response_limit=1000)
        result = await server._dispatch_tool("solveit_get_badge", {"item_id": "DFT-1001"})
        assert result.isError
        assert "RESPONSE_TOO_LARGE" in _text(result)

    @pytest.mark.asyncio
    async def test_missing_extra(self, monkeypatch: Any) -> None:
        from mcp_chassis.extensions.badges import render

        def no_resvg() -> Any:
            raise render.BadgeExtraMissingError("PNG badges need the 'badges' extra")

        monkeypatch.setattr(render, "_resvg", no_resvg)
        server = _server()
        png = await server._dispatch_tool("solveit_get_badge", {"item_id": "DFT-1001"})
        assert png.isError and "BADGE_EXTRA_NOT_INSTALLED" in _text(png)
        assert "badges" in _text(png).split(":", 1)[1]
        svg = await server._dispatch_tool(
            "solveit_get_badge", {"item_id": "DFT-1001", "format": "svg"}
        )
        assert not svg.isError


class TestSaveBadge:
    """Tests for solveit_save_badge and its path safety."""

    @pytest.mark.asyncio
    async def test_default_filename(self, out_dir: Path) -> None:
        pytest.importorskip("resvg_py")
        server = _server({"output_dir": str(out_dir)})
        result = await server._dispatch_tool(
            "solveit_save_badge", {"item_id": "dft-1001", "scale": 2}
        )
        assert not result.isError, result.content
        info = json.loads(_text(result))
        path = Path(info["path"])
        assert path == out_dir.resolve() / "DFT-1001.png"
        assert path.is_absolute()
        assert _png_size(path.read_bytes()) == (886, 331)
        assert info["bytes"] == path.stat().st_size
        assert stat.S_IMODE(out_dir.stat().st_mode) == 0o700

    @pytest.mark.asyncio
    async def test_custom_filename_gets_extension(self, out_dir: Path) -> None:
        server = _server({"output_dir": str(out_dir)})
        result = await server._dispatch_tool(
            "solveit_save_badge", {"item_id": "DFW-1001", "format": "svg", "filename": "slide_3"}
        )
        assert not result.isError
        path = Path(json.loads(_text(result))["path"])
        assert path.name == "slide_3.svg"
        assert path.read_text(encoding="utf-8").startswith("<svg ")

    @pytest.mark.asyncio
    async def test_default_dir_is_tempdir(self, monkeypatch: Any, tmp_path: Path) -> None:
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
        server = _server()
        result = await server._dispatch_tool(
            "solveit_save_badge", {"item_id": "DFT-1001", "format": "svg"}
        )
        assert not result.isError
        path = Path(json.loads(_text(result))["path"])
        assert path.parent == (tmp_path / "solveit-badges").resolve()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "filename",
        [
            "../evil.svg",
            "..",
            ".hidden.svg",
            "a/b.svg",
            "/etc/passwd",
            "..\\evil.svg",
            "sub/../x.svg",
            "x" * 70,
            "name with space.svg",
            "na\x00me.svg",
            "~root.svg",
            "café.svg",
        ],
    )
    async def test_rejects_unsafe_filenames(self, out_dir: Path, filename: str) -> None:
        server = _server({"output_dir": str(out_dir)})
        result = await server._dispatch_tool(
            "solveit_save_badge", {"item_id": "DFT-1001", "format": "svg", "filename": filename}
        )
        assert result.isError, filename
        assert "BADGE_" in _text(result)
        assert not (out_dir.parent / "evil.svg").exists()
        written = list(out_dir.iterdir()) if out_dir.exists() else []
        assert written == []

    @pytest.mark.asyncio
    async def test_rejects_symlinked_output_dir(self, tmp_path: Path) -> None:
        real = tmp_path / "real"
        real.mkdir()
        link = tmp_path / "link"
        link.symlink_to(real)
        server = _server({"output_dir": str(link)})
        result = await server._dispatch_tool(
            "solveit_save_badge", {"item_id": "DFT-1001", "format": "svg"}
        )
        assert result.isError and "symlink" in _text(result)
        assert list(real.iterdir()) == []

    @pytest.mark.asyncio
    async def test_rejects_symlinked_target(self, out_dir: Path, tmp_path: Path) -> None:
        out_dir.mkdir(mode=0o700)
        victim = tmp_path / "victim.txt"
        victim.write_text("keep")
        (out_dir / "DFT-1001.svg").symlink_to(victim)
        server = _server({"output_dir": str(out_dir)})
        result = await server._dispatch_tool(
            "solveit_save_badge", {"item_id": "DFT-1001", "format": "svg"}
        )
        assert result.isError and "symlink" in _text(result)
        assert victim.read_text() == "keep"

    @pytest.mark.asyncio
    async def test_rejects_file_as_output_dir(self, tmp_path: Path) -> None:
        not_dir = tmp_path / "file"
        not_dir.write_text("x")
        server = _server({"output_dir": str(not_dir)})
        result = await server._dispatch_tool(
            "solveit_save_badge", {"item_id": "DFT-1001", "format": "svg"}
        )
        assert result.isError

    @pytest.mark.skipif(not hasattr(os, "getuid"), reason="POSIX only")
    @pytest.mark.asyncio
    async def test_rejects_dir_owned_by_other_user(self, out_dir: Path, monkeypatch: Any) -> None:
        out_dir.mkdir()
        real_uid = os.getuid()
        monkeypatch.setattr(os, "getuid", lambda: real_uid + 1)
        server = _server({"output_dir": str(out_dir)})
        result = await server._dispatch_tool(
            "solveit_save_badge", {"item_id": "DFT-1001", "format": "svg"}
        )
        assert result.isError and "another user" in _text(result)

    @pytest.mark.asyncio
    async def test_save_unavailable_when_disabled(self, out_dir: Path) -> None:
        server = _server({"output_dir": str(out_dir), "enable_save": False})
        result = await server._dispatch_tool(
            "solveit_save_badge", {"item_id": "DFT-1001", "format": "svg"}
        )
        assert result.isError and "TOOL_NOT_FOUND" in _text(result)
        assert not out_dir.exists()


class TestRealKB:
    """Badge tools against the real SOLVE-IT data, when available."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("item_id", ["DFT-1001", "DFW-1001", "DFM-1001", "DFO-1015"])
    async def test_real_items(self, item_id: str) -> None:
        pytest.importorskip("resvg_py")
        kb = load_kb()
        if kb is None:
            pytest.skip("SOLVE-IT data not available")
        result = await _server(kb=kb)._dispatch_tool(
            "solveit_get_badge", {"item_id": item_id, "scale": 2}
        )
        assert not result.isError, result.content
        info = json.loads(_text(result, 1))
        assert info["id"] == item_id and info["name"]


class TestSaveOverwrite:
    """solveit_save_badge does not clobber existing files by default."""

    async def test_existing_file_with_other_content_is_kept(self, out_dir: Path) -> None:
        server = _server({"output_dir": str(out_dir)})
        out_dir.mkdir(parents=True, exist_ok=True)
        existing = out_dir / "logo.svg"
        existing.write_text("mine")
        result = await server._dispatch_tool(
            "solveit_save_badge", {"item_id": "DFT-1001", "format": "svg", "filename": "logo"}
        )
        assert result.isError
        assert existing.read_text() == "mine"

    async def test_overwrite_true_replaces(self, out_dir: Path) -> None:
        server = _server({"output_dir": str(out_dir)})
        out_dir.mkdir(parents=True, exist_ok=True)
        existing = out_dir / "logo.svg"
        existing.write_text("mine")
        result = await server._dispatch_tool(
            "solveit_save_badge",
            {"item_id": "DFT-1001", "format": "svg", "filename": "logo", "overwrite": True},
        )
        assert not result.isError, result.content
        assert existing.read_text().startswith("<svg")

    async def test_saving_same_badge_twice_succeeds(self, out_dir: Path) -> None:
        server = _server({"output_dir": str(out_dir)})
        args = {"item_id": "DFT-1001", "format": "svg"}
        first = await server._dispatch_tool("solveit_save_badge", args)
        second = await server._dispatch_tool("solveit_save_badge", args)
        assert not first.isError and not second.isError

    @pytest.mark.parametrize("filename", ["CON", "nul.svg", "com1", "LPT9.png"])
    async def test_rejects_windows_reserved_names(self, out_dir: Path, filename: str) -> None:
        server = _server({"output_dir": str(out_dir)})
        result = await server._dispatch_tool(
            "solveit_save_badge", {"item_id": "DFT-1001", "format": "svg", "filename": filename}
        )
        assert result.isError, filename


class TestObjectives:
    """Objective ids (DFO-) resolve and render."""

    async def test_get_objective_svg(self) -> None:
        server = _server()
        result = await server._dispatch_tool(
            "solveit_get_badge", {"item_id": " dfo-1015 ", "format": "svg"}
        )
        assert not result.isError, result.content
        assert "SOLVE-IT OBJECTIVE" in _text(result)
        assert json.loads(_text(result, 1))["type"] == "objective"

    async def test_get_objective_png(self) -> None:
        pytest.importorskip("resvg_py")
        server = _server()
        result = await server._dispatch_tool("solveit_get_badge", {"item_id": "DFO-1015"})
        assert not result.isError, result.content
        assert isinstance(result.content[0], types.ImageContent)

    async def test_no_objective_mapping_loaded(self) -> None:
        kb = FakeKB()
        kb.list_objectives = lambda: []  # type: ignore[method-assign]
        server = _server(kb=kb)
        result = await server._dispatch_tool("solveit_get_badge", {"item_id": "DFO-1015"})
        assert result.isError
        assert "No objective mapping is loaded" in _text(result)

    async def test_unknown_objective(self) -> None:
        server = _server()
        result = await server._dispatch_tool("solveit_get_badge", {"item_id": "DFO-9999"})
        assert result.isError
        assert "BADGE_NOT_FOUND" in _text(result)


class TestGuidance:
    """solveit_get_badge_guidance returns sizes and default positions."""

    async def test_without_slide_size(self) -> None:
        server = _server()
        result = await server._dispatch_tool("solveit_get_badge_guidance", {})
        assert not result.isError, result.content
        info = json.loads(_text(result))
        assert info["badge_width_pt"] == {"small": 443.2, "wide": 764.0}
        assert "for_slide" not in info
        assert "Top right corner" in info["default_position"]

    async def test_for_960x540_slide(self) -> None:
        server = _server()
        result = await server._dispatch_tool(
            "solveit_get_badge_guidance", {"slide_width": 960, "slide_height": 540}
        )
        assert not result.isError, result.content
        slide = json.loads(_text(result))["for_slide"]
        assert slide["factor"] == 0.5
        assert slide["badge_width_pt"] == {"small": 221.6, "wide": 382.0}
        small = slide["corner_frame"]["small"]
        assert small == {"x": 729.4, "y": 6.5, "w": 221.6}  # 18 pt right, 13 pt top, halved
        wide = slide["corner_frame"]["wide"]
        assert wide["x"] + wide["w"] == 951.0
        assert "note" not in slide

    async def test_header_height_moves_badge_below_band(self) -> None:
        server = _server()
        result = await server._dispatch_tool(
            "solveit_get_badge_guidance",
            {"slide_width": 960, "slide_height": 540, "header_height": 85},
        )
        assert not result.isError, result.content
        slide = json.loads(_text(result))["for_slide"]
        assert slide["corner_frame"]["small"]["y"] == 105.0  # band + 40 pt gap, halved
        assert slide["header_height_pt"] == 85

    async def test_reference_slide_matches_measured_corner(self) -> None:
        info = usage_guidance(1920, 1080)["for_slide"]["corner_frame"]["small"]
        assert info == {"x": 1458.8, "y": 13.0, "w": 443.2}

    @pytest.mark.parametrize(
        "arguments",
        [
            {"slide_width": 960},
            {"slide_width": 960, "slide_height": 0},
            {"slide_width": -960, "slide_height": -540},
            {"slide_width": 5, "slide_height": 5},
            {"slide_width": 1e300, "slide_height": 540},
            {"slide_width": float("nan"), "slide_height": 540},
            {"slide_width": 960, "slide_height": 540, "header_height": -1},
            {"slide_width": 960, "slide_height": 540, "header_height": 400},
            {"header_height": 85},
        ],
    )
    async def test_invalid_dimensions_are_tool_errors(self, arguments: dict[str, Any]) -> None:
        server = _server()
        result = await server._dispatch_tool("solveit_get_badge_guidance", arguments)
        assert result.isError, arguments
        assert "BADGE_INVALID_ARGUMENT" in _text(result) or "must" in _text(result)

    def test_rejects_bool_and_string_dimensions(self) -> None:
        for bad in (True, "960"):
            with pytest.raises(ValueError, match="number"):
                usage_guidance(bad, 540)

    async def test_registered_even_when_save_disabled(self) -> None:
        server = _server({"enable_save": False})
        assert "solveit_get_badge_guidance" in server._tools
        assert "solveit_save_badge" not in server._tools
