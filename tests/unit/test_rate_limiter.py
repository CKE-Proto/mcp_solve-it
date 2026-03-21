"""Unit tests for mcp_chassis.security.rate_limiter module."""


import pytest

from mcp_chassis.config import RateLimitConfig
from mcp_chassis.errors import RateLimitError
from mcp_chassis.security.rate_limiter import (
    RateLimiter,
    check_rate_limit,
)


class TestRateLimiterDisabled:
    """Tests for rate limiter when disabled."""

    def test_disabled_always_allows(self) -> None:
        config = RateLimitConfig(enabled=False)
        limiter = RateLimiter(config)
        for _ in range(1000):
            result = limiter.check("any_tool")
            assert result.allowed

    def test_disabled_no_buckets(self) -> None:
        config = RateLimitConfig(enabled=False)
        limiter = RateLimiter(config)
        assert limiter._global_bucket is None


class TestRateLimiterEnabled:
    """Tests for rate limiter when enabled."""

    def test_allows_within_burst(self) -> None:
        config = RateLimitConfig(
            enabled=True, global_rpm=60, per_tool_rpm=30, burst_size=5
        )
        limiter = RateLimiter(config)
        for i in range(5):
            result = limiter.check("my_tool")
            assert result.allowed, f"Request {i} should be allowed"

    def test_blocks_after_burst_exhausted(self) -> None:
        config = RateLimitConfig(
            enabled=True, global_rpm=60, per_tool_rpm=30, burst_size=3
        )
        limiter = RateLimiter(config)
        # Exhaust burst
        for _ in range(3):
            limiter.check("my_tool")
        # Next request should be blocked
        result = limiter.check("my_tool")
        assert not result.allowed

    def test_denied_result_has_retry_after(self) -> None:
        config = RateLimitConfig(
            enabled=True, global_rpm=60, per_tool_rpm=6, burst_size=1
        )
        limiter = RateLimiter(config)
        limiter.check("tool")  # consume the burst token
        result = limiter.check("tool")
        assert not result.allowed
        assert result.retry_after > 0

    def test_denied_result_has_reason(self) -> None:
        config = RateLimitConfig(
            enabled=True, global_rpm=60, per_tool_rpm=6, burst_size=1
        )
        limiter = RateLimiter(config)
        limiter.check("tool")
        result = limiter.check("tool")
        assert not result.allowed
        assert len(result.reason) > 0

    def test_different_tools_have_separate_buckets(self) -> None:
        # Per-tool bucket is 2 tokens; global bucket is 20 tokens
        # Exhaust tool_a's per-tool bucket (2 requests), then tool_b still has tokens
        config = RateLimitConfig(
            enabled=True, global_rpm=600, per_tool_rpm=3, burst_size=2
        )
        limiter = RateLimiter(config)
        # Override global bucket to have more capacity than per-tool
        assert limiter._global_bucket is not None
        limiter._global_bucket.tokens = 20.0
        limiter._global_bucket.capacity = 20.0
        # Exhaust tool_a's per-tool bucket
        limiter.check("tool_a")
        limiter.check("tool_a")
        blocked = limiter.check("tool_a")
        assert not blocked.allowed
        # tool_b still has its own full bucket
        allowed = limiter.check("tool_b")
        assert allowed.allowed

    def test_per_tool_denial_does_not_drain_global_bucket(self) -> None:
        """Regression test for C-1: denied per-tool requests must not consume global tokens.

        Setup: burst_size=3 for both buckets, but we inflate global capacity to 20
        so it outlasts the per-tool bucket. After 3 allowed requests, per-tool is
        exhausted (0 tokens) while global still has 17. Subsequent denied requests
        to tool_a must NOT consume those 17 global tokens.
        """
        config = RateLimitConfig(
            enabled=True, global_rpm=600, per_tool_rpm=3, burst_size=3
        )
        limiter = RateLimiter(config)

        # Give global bucket more capacity so it outlasts per-tool
        assert limiter._global_bucket is not None
        limiter._global_bucket.tokens = 20.0
        limiter._global_bucket.capacity = 20.0

        # Exhaust tool_a's per-tool bucket (3 allowed requests, consuming 3 global tokens)
        for _ in range(3):
            result = limiter.check("tool_a")
            assert result.allowed
        # Global: 17 remaining, per-tool tool_a: 0 remaining

        # Send 20 denied requests to tool_a. Before the fix, each would consume
        # a global token, draining all 17 remaining. After the fix, zero are consumed.
        for _ in range(20):
            result = limiter.check("tool_a")
            assert not result.allowed

        # tool_b should still work — global bucket must still have tokens
        result = limiter.check("tool_b")
        assert result.allowed, (
            "tool_b was blocked because denied tool_a requests drained the global bucket"
        )

    def test_global_limit_applies_across_tools(self) -> None:
        config = RateLimitConfig(
            enabled=True, global_rpm=6, per_tool_rpm=600, burst_size=3
        )
        limiter = RateLimiter(config)
        # Exhaust global bucket via different tools
        limiter.check("tool_a")
        limiter.check("tool_b")
        limiter.check("tool_c")
        # Global bucket exhausted, any tool should be blocked
        result = limiter.check("tool_d")
        assert not result.allowed


class TestRateLimiterReset:
    """Tests for rate limiter reset functionality."""

    def test_reset_refills_buckets(self) -> None:
        config = RateLimitConfig(
            enabled=True, global_rpm=60, per_tool_rpm=3, burst_size=3
        )
        limiter = RateLimiter(config)
        # Exhaust
        for _ in range(3):
            limiter.check("my_tool")
        blocked = limiter.check("my_tool")
        assert not blocked.allowed
        # Reset
        limiter.reset()
        # Should be allowed again
        result = limiter.check("my_tool")
        assert result.allowed

    def test_reset_clears_per_tool_state(self) -> None:
        config = RateLimitConfig(
            enabled=True, global_rpm=600, per_tool_rpm=1, burst_size=1
        )
        limiter = RateLimiter(config)
        limiter.check("my_tool")
        limiter.reset()
        assert len(limiter._tool_buckets) == 0


class TestTokenRefill:
    """Tests for token bucket refill over time."""

    def test_tokens_refill_after_time(self) -> None:
        config = RateLimitConfig(
            enabled=True, global_rpm=600, per_tool_rpm=600, burst_size=1
        )
        limiter = RateLimiter(config)
        # Consume the token
        first = limiter.check("tool")
        assert first.allowed
        blocked = limiter.check("tool")
        assert not blocked.allowed

        # Simulate time passing by manipulating the bucket directly
        bucket = limiter._tool_buckets["tool"]
        bucket.last_refill -= 1.0  # Pretend 1 second passed
        if limiter._global_bucket:
            limiter._global_bucket.last_refill -= 1.0

        result = limiter.check("tool")
        assert result.allowed


class TestCheckRateLimitHelper:
    """Tests for check_rate_limit convenience function."""

    def test_raises_when_exceeded(self) -> None:
        config = RateLimitConfig(
            enabled=True, global_rpm=60, per_tool_rpm=3, burst_size=1
        )
        limiter = RateLimiter(config)
        limiter.check("tool")  # consume
        with pytest.raises(RateLimitError):
            check_rate_limit(limiter, "tool")

    def test_no_raise_when_allowed(self) -> None:
        config = RateLimitConfig(enabled=True, global_rpm=60, per_tool_rpm=30, burst_size=5)
        limiter = RateLimiter(config)
        check_rate_limit(limiter, "tool")  # Should not raise
