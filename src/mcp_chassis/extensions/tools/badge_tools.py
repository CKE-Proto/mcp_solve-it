"""SOLVE-IT slide badge tools.

Registers ``solveit_get_badge`` (returns the badge as a PNG image or SVG
source) and ``solveit_save_badge`` (writes it into the configured output
directory so a presentation tool can insert it). Badges match the ones the
SOLVE-IT Explorer copies to the clipboard.

PNG output needs the optional ``badges`` extra (``resvg_py``); SVG output
works without it.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp import types

from mcp_chassis.errors import ChassisError
from mcp_chassis.extensions.badges.guidance import usage_guidance
from mcp_chassis.extensions.badges.layout import MARGIN, VARIANTS, BadgeLayout
from mcp_chassis.extensions.badges.render import (
    SCALES,
    BadgeExtraMissingError,
    BadgeRenderError,
    render_png,
)
from mcp_chassis.extensions.badges.svg import badge_svg_with_layout
from mcp_chassis.server import ToolResult

if TYPE_CHECKING:
    from mcp_chassis.context import HandlerContext
    from mcp_chassis.server import ChassisServer

logger = logging.getLogger(__name__)

_FORMATS = ("png", "svg")
_FILENAME_RE = re.compile(r"[A-Za-z0-9._-]{1,64}")
_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
_PREFIXES = {
    "DFT-": ("technique", "get_technique"),
    "DFW-": ("weakness", "get_weakness"),
    "DFM-": ("mitigation", "get_mitigation"),
}
_DEFAULT_DIR_NAME = "solveit-badges"


class BadgeToolError(ChassisError):
    """Badge tool error returned to the client as a tool error.

    Args:
        message: Human-readable error message.
        code: Machine-readable error code.
    """

    def __init__(self, message: str, code: str = "BADGE_INVALID_ARGUMENT") -> None:
        """Initialize the error with message and code."""
        super().__init__(message, code)


@dataclass
class _Badge:
    """A rendered badge and its metadata."""

    badge_type: str
    item_id: str
    name: str
    fmt: str
    scale: int
    lay: BadgeLayout
    svg: str
    png: bytes | None
    width_px: int
    height_px: int

    def summary(self) -> dict[str, Any]:
        """Return the metadata reported to the client."""
        info: dict[str, Any] = {
            "id": self.item_id,
            "type": self.badge_type,
            "name": self.name,
            "variant": self.lay.variant,
            "lines": len(self.lay.lines),
            "format": self.fmt,
            "width_px": self.width_px,
            "height_px": self.height_px,
        }
        if self.fmt == "png":
            info["scale"] = self.scale
            info["dpi"] = self.scale * 72
        return info


def _resolve_item(kb: Any, raw_id: Any) -> tuple[str, str, str]:
    """Resolve an item id to ``(type, id, name)`` through the KB.

    Args:
        kb: The KnowledgeBase.
        raw_id: Client-supplied id (case and surrounding space ignored).

    Returns:
        The badge type, canonical id and item name.

    Raises:
        BadgeToolError: If the id is malformed or not in the KB.
    """
    if not isinstance(raw_id, str) or not raw_id.strip():
        raise BadgeToolError("item_id must be a non-empty string")
    item_id = raw_id.strip().upper()
    if item_id.startswith("DFO-"):
        objectives = kb.list_objectives()
        if not objectives:
            raise BadgeToolError("No objective mapping is loaded", "BADGE_NOT_FOUND")
        for objective in objectives:
            if str(objective.get("id", "")).upper() == item_id:
                return "objective", item_id, str(objective.get("name", ""))
        raise BadgeToolError(f"No objective with id '{item_id}'", "BADGE_NOT_FOUND")
    for prefix, (badge_type, method) in _PREFIXES.items():
        if item_id.startswith(prefix):
            item = getattr(kb, method)(item_id)
            if not item:
                raise BadgeToolError(f"No {badge_type} with id '{item_id}'", "BADGE_NOT_FOUND")
            return badge_type, str(item.get("id", item_id)), str(item.get("name", ""))
    raise BadgeToolError(
        f"Unrecognised id '{item_id}': expected a DFO-, DFT-, DFW- or DFM- id", "BADGE_NOT_FOUND"
    )


def _parse_options(arguments: dict[str, Any], max_scale: int) -> tuple[str, int, str]:
    """Validate the size, scale and format arguments.

    Args:
        arguments: Tool arguments.
        max_scale: Largest scale allowed by config.

    Returns:
        The variant, scale and format.

    Raises:
        BadgeToolError: If an argument is invalid.
    """
    variant = arguments.get("size", "auto")
    if variant not in VARIANTS:
        raise BadgeToolError(f"size must be one of {', '.join(VARIANTS)}")
    scale = arguments.get("scale", min(4, max_scale))
    allowed = [s for s in SCALES if s <= max_scale]
    if isinstance(scale, bool) or scale not in allowed:
        raise BadgeToolError(f"scale must be one of {', '.join(map(str, allowed))}")
    fmt = arguments.get("format", "png")
    if fmt not in _FORMATS:
        raise BadgeToolError(f"format must be one of {', '.join(_FORMATS)}")
    return variant, int(scale), fmt


def _make_badge(kb: Any, arguments: dict[str, Any], max_scale: int) -> _Badge:
    """Resolve the item and build the badge in the requested format.

    Args:
        kb: The KnowledgeBase.
        arguments: Tool arguments.
        max_scale: Largest scale allowed by config.

    Returns:
        The built badge.

    Raises:
        BadgeToolError: If an argument is invalid or rendering fails.
    """
    badge_type, item_id, name = _resolve_item(kb, arguments.get("item_id"))
    variant, scale, fmt = _parse_options(arguments, max_scale)
    svg, lay = badge_svg_with_layout(badge_type, item_id, name, variant)
    if fmt == "svg":
        return _Badge(
            badge_type, item_id, name, fmt, scale, lay, svg, None,
            round(lay.w + 2 * MARGIN), round(lay.h + 2 * MARGIN),
        )
    try:
        png, (width, height) = render_png(svg, lay, scale)
    except BadgeExtraMissingError as exc:
        raise BadgeToolError(str(exc), "BADGE_EXTRA_NOT_INSTALLED") from exc
    except BadgeRenderError as exc:
        raise BadgeToolError(str(exc), "BADGE_RENDER_ERROR") from exc
    return _Badge(badge_type, item_id, name, fmt, scale, lay, svg, png, width, height)


def _output_dir(configured: str) -> Path:
    """Return the badge output directory, creating it with mode 0700.

    Args:
        configured: ``[app.badges] output_dir``; empty means
            ``<tempdir>/solveit-badges``.

    Returns:
        The resolved output directory.

    Raises:
        BadgeToolError: If the directory is a symlink, not a directory, or
            (on POSIX) owned by another user.
    """
    base = (
        Path(configured).expanduser() if configured
        else Path(tempfile.gettempdir()) / _DEFAULT_DIR_NAME
    )
    base = base.absolute()
    if base.is_symlink():
        raise BadgeToolError(f"Badge output_dir '{base}' is a symlink", "BADGE_SAVE_ERROR")
    try:
        base.mkdir(mode=0o700, parents=True, exist_ok=True)
        st = base.lstat()
    except OSError as exc:
        raise BadgeToolError(
            f"Cannot create badge output_dir '{base}': {exc.strerror}", "BADGE_SAVE_ERROR"
        ) from exc
    if not stat.S_ISDIR(st.st_mode):
        raise BadgeToolError(f"Badge output_dir '{base}' is not a directory", "BADGE_SAVE_ERROR")
    if hasattr(os, "getuid") and st.st_uid != os.getuid():
        raise BadgeToolError(
            f"Badge output_dir '{base}' is owned by another user", "BADGE_SAVE_ERROR"
        )
    return base.resolve()


def _target_path(out_dir: Path, filename: Any, item_id: str, fmt: str) -> Path:
    """Validate the filename and return the path to write.

    Args:
        out_dir: The resolved output directory.
        filename: Client-supplied bare filename, or None for ``<ID>.<fmt>``.
        item_id: Canonical item id.
        fmt: Output format, used as the extension.

    Returns:
        The target path inside ``out_dir``.

    Raises:
        BadgeToolError: If the filename is unsafe or the target is a symlink.
    """
    if filename is None or filename == "":
        name = f"{item_id}.{fmt}"
    else:
        if not isinstance(filename, str):
            raise BadgeToolError("filename must be a string")
        name = filename
        if not name.lower().endswith(f".{fmt}"):
            name = f"{name}.{fmt}"
    if (
        not _FILENAME_RE.fullmatch(name)
        or name.startswith(".")
        or name.split(".")[0].upper() in _WINDOWS_RESERVED
    ):
        raise BadgeToolError(
            "filename must be 1-64 characters of letters, digits, '.', '_' or '-', "
            "must not start with '.', and is a bare name (no directories)"
        )
    target = out_dir / name
    if target.is_symlink():
        raise BadgeToolError(f"Refusing to write through symlink '{target}'", "BADGE_SAVE_ERROR")
    if not target.resolve().is_relative_to(out_dir):
        raise BadgeToolError("filename escapes the output directory", "BADGE_SAVE_ERROR")
    return target


def _write_file(target: Path, data: bytes, overwrite: bool) -> None:
    """Write ``data`` to ``target`` without following symlinks.

    An existing file is left alone unless ``overwrite`` is true. Writing
    identical content over an existing file is accepted, so saving the same
    badge twice works.

    Args:
        target: Path to write.
        data: File contents.
        overwrite: Whether an existing file with different content may be replaced.

    Raises:
        BadgeToolError: If the file exists and ``overwrite`` is false, or the
            write fails.
    """
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    flags = os.O_WRONLY | os.O_CREAT | nofollow | (os.O_TRUNC if overwrite else os.O_EXCL)
    try:
        fd = os.open(target, flags, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
    except FileExistsError:
        try:
            fd = os.open(target, os.O_RDONLY | nofollow)
            with os.fdopen(fd, "rb") as fh:
                same = fh.read(len(data) + 1) == data
        except OSError:
            same = False
        if not same:
            raise BadgeToolError(
                f"'{target.name}' already exists with different content; "
                "choose another filename or set overwrite to true",
                "BADGE_FILE_EXISTS",
            ) from None
    except OSError as exc:
        raise BadgeToolError(
            f"Cannot write badge to '{target}': {exc.strerror}", "BADGE_SAVE_ERROR"
        ) from exc


_ID_DESCRIPTION = (
    "Item id: an objective (DFO-...), technique (DFT-...), weakness (DFW-...) "
    "or mitigation (DFM-...)."
)


def _common_properties(max_scale: int) -> dict[str, Any]:
    """Return the input schema properties shared by both tools."""
    scales = [s for s in SCALES if s <= max_scale]
    return {
        "item_id": {"type": "string", "description": _ID_DESCRIPTION},
        "size": {
            "type": "string",
            "enum": list(VARIANTS),
            "description": (
                "Badge width: 'small' (439 pt), 'wide' (760 pt) or 'auto' (small when "
                "the name fits in three lines, otherwise wide). Default: auto."
            ),
        },
        "scale": {
            "type": "integer",
            "enum": scales,
            "description": (
                "PNG pixels per slide point (ignored for SVG). The PNG is tagged with "
                f"scale x 72 dpi so it places at slide size. Default: {min(4, max_scale)}."
            ),
        },
        "format": {
            "type": "string",
            "enum": list(_FORMATS),
            "description": "Output format. Default: png.",
        },
    }


def register(server: ChassisServer) -> None:
    """Register the badge tools.

    Skipped when the KB is not loaded or ``[app.badges] enabled`` is false.
    ``solveit_save_badge`` is registered only when ``enable_save`` is true.

    Args:
        server: The ChassisServer instance with ``_kb`` and ``_app_config``
            set by the init hook.
    """
    kb = getattr(server, "_kb", None)
    if kb is None:
        logger.warning("SOLVE-IT KB not loaded — badge tools not registered")
        return

    from mcp_chassis.extensions.solveit_init import BadgesConfig

    app_cfg = getattr(server, "_app_config", None)
    cfg: BadgesConfig = getattr(app_cfg, "badges", None) or BadgesConfig()
    if not cfg.enabled:
        logger.info("Badge tools disabled by [app.badges] enabled = false")
        return
    max_scale = cfg.max_scale

    async def _handle_get(arguments: dict[str, Any], context: HandlerContext) -> ToolResult:
        await context.log_debug("solveit_get_badge called")
        badge = _make_badge(kb, arguments, max_scale)
        summary = types.TextContent(type="text", text=json.dumps(badge.summary()))
        if badge.png is not None:
            image = types.ImageContent(
                type="image",
                data=base64.b64encode(badge.png).decode("ascii"),
                mimeType="image/png",
            )
            return ToolResult(content=[image, summary])
        return ToolResult(content=[types.TextContent(type="text", text=badge.svg), summary])

    server.register_tool(
        name="solveit_get_badge",
        description=(
            "Get the SOLVE-IT slide badge for an objective, technique, weakness or "
            "mitigation, as a PNG image or SVG source. Matches the badges the SOLVE-IT "
            "Explorer copies for presentation slides (1920x1080 deck)."
        ),
        input_schema={
            "type": "object",
            "properties": _common_properties(max_scale),
            "required": ["item_id"],
        },
        handler=_handle_get,
    )

    async def _handle_guidance(
        arguments: dict[str, Any], context: HandlerContext
    ) -> dict[str, Any]:
        await context.log_debug("solveit_get_badge_guidance called")
        try:
            return usage_guidance(
                arguments.get("slide_width"),
                arguments.get("slide_height"),
                arguments.get("header_height"),
            )
        except ValueError as exc:
            raise BadgeToolError(str(exc)) from exc

    server.register_tool(
        name="solveit_get_badge_guidance",
        description=(
            "How to size and place SOLVE-IT badges on slides: badge sizes, when the wide "
            "variant is used, default position (top right corner) "
            "and how to add them to a presentation. Pass slide_width and slide_height "
            "in points to get ready-made frames for that slide size, and header_height if "
            "the template has a header band along the top."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "slide_width": {
                    "type": "number", "minimum": 100, "maximum": 20000,
                    "description": "Slide width in points (e.g. 960 or 1920).",
                },
                "slide_height": {
                    "type": "number", "minimum": 100, "maximum": 20000,
                    "description": "Slide height in points (e.g. 540 or 1080).",
                },
                "header_height": {
                    "type": "number", "minimum": 0, "maximum": 10000,
                    "description": (
                        "Height in points of a header band along the top of the slide; "
                        "the badge is placed below it. Omit if there is none."
                    ),
                },
            },
        },
        handler=_handle_guidance,
    )

    if not cfg.enable_save:
        logger.info("solveit_save_badge disabled by [app.badges] enable_save = false")
        return

    output_dir = cfg.output_dir

    async def _handle_save(
        arguments: dict[str, Any], context: HandlerContext
    ) -> dict[str, Any]:
        await context.log_debug("solveit_save_badge called")
        badge = _make_badge(kb, arguments, max_scale)
        out_dir = _output_dir(output_dir)
        target = _target_path(out_dir, arguments.get("filename"), badge.item_id, badge.fmt)
        data = badge.png if badge.png is not None else badge.svg.encode("utf-8")
        _write_file(target, data, arguments.get("overwrite") is True)
        logger.info("Saved badge %s to %s", badge.item_id, target)
        return {"path": str(target), "bytes": len(data), **badge.summary()}

    properties = _common_properties(max_scale)
    properties["filename"] = {
        "type": "string",
        "description": (
            "Optional bare file name (letters, digits, '.', '_', '-'; max 64; no "
            "directories). The extension is added if missing. Default: <ID>.<format>."
        ),
    }
    properties["overwrite"] = {
        "type": "boolean",
        "description": (
            "Replace an existing file with the same name. Default: false, which "
            "refuses to overwrite a file whose content differs."
        ),
    }
    server.register_tool(
        name="solveit_save_badge",
        description=(
            "Save the SOLVE-IT slide badge for an objective, technique, weakness or mitigation to "
            "the server's badge output directory and return its absolute path, for "
            "inserting into a presentation slide."
        ),
        input_schema={
            "type": "object",
            "properties": properties,
            "required": ["item_id"],
        },
        handler=_handle_save,
    )
