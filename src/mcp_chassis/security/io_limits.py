"""I/O size limit enforcement for MCP request and response payloads.

Protects the server from excessively large payloads that could cause
resource exhaustion.
"""

from __future__ import annotations

import logging

from mcp_chassis.errors import IOLimitError

logger = logging.getLogger(__name__)


def check_request_size(data: bytes | str, max_size: int) -> None:
    """Raise IOLimitError if the request data exceeds the maximum size.

    Args:
        data: Request payload as bytes or string.
        max_size: Maximum allowed size in bytes.

    Raises:
        IOLimitError: If the payload size exceeds max_size.
    """
    size = _byte_length(data)
    if size > max_size:
        logger.warning("Request size %d bytes exceeds limit %d bytes", size, max_size)
        raise IOLimitError(
            f"Request size {size} bytes exceeds limit {max_size} bytes",
            code="REQUEST_TOO_LARGE",
        )


def check_response_size(data: bytes | str, max_size: int) -> None:
    """Raise IOLimitError if the response data exceeds the maximum size.

    Args:
        data: Response payload as bytes or string.
        max_size: Maximum allowed size in bytes.

    Raises:
        IOLimitError: If the payload size exceeds max_size.
    """
    size = _byte_length(data)
    if size > max_size:
        logger.warning("Response size %d bytes exceeds limit %d bytes", size, max_size)
        raise IOLimitError(
            f"Response size {size} bytes exceeds limit {max_size} bytes",
            code="RESPONSE_TOO_LARGE",
        )


def _byte_length(data: bytes | str) -> int:
    """Return the byte length of a bytes or string value.

    Strings are encoded as UTF-8 for size calculation.

    Args:
        data: Data whose size to measure.

    Returns:
        Size in bytes.
    """
    if isinstance(data, bytes):
        return len(data)
    return len(data.encode("utf-8"))
