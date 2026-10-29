"""Badge geometry, styles and text layout.

A port of the ``BADGE`` constant, ``badgeWrap`` and ``badgeLayout`` from
the SOLVE-IT Explorer (``generate_html_from_kb.py``). Geometry, colours and
icon paths come from the SOLVE-IT-Resources-Slides-v5 template (1920x1080
deck). Pure functions, no I/O.

Text is measured with a static Arial Bold width table (``widths.py``) as a
sum of advances, so layout is identical on every host. The browser's
``measureText`` also applies kerning, so line breaks may differ from the
Explorer for names that sit on a wrap boundary.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass

from mcp_chassis.extensions.badges.widths import ADVANCES, FALLBACK_ADVANCE, UNITS_PER_EM

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BadgeStyle:
    """Colours and title for one badge type.

    Attributes:
        panel: Fill of the left panel and the outline.
        label: Colour of the title label.
        icon: Colour of the panel icon.
        title: Title label text.
    """

    panel: str
    label: str
    icon: str
    title: str


@dataclass(frozen=True)
class IconPath:
    """One path of a badge icon.

    Attributes:
        d: SVG path data.
        fill: True to fill the path, False to stroke it.
        sw: Stroke width (used when ``fill`` is False).
    """

    d: str
    fill: bool
    sw: float


@dataclass(frozen=True)
class BadgeLayout:
    """Computed layout for one badge.

    Attributes:
        w: Badge width (without margin).
        h: Badge height (without margin).
        lines: Wrapped name lines.
        first: Top of the first name line.
        variant: ``"small"`` or ``"wide"``.
    """

    w: float
    h: float
    lines: list[str]
    first: float
    variant: str


STYLES: dict[str, BadgeStyle] = {
    "objective": BadgeStyle("#3C4650", "#4F5B67", "#D5DBE1", "SOLVE-IT OBJECTIVE"),
    "technique": BadgeStyle("#0A1B2D", "#0E7C93", "#18B7D3", "SOLVE-IT TECHNIQUE"),
    "weakness": BadgeStyle("#742631", "#B8323F", "#F3A6AE", "SOLVE-IT WEAKNESS"),
    "mitigation": BadgeStyle("#145A44", "#1E7A55", "#8FDDB8", "SOLVE-IT MITIGATION"),
}

SMALL_W = 439.2
WIDE_W = 760
MIN_H = 161.28
RADIUS = 26.88
PANEL_W = 136.8
PANEL_R = 22.8
TEXT_LEFT = 167.3
TEXT_RIGHT_PAD = 32
NAME_SIZE = 22
LABEL_SIZE = 18
PITCH = 26
ASCENT = 0.905
MARGIN = 2

VARIANTS = ("auto", "small", "wide")

ICONS: dict[str, list[IconPath]] = {
    "objective": [
        IconPath(
            "M 82.141 47.859 C 89.953 55.668 89.953 68.332 82.141 76.141 C 74.332 83.953 "
            "61.668 83.953 53.859 76.141 C 46.047 68.332 46.047 55.668 53.859 47.859 C 61.668 "
            "40.047 74.332 40.047 82.141 47.859 Z M 82.141 47.859",
            False, 3.5,
        ),
        IconPath(
            "M 75.070 54.930 C 78.977 58.836 78.977 65.164 75.070 69.070 C 71.164 72.977 "
            "64.836 72.977 60.930 69.070 C 57.023 65.164 57.023 58.836 60.930 54.930 C 64.836 "
            "51.023 71.164 51.023 75.070 54.930 Z M 75.070 54.930",
            False, 3.5,
        ),
        IconPath(
            "M 72.242 57.758 C 74.586 60.102 74.586 63.898 72.242 66.242 C 69.898 68.586 "
            "66.102 68.586 63.758 66.242 C 61.414 63.898 61.414 60.102 63.758 57.758 C 66.102 "
            "55.414 69.898 55.414 72.242 57.758 Z M 72.242 57.758",
            True, 0,
        ),
        IconPath(
            "M 66.000 50.000 L 69.000 50.000 L 69.000 32.000 L 66.000 32.000 Z M 66.000 "
            "50.000",
            True, 0,
        ),
        IconPath(
            "M 66.000 92.000 L 69.000 92.000 L 69.000 74.000 L 66.000 74.000 Z M 66.000 "
            "92.000",
            True, 0,
        ),
        IconPath(
            "M 38.000 63.000 L 56.000 63.000 L 56.000 60.000 L 38.000 60.000 Z M 38.000 "
            "63.000",
            True, 0,
        ),
        IconPath(
            "M 80.000 63.000 L 98.000 63.000 L 98.000 60.000 L 80.000 60.000 Z M 80.000 "
            "63.000",
            True, 0,
        ),
    ],
    "technique": [
        IconPath(
            "M 91.742 41.617 C 99.234 49.109 99.234 61.254 91.742 68.742 C 84.254 76.234 "
            "72.109 76.234 64.617 68.742 C 57.129 61.254 57.129 49.109 64.617 41.617 C "
            "72.109 34.129 84.254 34.129 91.742 41.617 Z M 91.742 41.617",
            False, 2.8,
        ),
        IconPath(
            "M 63.129 68.734 L 66.062 71.664 C 66.465 72.070 66.465 72.727 66.062 73.133 L "
            "52.133 87.062 C 51.727 87.465 51.070 87.465 50.664 87.062 L 47.734 84.129 C "
            "47.328 83.723 47.328 83.066 47.734 82.664 L 61.664 68.734 C 62.066 68.328 "
            "62.723 68.328 63.129 68.734 Z M 63.129 68.734",
            True, 0,
        ),
        IconPath(
            "M 66.000 47.812 L 87.773 47.812 L 87.773 46.000 L 66.000 46.000 Z M 66.000 47.812",
            True, 0,
        ),
        IconPath(
            "M 66.000 54.812 L 90.883 54.812 L 90.883 53.000 L 66.000 53.000 Z M 66.000 54.812",
            True, 0,
        ),
        IconPath(
            "M 66.000 62.812 L 84.145 62.812 L 84.145 61.000 L 66.000 61.000 Z M 66.000 62.812",
            True, 0,
        ),
    ],
    "weakness": [
        IconPath(
            "M 67.930 32.000 L 93.852 78.656 L 42.012 78.656 Z M 67.930 32.000",
            False, 3.5,
        ),
        IconPath(
            "M 66.000 61.551 L 70.500 61.551 L 70.500 46.000 L 66.000 46.000 Z M 66.000 61.551",
            True, 0,
        ),
        IconPath(
            "M 70.840 64.832 C 71.945 65.938 71.945 67.730 70.840 68.840 C 69.730 69.945 "
            "67.938 69.945 66.832 68.840 C 65.723 67.730 65.723 65.938 66.832 64.832 C "
            "67.938 63.723 69.730 63.723 70.840 64.832 Z M 70.840 64.832",
            True, 0,
        ),
    ],
    "mitigation": [
        IconPath(
            "M 68.000 35.000 L 92.000 43.398 L 92.000 62.066 C 92.000 77.000 81.441 85.867 "
            "68.000 91.000 C 54.559 85.867 44.000 77.000 44.000 62.066 L 44.000 43.398 Z M "
            "68.000 35.000",
            False, 3.5,
        ),
    ],
}

# Characters matched by JavaScript's ``\s`` (WhiteSpace plus LineTerminator).
_JS_WHITESPACE_RE = re.compile(
    "[\t\n\v\f\r    -     　﻿]+"
)

_warned_fallback = False


def js_num(value: float) -> str:
    """Format a number the way JavaScript's ``String(number)`` does.

    Uses the shortest round-trip digits (as Python's ``repr``), prints
    integral values without ``.0``, prints ``-0`` as ``0`` and switches to
    exponent form only outside ``1e-7 < |x| < 1e21``, as JavaScript does.

    Args:
        value: The number to format.

    Returns:
        The JavaScript string form of ``value``.

    Raises:
        ValueError: If ``value`` is NaN or infinite.
    """
    x = float(value)
    if math.isnan(x) or math.isinf(x):
        raise ValueError(f"Cannot format non-finite number {value!r}")
    if x == 0:
        return "0"
    sign = "-" if x < 0 else ""
    mantissa, _, exp_part = repr(abs(x)).partition("e")
    int_part, _, frac_part = mantissa.partition(".")
    digits = (int_part + frac_part).lstrip("0")
    # Decimal exponent n such that value = 0.digits * 10**n (ECMA-262 Number::toString).
    n = len(int_part) + (int(exp_part) if exp_part else 0)
    if int_part == "0":
        n -= len(frac_part) - len(frac_part.lstrip("0"))
        n -= 1
    digits = digits.rstrip("0") or "0"
    k = len(digits)
    if k <= n <= 21:
        return sign + digits + "0" * (n - k)
    if 0 < n <= 21:
        return sign + digits[:n] + "." + digits[n:]
    if -6 < n <= 0:
        return sign + "0." + "0" * (-n) + digits
    e = n - 1
    exp = f"e{'+' if e >= 0 else '-'}{abs(e)}"
    if k == 1:
        return sign + digits + exp
    return sign + digits[0] + "." + digits[1:] + exp


def text_width(text: str, size: float = NAME_SIZE) -> float:
    """Return the width of ``text`` in bold Arial at ``size`` px.

    Sums advance widths without kerning. Characters missing from the table
    use ``FALLBACK_ADVANCE`` (logged once per process).

    Args:
        text: Text to measure.
        size: Font size in px.

    Returns:
        Width in px.
    """
    global _warned_fallback
    units = 0
    for ch in text:
        adv = ADVANCES.get(ch)
        if adv is None:
            if not _warned_fallback:
                logger.warning(
                    "Badge width table has no entry for %r; using average width", ch
                )
                _warned_fallback = True
            adv = FALLBACK_ADVANCE
        units += adv
    return units * size / UNITS_PER_EM


def wrap(text: str, max_w: float) -> list[str]:
    """Greedy word wrap, a port of ``badgeWrap``.

    Args:
        text: Text to wrap.
        max_w: Maximum line width in px at ``NAME_SIZE``.

    Returns:
        The wrapped lines. A single word wider than ``max_w`` gets a line
        of its own and is not broken.
    """
    lines: list[str] = []
    cur = ""
    for word in (w for w in _JS_WHITESPACE_RE.split(str(text)) if w):
        cand = cur + " " + word if cur else word
        if not cur or text_width(cand) <= max_w:
            cur = cand
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def content_height(lines: int) -> float:
    """Return the badge height (without margin) for a name of ``lines`` lines.

    Args:
        lines: Number of wrapped name lines.

    Returns:
        The height in design points.
    """
    return max(MIN_H, 58.1 + PITCH * lines)


def _build(name: str, w: float, variant: str) -> BadgeLayout:
    """Lay out ``name`` in a badge of width ``w``."""
    lines = wrap(name, w - TEXT_LEFT - TEXT_RIGHT_PAD)
    n = len(lines)
    h = content_height(n)
    first = 42.3 if n >= 4 else 93.5 - PITCH * n / 2
    return BadgeLayout(w=w, h=h, lines=lines, first=first, variant=variant)


def layout(name: str, variant: str = "auto") -> BadgeLayout:
    """Compute the badge layout, a port of ``badgeLayout``.

    ``auto`` uses the small badge when the name fits in three lines,
    otherwise the wide one. The line count is not clamped.

    Args:
        name: Item name.
        variant: ``"auto"``, ``"small"`` or ``"wide"``.

    Returns:
        The computed layout.

    Raises:
        ValueError: If ``variant`` is not recognised.
    """
    if variant not in VARIANTS:
        raise ValueError(f"Unknown badge variant '{variant}'. Valid: {', '.join(VARIANTS)}")
    if variant == "small":
        return _build(name, SMALL_W, "small")
    if variant == "wide":
        return _build(name, WIDE_W, "wide")
    small = _build(name, SMALL_W, "small")
    return small if len(small.lines) <= 3 else _build(name, WIDE_W, "wide")
