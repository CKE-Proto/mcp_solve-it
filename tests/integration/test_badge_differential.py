"""Differential test: Python badge port vs the SOLVE-IT Explorer's JavaScript.

Extracts the badge code (``// ── Slide badges`` up to ``const BADGE_SCALES``)
from the Explorer's ``generate_html_from_kb.py``, runs it under Node with a
stub canvas whose ``measureText`` uses the same width table as the Python
port, and asserts the SVGs are byte-identical for every real KB item in
every variant. It also checks ``png_with_dpi`` against ``pngWithDpi``.

This proves the port's logic, not browser fidelity: a browser's
``measureText`` applies kerning, so its line breaks can differ at wrap
boundaries.

Skipped when Node, the Explorer script or the SOLVE-IT data is missing.
Set ``SOLVEIT_EXPLORER_SCRIPT`` to the script path to override discovery.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from mcp_chassis.extensions.badges import widths
from mcp_chassis.extensions.badges.render import png_with_dpi
from mcp_chassis.extensions.badges.svg import badge_svg
from tests._solveit_kb import load_kb, solveit_path

_GOLDEN = Path(__file__).parent.parent / "unit" / "golden"
_START = "// ── Slide badges"
_END = "const BADGE_SCALES"
_SCRIPT_REL = Path("reporting_scripts") / "generate_html_from_kb.py"

_STUB = r"""
const TABLE = __TABLE__;
const ctx2d = {
  font: '',
  measureText(text) {
    const m = /(\d+(?:\.\d+)?)px/.exec(this.font);
    const size = Number(m[1]);
    let units = 0;
    for (const ch of String(text)) {
      units += Object.prototype.hasOwnProperty.call(TABLE.advances, ch)
        ? TABLE.advances[ch] : TABLE.fallback;
    }
    return {width: units * size / TABLE.upm};
  }
};
const document = {createElement: () => ({getContext: () => ctx2d})};
"""

_DRIVER = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
(async () => {
  const svgs = input.items.map(([t, id, name, v]) => badgeSvg(t, id, name, v));
  const pngs = [];
  for (const [b64, scale] of input.pngs) {
    const blob = pngWithDpi(Buffer.from(b64, 'base64'), scale);
    pngs.push(Buffer.from(await blob.arrayBuffer()).toString('base64'));
  }
  process.stdout.write(JSON.stringify({svgs, pngs}));
})();
"""


def _find_script() -> Path | None:
    """Locate an Explorer script that contains the badge code."""
    candidates: list[Path] = []
    env = os.environ.get("SOLVEIT_EXPLORER_SCRIPT")
    if env:
        candidates.append(Path(env))
    data = solveit_path()
    if data is not None:
        candidates.append(data / _SCRIPT_REL)
    for path in candidates:
        if path.is_file() and _START in path.read_text(encoding="utf-8"):
            return path
    return None


def _extract_js(script: Path) -> str:
    """Return the badge JS with the f-string escaping undone."""
    text = script.read_text(encoding="utf-8")
    start = text.index(_START)
    end = text.index(_END, start)
    region = text[start:end]
    return region.replace("{{", "{").replace("}}", "}").replace("\\\\", "\\")


@pytest.fixture(scope="module")
def run_js(tmp_path_factory: pytest.TempPathFactory) -> Any:
    """Return a function that runs the Explorer badge JS under Node."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not available")
    script = _find_script()
    if script is None:
        pytest.skip("Explorer script with badge code not found")
    table = {
        "advances": widths.ADVANCES,
        "fallback": widths.FALLBACK_ADVANCE,
        "upm": widths.UNITS_PER_EM,
    }
    js = (
        _STUB.replace("__TABLE__", json.dumps(table))
        + _extract_js(script)
        + _DRIVER
    )
    js_path = tmp_path_factory.mktemp("badge_js") / "badge.js"
    js_path.write_text(js, encoding="utf-8")

    def _run(items: list[list[str]], pngs: list[list[Any]] | None = None) -> dict[str, Any]:
        proc = subprocess.run(
            [node, str(js_path)],
            input=json.dumps({"items": items, "pngs": pngs or []}),
            capture_output=True, text=True, timeout=60, check=False,
        )
        assert proc.returncode == 0, proc.stderr
        result: dict[str, Any] = json.loads(proc.stdout)
        return result

    return _run


def _kb_items() -> list[tuple[str, str, str]]:
    kb = load_kb()
    if kb is None:
        pytest.skip("SOLVE-IT data not available")
    items: list[tuple[str, str, str]] = []
    for badge_type, listing in (
        ("objective", kb.list_objectives()),
        ("technique", kb.get_all_techniques_with_name_and_id()),
        ("weakness", kb.get_all_weaknesses_with_name_and_id()),
        ("mitigation", kb.get_all_mitigations_with_name_and_id()),
    ):
        items.extend((badge_type, i["id"], i["name"]) for i in listing)
    return items


def test_svg_identical_for_all_real_items(run_js: Any) -> None:
    items = _kb_items()
    assert {t for t, _, _ in items} == {"objective", "technique", "weakness", "mitigation"}
    assert any(i == "DFM-1307" for _, i, _ in items)
    cases = [[t, i, n, v] for t, i, n in items for v in ("auto", "small", "wide")]
    js_svgs = run_js(cases)["svgs"]
    mismatches = [
        (c[1], c[3]) for c, js in zip(cases, js_svgs, strict=True)
        if badge_svg(c[0], c[1], c[2], c[3]) != js
    ]
    assert mismatches == []


def test_svg_identical_for_edge_cases(run_js: Any) -> None:
    cases = [
        ["technique", "DFT-1", "", "auto"],
        ["weakness", "DFW-<&>", "Tom's \"x\" & <y> ‘q’", "auto"],
        ["mitigation", "DFM-1", "  spaced\t\tout   words  ", "small"],
        ["technique", "DFT-2", "x" * 120, "auto"],
        ["weakness", "DFW-2", "Unicode 一二 fallback widths", "wide"],
    ]
    js_svgs = run_js(cases)["svgs"]
    for case, js in zip(cases, js_svgs, strict=True):
        assert badge_svg(*case) == js, case


def test_goldens_match_javascript(run_js: Any) -> None:
    from tests.unit.test_badges import _GOLDEN_CASES

    cases = [[t, i, n, "auto"] for t, (i, n) in sorted(_GOLDEN_CASES.items())]
    js_svgs = run_js(cases)["svgs"]
    for case, js in zip(cases, js_svgs, strict=True):
        assert (_GOLDEN / f"badge_{case[0]}.svg").read_text(encoding="utf-8") == js


def test_png_with_dpi_matches_javascript(run_js: Any) -> None:
    pytest.importorskip("resvg_py")
    import base64

    from mcp_chassis.extensions.badges.layout import layout
    from mcp_chassis.extensions.badges.render import pixel_size, svg_to_png

    svg = badge_svg("technique", "DFT-1001", "Triage devices or media")
    raw = svg_to_png(svg, *pixel_size(layout("Triage devices or media"), 2))
    assert b"pHYs" not in raw
    scales = (2, 4, 8)
    b64 = base64.b64encode(raw).decode("ascii")
    js_pngs = run_js([], [[b64, s] for s in scales])["pngs"]
    for scale, js in zip(scales, js_pngs, strict=True):
        assert png_with_dpi(raw, scale) == base64.b64decode(js)
