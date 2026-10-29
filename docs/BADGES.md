# Slide badges

`solveit_get_badge` and `solveit_save_badge` produce the SOLVE-IT slide badge for an objective, technique, weakness or mitigation: the same badge the SOLVE-IT Explorer copies to the clipboard for presentation slides. Geometry, colours and icons come from the SOLVE-IT-Resources-Slides-v5 template (1920x1080 deck).

## How it works

- `extensions/badges/layout.py` and `svg.py` are a direct port of the Explorer's `BADGE`, `badgeWrap`, `badgeLayout` and `badgeSvg` (in `reporting_scripts/generate_html_from_kb.py`). They are pure Python with no I/O. `js_num()` prints numbers as JavaScript's `String(number)` does, so the SVG text matches the Explorer's exactly.
- `extensions/badges/render.py` rasterises with `resvg_py` (the optional `badges` extra) using only the bundled Liberation Sans Bold, so PNGs look the same on every host. The SVG keeps the Explorer's `font-family="Arial, Helvetica, sans-serif"`; the renderer maps the generic sans-serif family to Liberation Sans. The PNG size is `round(svg size x scale)`. The Explorer rounds the browser's integer image width instead, so sizes can differ from an Explorer PNG by a pixel (not yet checked in a browser). A pHYs chunk records `scale x 72` dpi so the image places at its slide size.
- Text is measured with a static Arial Bold width table (`extensions/badges/widths.py`), generated from the bundled font by `scripts/gen_badge_widths.py`. Liberation Sans Bold has the same advance widths as Arial Bold. The table covers printable ASCII plus U+2018/U+2019, which is every character in the current KB; any other character uses an average width and logs a warning once.

## Limits

- **Line breaks can differ from the browser at wrap boundaries.** The port measures a line as the sum of glyph advances. A browser's `canvas.measureText` also applies kerning, so a name whose line width sits right on the limit can wrap one word differently in the Explorer.
- **The differential test proves port logic, not browser fidelity.** `tests/integration/test_badge_differential.py` runs the Explorer's own badge JavaScript under Node with a stub canvas that uses the same width table, and checks the SVGs are byte-identical for every KB item in every size, and that `png_with_dpi` matches `pngWithDpi`. It does not compare against a real browser.
- Rasterisation is resvg's, not the browser's, so anti-aliasing differs slightly from an Explorer PNG.

## Saving files

`solveit_save_badge` writes only into `[app.badges] output_dir` (default `<temp dir>/solveit-badges`, overridable with `MCP_APP_BADGES_OUTPUT_DIR`). The client supplies at most a bare file name. The directory is created with mode `0700`; symlinked directories, directories owned by another user, symlinked targets and unsafe names are refused, and files are opened with `O_NOFOLLOW`. Choose an `output_dir` that the presentation tool you hand the path to is allowed to read.

## Response size

A PNG is returned as base64 `ImageContent` through the chassis `ToolResult`, and the response size limit counts the base64 data. The largest badge (the longest name, wide, scale 8) is well under the strict profile's 5 MB limit.

## Placing badges on slides

`solveit_get_badge_guidance` returns sizes and default positions so a client does not have to work them out. It takes optional `slide_width` and `slide_height` (points) and then adds ready-made frames for that slide size. Add `header_height` when the template has a header band along the top.

- Badges are drawn for a 1920x1080 deck: 443.2 pt wide (small) or 764 pt (wide), including the 2 pt margin. Scale by `slide_width / 1920` for other slide sizes. A 960x540 slide uses half.
- Default position for every badge type and both variants: the top right corner, with the right edge about 18 pt and the top about 13 pt from the slide edges (1920x1080 scale). These were measured, to about 5 pt, on a reference slide with no header band in that corner. With `header_height` the badge goes below the band. Further badges stack down the right edge, right aligned; the gap of about 20 pt is a suggestion, not measured.
- Small is the standard badge and wide is only for names too long for it. Use `size=small` and read `lines`: up to four lines is fine use `size=wide` above four. The four-line limit is a suggested default, not a measured rule. `size=auto` follows the SOLVE-IT Explorer and switches to wide above three lines. A wide badge is about 40% of the slide width, so check it clears the title.
- Add each badge to the slide as an image, using the saved file's path, with the frame from `corner_frame`. If the presentation tool offers an image role, "logo" suits a badge. Tools that build a deck from a theme often give slide 1 a title layout, so put badges on content slides.

The guidance is advice; the presentation tool decides the final placement.
