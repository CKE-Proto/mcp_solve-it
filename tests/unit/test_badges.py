"""Tests for the badge layout, SVG and PNG rendering modules."""

from __future__ import annotations

import builtins
import struct
import zlib
from pathlib import Path
from typing import Any

import pytest

from mcp_chassis.extensions.badges import widths
from mcp_chassis.extensions.badges.layout import (
    MIN_H,
    SMALL_W,
    WIDE_W,
    js_num,
    layout,
    text_width,
    wrap,
)
from mcp_chassis.extensions.badges.render import (
    BadgeExtraMissingError,
    BadgeRenderError,
    pixel_size,
    png_with_dpi,
    render_png,
)
from mcp_chassis.extensions.badges.svg import badge_svg, badge_svg_with_layout
from tests._solveit_kb import load_kb

_GOLDEN = Path(__file__).parent / "golden"

_GOLDEN_CASES = {
    "objective": ("DFO-1015", "Prepare for a digital investigation"),
    "technique": ("DFT-1001", "Triage devices or media"),
    "weakness": (
        "DFW-1134",
        "Recovered (non-allocated) file content has been overwritten by the content "
        "of a newer, but also non-allocated file (which has residual file system "
        "information) but this is not detected",
    ),
    "mitigation": ("DFM-1001", "Use a write blocker & check <hash> values"),
}


def _chunks(png: bytes) -> list[tuple[bytes, bytes]]:
    out = []
    pos = 8
    while pos < len(png):
        (length,) = struct.unpack(">I", png[pos:pos + 4])
        ctype = png[pos + 4:pos + 8]
        data = png[pos + 8:pos + 8 + length]
        (crc,) = struct.unpack(">I", png[pos + 8 + length:pos + 12 + length])
        assert crc == zlib.crc32(ctype + data) & 0xFFFFFFFF
        out.append((ctype, data))
        pos += 12 + length
    return out


def _minimal_png(extra: list[tuple[bytes, bytes]] | None = None) -> bytes:
    def chunk(t: bytes, d: bytes) -> bytes:
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    idat = zlib.compress(b"\x00\x00\x00\x00\x00")
    body = chunk(b"IHDR", ihdr)
    for t, d in extra or []:
        body += chunk(t, d)
    return b"\x89PNG\r\n\x1a\n" + body + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


