"""SOLVE-IT slide badges: layout, SVG assembly and PNG rendering.

A port of the badge code in the SOLVE-IT Explorer. ``layout`` and ``svg``
are pure; ``render`` needs the optional ``badges`` extra (``resvg_py``).
"""

from mcp_chassis.extensions.badges.layout import BadgeLayout, layout
from mcp_chassis.extensions.badges.svg import badge_svg, badge_svg_with_layout

__all__ = ["BadgeLayout", "badge_svg", "badge_svg_with_layout", "layout"]
