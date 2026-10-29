"""Rasterise badge SVGs to PNG.

Uses ``resvg_py`` (the optional ``badges`` extra) with the bundled
Liberation Sans Bold and no system fonts, so output is the same on every
host. ``png_with_dpi`` is a port of the SOLVE-IT Explorer's ``pngWithDpi``.
"""

from __future__ import annotations

import math
import re
import struct
import zlib
from pathlib import Path
from typing import Any

from mcp_chassis.extensions.badges.layout import MARGIN, BadgeLayout

FONT_PATH = Path(__file__).parent / "fonts" / "LiberationSans-Bold.ttf"
SCALES = (2, 4, 8)

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_ROOT_SIZE_RE = re.compile(r'^<svg ([^>]*?)width="[^"]*" height="[^"]*"')
_INSTALL_HINT = (
    "PNG badges need the 'badges' extra: pip install 'mcp-chassis[badges]' "
    "(or install resvg_py). SVG output works without it."
)


class BadgeRenderError(RuntimeError):
    """Raised when a badge cannot be rasterised."""


class BadgeExtraMissingError(BadgeRenderError):
    """Raised when ``resvg_py`` (the ``badges`` extra) is not installed."""


def _resvg() -> Any:
    """Import ``resvg_py`` lazily.

    Returns:
        The ``resvg_py`` module.

    Raises:
        BadgeExtraMissingError: If ``resvg_py`` is not installed.
    """
    try:
        import resvg_py
    except ImportError as exc:
        raise BadgeExtraMissingError(_INSTALL_HINT) from exc
    return resvg_py


def _round(x: float) -> int:
    """Round half up, as JavaScript's ``Math.round``."""
    return math.floor(x + 0.5)


def pixel_size(lay: BadgeLayout, scale: int) -> tuple[int, int]:
    """Return the PNG pixel size for a badge layout at ``scale``.

    Matches the Explorer's canvas size: ``Math.round(svgSize * scale)``.

    Args:
        lay: The badge layout.
        scale: Pixel scale (2, 4 or 8).

    Returns:
        A ``(width, height)`` tuple in pixels.
    """
    return (
        _round((lay.w + 2 * MARGIN) * scale),
        _round((lay.h + 2 * MARGIN) * scale),
    )


def svg_to_png(svg: str, width: int, height: int) -> bytes:
    """Render SVG source to PNG at an exact pixel size.

    Args:
        svg: SVG source.
        width: Output width in pixels.
        height: Output height in pixels.

    Returns:
        PNG bytes (without a pHYs chunk; see ``png_with_dpi``).

    Raises:
        BadgeRenderError: If ``resvg_py`` is missing or rendering fails.
    """
    resvg = _resvg()
    # Set the root size to the pixel size and stretch the viewBox to fill it, as the
    # Explorer's canvas drawImage does. resvg's own width/height options keep the
    # aspect ratio, which can lose a pixel row.
    sized, count = _ROOT_SIZE_RE.subn(
        rf'<svg \1preserveAspectRatio="none" width="{width}" height="{height}"', svg, count=1
    )
    if count != 1:
        raise BadgeRenderError("Badge SVG has no root width/height")
    try:
        data = resvg.svg_to_bytes(
            svg_string=sized,
            font_files=[str(FONT_PATH)],
            skip_system_fonts=True,
            sans_serif_family="Liberation Sans",
        )
    except ValueError as exc:
        raise BadgeRenderError(f"Badge render failed: {exc}") from exc
    return bytes(data)


def _chunks(png: bytes) -> list[tuple[bytes, bytes]]:
    """Split a PNG into ``(type, data)`` chunks.

    Args:
        png: PNG bytes.

    Returns:
        The chunks in file order.

    Raises:
        BadgeRenderError: If the data is not a well-formed PNG.
    """
    if not png.startswith(_PNG_SIGNATURE):
        raise BadgeRenderError("Not a PNG")
    out: list[tuple[bytes, bytes]] = []
    pos = len(_PNG_SIGNATURE)
    while pos < len(png):
        if pos + 8 > len(png):
            raise BadgeRenderError("Truncated PNG chunk header")
        (length,) = struct.unpack(">I", png[pos:pos + 4])
        ctype = png[pos + 4:pos + 8]
        end = pos + 12 + length
        if end > len(png):
            raise BadgeRenderError("Truncated PNG chunk")
        out.append((ctype, png[pos + 8:pos + 8 + length]))
        pos = end
    if not out or out[0][0] != b"IHDR":
        raise BadgeRenderError("PNG does not start with IHDR")
    return out


def _chunk_bytes(ctype: bytes, data: bytes) -> bytes:
    """Serialise one PNG chunk with its CRC."""
    crc = zlib.crc32(ctype + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + ctype + data + struct.pack(">I", crc)


def png_with_dpi(png: bytes, scale: int) -> bytes:
    """Tag a PNG with its pixel density so slides place it at point size.

    Inserts a pHYs chunk right after IHDR with ``scale * 72`` dpi, so
    Presentation tools show the badge at its slide size whatever the pixel count.
    Any existing pHYs chunk is replaced.

    Args:
        png: PNG bytes.
        scale: Pixel scale the PNG was rendered at.

    Returns:
        PNG bytes with the pHYs chunk.

    Raises:
        BadgeRenderError: If ``png`` is not a well-formed PNG.
    """
    ppm = _round(scale * 72 / 0.0254)
    phys = _chunk_bytes(b"pHYs", struct.pack(">IIB", ppm, ppm, 1))
    parts = [_PNG_SIGNATURE]
    for i, (ctype, data) in enumerate(_chunks(png)):
        if ctype == b"pHYs":
            continue
        parts.append(_chunk_bytes(ctype, data))
        if i == 0:
            parts.append(phys)
    return b"".join(parts)


def render_png(svg: str, lay: BadgeLayout, scale: int) -> tuple[bytes, tuple[int, int]]:
    """Render a badge SVG to a DPI-tagged PNG.

    Args:
        svg: Badge SVG source.
        lay: The layout the SVG was built from.
        scale: Pixel scale, one of ``SCALES``.

    Returns:
        A tuple of the PNG bytes and the ``(width, height)`` pixel size.

    Raises:
        ValueError: If ``scale`` is not one of ``SCALES``.
        BadgeRenderError: If rendering fails.
    """
    if scale not in SCALES:
        raise ValueError(f"Unknown scale {scale!r}. Valid: {', '.join(map(str, SCALES))}")
    size = pixel_size(lay, scale)
    return png_with_dpi(svg_to_png(svg, *size), scale), size
