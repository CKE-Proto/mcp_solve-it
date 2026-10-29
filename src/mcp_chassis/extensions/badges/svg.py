"""Badge SVG assembly, a direct port of the SOLVE-IT Explorer's ``badgeSvg``.

The output is byte-identical to the Explorer's when both measure text with
the same width table (checked by the differential test).
"""

from __future__ import annotations

from mcp_chassis.extensions.badges.layout import (
    ASCENT,
    ICONS,
    LABEL_SIZE,
    MARGIN,
    MIN_H,
    NAME_SIZE,
    PANEL_R,
    PANEL_W,
    PITCH,
    RADIUS,
    STYLES,
    TEXT_LEFT,
    BadgeLayout,
    js_num,
    layout,
    text_width,
)

_FONT_ATTRS = 'font-family="Arial, Helvetica, sans-serif" font-weight="bold"'


def _esc(text: str) -> str:
    """Escape ``&``, ``<`` and ``>`` as the Explorer does."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _baseline(top: float, size: float) -> float:
    """Return the text baseline for a line whose top is ``top``."""
    return top + ASCENT * size


def badge_svg_with_layout(
    badge_type: str, item_id: str, name: str, variant: str = "auto"
) -> tuple[str, BadgeLayout]:
    """Build the badge SVG and return it with its layout.

    Args:
        badge_type: ``"technique"``, ``"weakness"`` or ``"mitigation"``.
        item_id: Item id shown in the panel (e.g. ``DFT-1001``).
        name: Item name.
        variant: ``"auto"``, ``"small"`` or ``"wide"``.

    Returns:
        A tuple of the SVG source and the layout used.

    Raises:
        ValueError: If ``badge_type`` or ``variant`` is not recognised.
    """
    st = STYLES.get(badge_type)
    if st is None:
        raise ValueError(
            f"Unknown badge type '{badge_type}'. Valid: {', '.join(STYLES)}"
        )
    lay = layout(name or "", variant or "auto")
    m = MARGIN
    h = lay.h
    id_w = text_width(item_id)
    n = js_num

    s = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="' + n(lay.w + 2 * m)
        + '" height="' + n(h + 2 * m)
        + '" viewBox="' + n(-m) + " " + n(-m) + " " + n(lay.w + 2 * m) + " " + n(h + 2 * m)
        + '">'
    )
    s += (
        '<rect width="' + n(lay.w) + '" height="' + n(h) + '" rx="' + n(RADIUS)
        + '" fill="#fff"/>'
    )
    s += (
        '<rect width="' + n(PANEL_W) + '" height="' + n(h) + '" rx="' + n(PANEL_R)
        + '" fill="' + st.panel + '" stroke="' + st.panel + '" stroke-width="1.6"/>'
    )
    s += '<rect x="122.4" width="17.28" height="' + n(h) + '" fill="' + st.panel + '"/>'
    s += (
        '<rect width="' + n(lay.w) + '" height="' + n(h) + '" rx="' + n(RADIUS)
        + '" fill="none" stroke="' + st.panel + '" stroke-width="1.8"/>'
    )
    s += '<g transform="translate(0 ' + n((h - MIN_H) / 2) + ')">'
    for e in ICONS[badge_type]:
        if e.fill:
            s += '<path d="' + e.d + '" fill="' + st.icon + '"/>'
        else:
            s += (
                '<path d="' + e.d + '" fill="none" stroke="' + st.icon
                + '" stroke-width="' + n(e.sw) + '"/>'
            )
    s += "</g>"
    s += (
        '<text x="' + n(TEXT_LEFT) + '" y="' + n(_baseline(15.3, LABEL_SIZE)) + '" '
        + _FONT_ATTRS + ' font-size="' + n(LABEL_SIZE) + '" fill="' + st.label + '">'
        + st.title + "</text>"
    )
    for i, line in enumerate(lay.lines):
        s += (
            '<text x="' + n(TEXT_LEFT) + '" y="'
            + n(_baseline(lay.first + i * PITCH, NAME_SIZE)) + '" ' + _FONT_ATTRS
            + ' font-size="' + n(NAME_SIZE) + '" fill="#0A1B2D">' + _esc(line) + "</text>"
        )
    s += (
        '<text x="' + n(PANEL_W / 2 - id_w / 2) + '" y="'
        + n(_baseline(h - 37.8, NAME_SIZE)) + '" ' + _FONT_ATTRS
        + ' font-size="' + n(NAME_SIZE) + '" fill="#fff">' + _esc(item_id) + "</text>"
    )
    return s + "</svg>", lay


def badge_svg(badge_type: str, item_id: str, name: str, variant: str = "auto") -> str:
    """Build the SVG source for a SOLVE-IT slide badge.

    Args:
        badge_type: ``"technique"``, ``"weakness"`` or ``"mitigation"``.
        item_id: Item id shown in the panel (e.g. ``DFT-1001``).
        name: Item name.
        variant: ``"auto"``, ``"small"`` or ``"wide"``.

    Returns:
        The SVG source.

    Raises:
        ValueError: If ``badge_type`` or ``variant`` is not recognised.
    """
    return badge_svg_with_layout(badge_type, item_id, name, variant)[0]
