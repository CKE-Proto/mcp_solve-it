"""Input sanitization for MCP tool arguments.

Provides three sanitization levels (strict, moderate, permissive) that
recursively clean string values in tool inputs. Non-string values
(numbers, booleans, null) pass through unchanged.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from mcp_chassis.errors import SanitizationError

# ASCII control characters except tab (0x09), newline (0x0A), carriage return (0x0D)
_CTRL_CHAR_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")

# Null byte
_NULL_BYTE_RE = re.compile(r"\x00")

# Path traversal: ../  ..\  /..  \..  and bare trailing ..
_PATH_TRAVERSAL_RE = re.compile(r"\.\.[/\\]|[/\\]\.\.|(?:^|[/\\])\.\.$")

# URL-encoded characters used in path traversal evasion (case-insensitive)
_TRAVERSAL_ENCODED_RE = re.compile(r"%2[eE]|%2[fF]|%5[cC]")

# Maximum iterations for fixed-point path traversal stripping
_MAX_TRAVERSAL_PASSES = 10

# Shell metacharacters (includes quotes, tilde, and newline as command separator)
_SHELL_META_RE = re.compile(r"[;|&$`\\!#()\[\]{}<>\"'~\n]")


_MAX_SANITIZE_DEPTH = 50


def sanitize_input(
    value: Any,
    level: str,
    *,
    _depth: int = 0,
) -> Any:
    """Recursively sanitize an input value.

    Strings are cleaned according to the level. Numbers, booleans, and
    None pass through unchanged. Dicts and lists are recursively
    sanitized. Both dict keys and values are sanitized.

    Levels:
    - strict: strip control chars, path traversal, shell metacharacters,
              null bytes, normalize Unicode NFC, strip Unicode control categories
    - moderate: strip control chars, null bytes, path traversal
    - permissive: strip null bytes only

    Args:
        value: The value to sanitize (any JSON-compatible type).
        level: Sanitization level ('strict', 'moderate', 'permissive').
        _depth: Internal recursion depth counter (do not set externally).

    Returns:
        Sanitized value of the same structural type.

    Raises:
        SanitizationError: If an unsupported level is specified or depth exceeded.
    """
    if level not in ("strict", "moderate", "permissive"):
        raise SanitizationError(
            f"Unknown sanitization level '{level}'",
            code="INVALID_SANITIZATION_LEVEL",
        )

    if _depth > _MAX_SANITIZE_DEPTH:
        raise SanitizationError(
            f"Input nesting depth exceeds maximum ({_MAX_SANITIZE_DEPTH})",
            code="SANITIZATION_DEPTH_EXCEEDED",
        )

    if isinstance(value, str):
        return _sanitize_string(value, level)
    elif isinstance(value, dict):
        sanitized_pairs: list[tuple[Any, Any]] = []
        seen_keys: dict[Any, Any] = {}
        for k, v in value.items():
            new_key = _sanitize_string(k, level) if isinstance(k, str) else k
            if new_key in seen_keys:
                raise SanitizationError(
                    f"Dict key collision: keys {seen_keys[new_key]!r} and {k!r} "
                    f"both sanitize to {new_key!r}",
                    code="KEY_COLLISION",
                )
            seen_keys[new_key] = k
            sanitized_pairs.append((new_key, sanitize_input(v, level, _depth=_depth + 1)))
        return dict(sanitized_pairs)
    elif isinstance(value, list):
        return [sanitize_input(item, level, _depth=_depth + 1) for item in value]
    else:
        # int, float, bool, None — pass through unchanged
        return value


def _sanitize_string(value: str, level: str) -> str:
    """Apply sanitization to a single string value.

    Args:
        value: String to sanitize.
        level: Sanitization level.

    Returns:
        Sanitized string.
    """
    if level == "strict":
        return _sanitize_strict(value)
    elif level == "moderate":
        return _sanitize_moderate(value)
    else:
        return _sanitize_permissive(value)


def _decode_traversal_percent_encoding(value: str) -> str:
    """Decode only percent-encoded characters relevant to path traversal.

    Decodes %2e (.), %2f (/), and %5c (\\) in any case combination.
    Other percent-encoded sequences are left intact to preserve string
    semantics.

    Args:
        value: String potentially containing percent-encoded traversal chars.

    Returns:
        String with traversal-relevant percent encodings decoded.
    """
    _decode_map = {
        "%2e": ".", "%2f": "/", "%5c": "\\",
    }
    return _TRAVERSAL_ENCODED_RE.sub(
        lambda m: _decode_map[m.group(0).lower()], value
    )


def _strip_path_traversal(value: str) -> str:
    """Remove path traversal sequences, handling stacked and encoded payloads.

    First decodes URL-encoded traversal characters, then repeatedly strips
    traversal patterns until a fixed point is reached (no further matches).

    Args:
        value: String to strip traversal sequences from.

    Returns:
        String with all path traversal sequences removed.
    """
    result = _decode_traversal_percent_encoding(value)
    for _ in range(_MAX_TRAVERSAL_PASSES):
        cleaned = _PATH_TRAVERSAL_RE.sub("", result)
        if cleaned == result:
            break
        result = cleaned
    return result


def _sanitize_strict(value: str) -> str:
    """Apply strict sanitization to a string.

    Removes control characters, path traversal sequences, shell
    metacharacters, normalizes to Unicode NFC, and strips Unicode
    control/format categories.

    Args:
        value: String to sanitize.

    Returns:
        Sanitized string.
    """
    result = unicodedata.normalize("NFC", value)
    result = _strip_unicode_controls(result)
    result = _NULL_BYTE_RE.sub("", result)
    result = _CTRL_CHAR_RE.sub("", result)
    result = _strip_path_traversal(result)
    result = _SHELL_META_RE.sub("", result)
    return result


def _sanitize_moderate(value: str) -> str:
    """Apply moderate sanitization to a string.

    Removes control characters, null bytes, and path traversal sequences.
    Shell metacharacters are NOT removed.

    Args:
        value: String to sanitize.

    Returns:
        Sanitized string.
    """
    result = _NULL_BYTE_RE.sub("", value)
    result = _CTRL_CHAR_RE.sub("", result)
    result = _strip_path_traversal(result)
    return result


def _sanitize_permissive(value: str) -> str:
    """Apply permissive sanitization to a string.

    Only removes null bytes.

    Args:
        value: String to sanitize.

    Returns:
        String with null bytes removed.
    """
    return _NULL_BYTE_RE.sub("", value)


def _strip_unicode_controls(value: str) -> str:
    """Remove Unicode control and format characters (Cc, Cf categories).

    Common whitespace (space, tab, newline, CR) is preserved.

    Args:
        value: String to process.

    Returns:
        String with Unicode control/format characters removed.
    """
    _allowed_controls = {"\t", "\n", "\r", " "}
    result = []
    for ch in value:
        cat = unicodedata.category(ch)
        if cat in ("Cc", "Cf") and ch not in _allowed_controls:
            continue
        result.append(ch)
    return "".join(result)