class TestJsNum:
    """js_num should match JavaScript's String(number)."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (764, "764"),
            (764.0, "764"),
            (0.0, "0"),
            (-0.0, "0"),
            (-2, "-2"),
            (443.2, "443.2"),
            (165.28, "165.28"),
            (143.39000000000001, "143.39000000000001"),
            (0.5, "0.5"),
            (0.001, "0.001"),
            (1e-5, "0.00001"),
            (1e-7, "1e-7"),
            (1.5e-7, "1.5e-7"),
            (1.5e16, "15000000000000000"),
            (1e21, "1e+21"),
            (1.25e22, "1.25e+22"),
            (123456789.125, "123456789.125"),
        ],
    )
    def test_matches_javascript(self, value: float, expected: str) -> None:
        assert js_num(value) == expected

    def test_rejects_nan(self) -> None:
        with pytest.raises(ValueError):
            js_num(float("nan"))


class TestWrap:
    """Tests for word wrapping and variant selection."""

    def test_text_width_sums_advances(self) -> None:
        # 'A' is 1479 units in Arial Bold at 2048 units/em.
        assert text_width("AA") == 2 * 1479 * 22 / 2048

    def test_fallback_width_for_unknown_character(self) -> None:
        assert text_width("一") == widths.FALLBACK_ADVANCE * 22 / 2048

    def test_curly_quotes_in_table(self) -> None:
        assert text_width("‘’") == 2 * 569 * 22 / 2048

    def test_collapses_whitespace(self) -> None:
        assert wrap("  a \t b\n c  ", 1000) == ["a b c"]

    def test_empty_name_has_no_lines(self) -> None:
        assert wrap("", 100) == []
        lay = layout("")
        assert lay.lines == [] and lay.h == MIN_H and lay.variant == "small"

    def test_long_word_is_not_broken(self) -> None:
        word = "x" * 200
        assert wrap(f"a {word} b", 50) == ["a", word, "b"]

    def test_one_line(self) -> None:
        lay = layout("Short")
        assert lay.variant == "small" and len(lay.lines) == 1
        assert lay.first == 93.5 - 26 / 2

    def test_auto_keeps_small_for_three_lines(self) -> None:
        name = "Acquire data from a mobile phone using a logical extraction tool"
        small = layout(name, "small")
        assert len(small.lines) == 3
        assert layout(name) == small

    def test_auto_picks_wide_beyond_three_lines(self) -> None:
        name = _GOLDEN_CASES["weakness"][1]
        assert len(layout(name, "small").lines) > 3
        lay = layout(name)
        assert lay.variant == "wide" and lay.w == WIDE_W
        assert len(lay.lines) == 4
        assert lay.first == 42.3
        assert lay.h == max(MIN_H, 58.1 + 26 * 4)

    def test_forced_variants(self) -> None:
        assert layout("Short", "wide").w == WIDE_W
        assert layout(_GOLDEN_CASES["weakness"][1], "small").w == SMALL_W

    def test_unknown_variant(self) -> None:
        with pytest.raises(ValueError, match="variant"):
            layout("x", "huge")

    def test_lines_fit_width(self) -> None:
        for line in layout(_GOLDEN_CASES["weakness"][1]).lines:
            assert text_width(line) <= WIDE_W - 167.3 - 32


class TestSvg:
    """Tests for SVG assembly."""

    @pytest.mark.parametrize("badge_type", sorted(_GOLDEN_CASES))
    def test_golden(self, badge_type: str) -> None:
        item_id, name = _GOLDEN_CASES[badge_type]
        expected = (_GOLDEN / f"badge_{badge_type}.svg").read_text(encoding="utf-8")
        assert badge_svg(badge_type, item_id, name) == expected

    def test_escapes_only_amp_lt_gt(self) -> None:
        svg = badge_svg("technique", "DFT-1<&>", "Tom's \"tool\" & <x>")
        assert "Tom's \"tool\" &amp; &lt;x&gt;" in svg
        assert ">DFT-1&lt;&amp;&gt;</text>" in svg

    def test_unknown_type(self) -> None:
        with pytest.raises(ValueError, match="type"):
            badge_svg("citation", "X", "y")

    def test_font_family_unchanged(self) -> None:
        svg = badge_svg("weakness", "DFW-1001", "Name")
        assert 'font-family="Arial, Helvetica, sans-serif"' in svg

    def test_tall_badge_shifts_icon(self) -> None:
        svg, lay = badge_svg_with_layout("technique", "DFT-1", _GOLDEN_CASES["weakness"][1])
        assert lay.h > MIN_H
        assert f'<g transform="translate(0 {js_num((lay.h - MIN_H) / 2)})">' in svg


class TestLongestRealName:
    """The longest name in the KB lays out without clamping."""

    def test_dfm_1307(self) -> None:
        kb = load_kb()
        if kb is None:
            pytest.skip("SOLVE-IT data not available")
        name = kb.get_mitigation("DFM-1307")["name"]
        assert len(name) == 295
        lay = layout(name)
        assert lay.variant == "wide"
        # Sum-of-advances wrapping gives 6 lines (the plan estimated 7).
        assert len(lay.lines) == 6
        assert lay.h == 58.1 + 26 * 6
        assert " ".join(lay.lines) == " ".join(name.split())


class TestPngWithDpi:
    """Tests for the pHYs chunk insertion."""

    @pytest.mark.parametrize(("scale", "ppm"), [(2, 5669), (4, 11339), (8, 22677)])
    def test_phys_after_ihdr(self, scale: int, ppm: int) -> None:
        out = png_with_dpi(_minimal_png(), scale)
        chunks = _chunks(out)
        assert [c[0] for c in chunks] == [b"IHDR", b"pHYs", b"IDAT", b"IEND"]
        assert chunks[1][1] == struct.pack(">IIB", ppm, ppm, 1)

    def test_replaces_existing_phys(self) -> None:
        src = _minimal_png([(b"pHYs", struct.pack(">IIB", 1, 1, 0))])
        chunks = _chunks(png_with_dpi(src, 4))
        phys = [c for c in chunks if c[0] == b"pHYs"]
        assert len(phys) == 1 and phys[0][1] == struct.pack(">IIB", 11339, 11339, 1)

    def test_rejects_non_png(self) -> None:
        with pytest.raises(BadgeRenderError):
            png_with_dpi(b"GIF89a", 2)


class TestRenderPng:
    """Tests for rasterisation with resvg."""

    @pytest.mark.parametrize("scale", [2, 4, 8])
    def test_renders_tagged_png(self, scale: int) -> None:
        pytest.importorskip("resvg_py")
        svg, lay = badge_svg_with_layout("technique", "DFT-1001", "Triage devices or media")
        png, size = render_png(svg, lay, scale)
        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        chunks = _chunks(png)
        assert chunks[1][0] == b"pHYs"
        assert sum(1 for c in chunks if c[0] == b"pHYs") == 1
        width, height = struct.unpack(">II", chunks[0][1][:8])
        assert (width, height) == size == pixel_size(lay, scale)

    def test_pixel_size_rounds_like_javascript(self) -> None:
        lay = layout("Short")
        # 443.2 * 4 = 1772.8 -> 1773, 165.28 * 4 = 661.12 -> 661
        assert pixel_size(lay, 4) == (1773, 661)

    def test_text_is_drawn(self) -> None:
        pytest.importorskip("resvg_py")
        from mcp_chassis.extensions.badges.render import svg_to_png

        blank = badge_svg("technique", "", "")
        with_text = badge_svg("technique", "DFT-1001", "Name")
        assert svg_to_png(blank, 443, 165) != svg_to_png(with_text, 443, 165)

    def test_svg_without_root_size_is_rejected(self) -> None:
        pytest.importorskip("resvg_py")
        from mcp_chassis.extensions.badges.render import svg_to_png

        with pytest.raises(BadgeRenderError, match="width"):
            svg_to_png('<svg xmlns="http://www.w3.org/2000/svg"/>', 10, 10)

    def test_invalid_scale(self) -> None:
        lay = layout("x")
        with pytest.raises(ValueError, match="scale"):
            render_png("<svg/>", lay, 3)

    def test_missing_extra_gives_install_hint(self, monkeypatch: Any) -> None:
        real_import = builtins.__import__

        def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "resvg_py":
                raise ImportError("no resvg")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        lay = layout("x")
        with pytest.raises(BadgeExtraMissingError, match="badges"):
            render_png(badge_svg("technique", "DFT-1", "x"), lay, 2)
