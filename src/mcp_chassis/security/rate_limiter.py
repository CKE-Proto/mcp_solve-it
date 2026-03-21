"""Token bucket rate limiter for MCP tool calls.

Provides global and per-tool rate limiting using an in-memory token bucket
algorithm. Uses time.monotonic() for clock accuracy.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from mcp_chassis.config import RateLimitConfig
from mcp_chassis.errors import RateLimitError

logger = logging.getLogger(__name__)


@dataclass
class _Bucket:
    """A single token bucket.

    Attributes:
        tokens: Current token count (float for partial tokens).
        last_refill: Monotonic timestamp of last refill.
        capacity: Maximum token count (burst size).
        refill_rate: Tokens added per second.
    """

    tokens: float
    last_refill: float
    capacity: float
    refill_rate: float

    def _refill(self, now: float) -> None:
        """Refill tokens based on elapsed time since last refill.

        Args:
            now: Current monotonic time.
        """
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

    def has_token(self, now: float) -> bool:
        """Check if a token is available, refilling first but not consuming.

        Args:
            now: Current monotonic time.

        Returns:
            True if at least one token is available.
        """
        self._refill(now)
        return self.tokens >= 1.0

    def consume(self, now: float) -> bool:
        """Consume one token if available.

        Callers must call has_token() before this method to ensure a
        token is available and the bucket is refilled.

        Args:
            now: Current monotonic time.

        Returns:
            True if a token was consumed; False if bucket was empty.
        """
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False

    def retry_after(self, now: float) -> float:
        """Calculate seconds until one token will be available.

        Args:
            now: Current monotonic time (unused; kept for symmetry).

        Returns:
            Seconds until the next token is available.
        """
        deficit = 1.0 - self.tokens
        if self.refill_rate <= 0:
            return float("inf")
        return max(0.0, deficit / self.refill_rate)


@dataclass
class RateLimitResult:
    """Result of a rate limit check.

    Attributes:
        allowed: True if the request is within limits.
        retry_after: Seconds until the client may retry (0 if allowed).
        reason: Human-readable reason for denial.
    """

    allowed: bool
    retry_after: float = 0.0
    reason: str = ""


class RateLimiter:
    """In-memory token bucket rate limiter with global and per-tool buckets.

    Each tool gets its own bucket. A separate global bucket applies to all
    requests regardless of tool. The request is allowed only when BOTH
    the global bucket and the per-tool bucket have tokens available.

    Args:
        config: Rate limiting configuration.
    """

    def __init__(self, config: RateLimitConfig) -> None:
        """Initialize the rate limiter with the given configuration.

        Args:
            config: Rate limiting configuration.
        """
        self._config = config
        self._global_bucket: _Bucket | None = None
        self._tool_buckets: dict[str, _Bucket] = {}

        if config.enabled:
            now = time.monotonic()
            self._global_bucket = _Bucket(
                tokens=float(config.burst_size),
                last_refill=now,
                capacity=float(config.burst_size),
                refill_rate=config.global_rpm / 60.0,
            )

    def check(self, tool_name: str) -> RateLimitResult:
        """Check whether a request for the given tool is within rate limits.

        Consumes one token from the global bucket and one from the per-tool
        bucket if both are available.

        Args:
            tool_name: Name of the tool being called.

        Returns:
            RateLimitResult indicating allowed or denied with retry-after.
        """
        if not self._config.enabled:
            return RateLimitResult(allowed=True)

        now = time.monotonic()

        # Ensure per-tool bucket exists
        if tool_name not in self._tool_buckets:
            self._tool_buckets[tool_name] = _Bucket(
                tokens=float(self._config.burst_size),
                last_refill=now,
                capacity=float(self._config.burst_size),
                refill_rate=self._config.per_tool_rpm / 60.0,
            )

        global_bucket = self._global_bucket
        tool_bucket = self._tool_buckets[tool_name]

        if global_bucket is None:
            msg = "Global rate limit bucket is None despite rate limiting being enabled"
            raise RuntimeError(msg)

        # Peek both buckets before consuming either. This prevents a denied
        # per-tool request from wasting a global token (see AUDIT_RESULTS.md C-1).
        if not global_bucket.has_token(now):
            wait = global_bucket.retry_after(now)
            logger.warning("Global rate limit exceeded for tool '%s'", tool_name)
            return RateLimitResult(
                allowed=False,
                retry_after=wait,
                reason=f"Global rate limit exceeded. Retry after {wait:.1f}s",
            )

        if not tool_bucket.has_token(now):
            wait = tool_bucket.retry_after(now)
            logger.warning("Per-tool rate limit exceeded for tool '%s'", tool_name)
            return RateLimitResult(
                allowed=False,
                retry_after=wait,
                reason=f"Rate limit exceeded for tool '{tool_name}'. Retry after {wait:.1f}s",
            )

        # Both buckets have capacity — consume one token from each
        global_bucket.consume(now)
        tool_bucket.consume(now)
        return RateLimitResult(allowed=True)

    def reset(self) -> None:
        """Reset all token buckets to full capacity.

        Intended for use in tests to avoid cross-test state pollution.
        """
        now = time.monotonic()
        if self._global_bucket is not None:
            self._global_bucket.tokens = self._global_bucket.capacity
            self._global_bucket.last_refill = now
        for bucket in self._tool_buckets.values():
            bucket.tokens = bucket.capacity
            bucket.last_refill = now
        self._tool_buckets.clear()


def check_rate_limit(limiter: RateLimiter, tool_name: str) -> None:
    """Check rate limit and raise RateLimitError if exceeded.

    Convenience wrapper for use in middleware.

    Args:
        limiter: The RateLimiter instance.
        tool_name: Tool name being requested.

    Raises:
        RateLimitError: If the rate limit is exceeded.
    """
    result = limiter.check(tool_name)
    if not result.allowed:
        raise RateLimitError(
            result.reason,
            retry_after=result.retry_after,
        )
