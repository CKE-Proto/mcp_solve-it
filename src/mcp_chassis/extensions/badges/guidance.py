"""Usage guidance for placing SOLVE-IT badges on slides.

Badges are drawn for a 1920x1080 deck. This module turns that into sizes and
default positions for any slide size, so a client does not have to work them
out. It is advice only: the presentation tool decides the final placement.
"""

from __future__ import annotations

import math
from typing import Any

from mcp_chassis.extensions.badges.layout import (
    MARGIN,
    SMALL_W,
    WIDE_W,
    content_height,
)

DESIGN_WIDTH = 1920
DESIGN_HEIGHT = 1080

# Default corner position in design points (1920x1080). Measured, to about
# +/-5 pt, on a 1920x1080 reference slide with a small technique badge in the
# top right corner and no header band there.
_RIGHT_MARGIN = 18
_TOP_MARGIN = 13
# Suggestions, not measured on a reference slide.
_HEADER_GAP = 40
_STACK_GAP = 20
_MAX_LINES = 7
_MIN_DIMENSION = 100
_MAX_DIMENSION = 20000


def _pt(value: float) -> float:
    """Round a point value for display."""
    return round(value, 1)


def _number(name: str, value: Any, low: float, high: float) -> float:
    """Validate a numeric argument.

    Args:
        name: Argument name, for the error message.
        value: The client-supplied value.
        low: Smallest allowed value.
        high: Largest allowed value.

    Returns:
        The value as a float.

    Raises:
        ValueError: If it is not a finite number in range.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    number = float(value)
    if not math.isfinite(number) or not low <= number <= high:
        raise ValueError(f"{name} must be between {low:g} and {high:g} points")
    return number


def usage_guidance(
    slide_width: Any = None,
    slide_height: Any = None,
    header_height: Any = None,
) -> dict[str, Any]:
    """Describe how to size and place badges, optionally for a slide size.

    Args:
        slide_width: Slide width in points, or None for the design deck only.
        slide_height: Slide height in points. Needed with ``slide_width``.
        header_height: Height in points of a header band along the top of the
            slide (for example the SOLVE-IT theme's dark title bar). The
            badge is placed below it. None means no band.

    Returns:
        A JSON-serialisable guidance dict.

    Raises:
        ValueError: If a dimension is missing, not a finite number or out of range.
    """
    if (slide_width is None) != (slide_height is None):
        raise ValueError("Give both slide_width and slide_height, or neither")
    if header_height is not None and slide_height is None:
        raise ValueError("header_height needs slide_width and slide_height")

    small = SMALL_W + 2 * MARGIN
    wide = WIDE_W + 2 * MARGIN
    guidance: dict[str, Any] = {
        "design_deck_pt": {"width": DESIGN_WIDTH, "height": DESIGN_HEIGHT},
        "badge_width_pt": {"small": _pt(small), "wide": _pt(wide)},
        "badge_height_pt_by_lines": {
            str(n): _pt(content_height(n) + 2 * MARGIN) for n in range(1, _MAX_LINES + 1)
        },
        "which_variant": (
            "Small is the standard badge and wide is only for names too long for it. "
            "Use size=small and read `lines` from the result: up to four lines is fine "
            "(a four-line name makes the badge taller, about 166 pt); for more than four "
            "lines use size=wide instead. The four-line limit "
            "is a suggested default. size=auto (the default, as in the "
            "SOLVE-IT Explorer) is stricter and switches to wide above three lines. "
            "A wide badge goes in the same top right corner; it is 764 pt wide, about 40% "
            "of a 1920 pt slide, so check it does not run into the title. Read `variant`, "
            "`lines`, width_px and height_px from the get/save result rather than guessing."
        ),
        "sizing": (
            "Frame width in slide points = width_px / scale * (slide_width / 1920). "
            "Set only the width; the height follows the aspect ratio. Do not stretch or "
            "crop. On a 1920x1080 slide a small badge is 443.2 pt wide and a wide badge "
            "764 pt. On a 960x540 slide use half of each."
        ),
        "default_position": (
            "Top right corner for every badge type (objective, technique, weakness, "
            "mitigation) and both variants: the right edge about 18 pt and the top about "
            "13 pt from the slide edges on a 1920x1080 slide (scale both by slide_width / "
            "1920). Measured on a reference slide with no "
            "header band there. If the template has a header band or logo in that corner, "
            "pass header_height to place the badge below it. Further badges on the same "
            "slide stack down the right edge, right aligned: the next badge's y is the "
            "previous badge's y plus its height plus the gap (about 20 pt; the stacking "
            "the gap is a suggestion, not measured). Right "
            "align by x = right edge minus that badge's own width."
        ),
        "presentation_tools": (
            "Add each badge as an image item with role \"logo\" and frame {x, y, w}, and "
            "a description such as \"SOLVE-IT technique badge DFT-1001\". Save the badge "
            "first with solveit_save_badge and use the returned path. If the tool "
            "has no logo role, a plain image works. Tools that build a deck from a "
            "theme often give the first slide a title layout, so put badges on "
            "content slides, not on slide 1."
        ),
        "avoid": [
            "Overlapping the title, a header band or its logo.",
            "Using a badge for text that should stay editable; badges are images.",
            "Mixing scales on one slide: use the same scale for every badge on it.",
        ],
    }
    if slide_width is not None and slide_height is not None:
        width = _number("slide_width", slide_width, _MIN_DIMENSION, _MAX_DIMENSION)
        height = _number("slide_height", slide_height, _MIN_DIMENSION, _MAX_DIMENSION)
        header = 0.0
        if header_height is not None:
            header = _number("header_height", header_height, 0, height / 2)
        factor = width / DESIGN_WIDTH
        top = header + _HEADER_GAP * factor if header else _TOP_MARGIN * factor
        right = width - _RIGHT_MARGIN * factor
        for_slide: dict[str, Any] = {
            "slide_pt": {"width": width, "height": height},
            "factor": factor,
            "badge_width_pt": {"small": _pt(small * factor), "wide": _pt(wide * factor)},
            "corner_frame": {
                variant: {
                    "x": _pt(right - badge * factor),
                    "y": _pt(top),
                    "w": _pt(badge * factor),
                }
                for variant, badge in (("small", small), ("wide", wide))
            },
            "stack_gap_pt": _pt(_STACK_GAP * factor),
        }
        if header:
            for_slide["header_height_pt"] = header
        if abs(width / height - DESIGN_WIDTH / DESIGN_HEIGHT) > 0.01:
            for_slide["note"] = (
                "The slide is not 16:9; check the badge fits before placing."
            )
        guidance["for_slide"] = for_slide
    return guidance
