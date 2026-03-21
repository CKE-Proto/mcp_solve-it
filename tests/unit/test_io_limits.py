"""Unit tests for mcp_chassis.security.io_limits module."""

import pytest

from mcp_chassis.errors import IOLimitError
from mcp_chassis.security.io_limits import check_request_size, check_response_size


class TestCheckRequestSize:
    """Tests for check_request_size function."""

    def test_allows_within_limit_bytes(self) -> None:
        data = b"x" * 100
        check_request_size(data, 1000)  # Should not raise

    def test_allows_within_limit_string(self) -> None:
        data = "x" * 100
        check_request_size(data, 1000)  # Should not raise

    def test_raises_when_bytes_exceed_limit(self) -> None:
        data = b"x" * 200
        with pytest.raises(IOLimitError) as exc_info:
            check_request_size(data, 100)
        assert exc_info.value.code == "REQUEST_TOO_LARGE"

    def test_raises_when_string_exceeds_limit(self) -> None:
        data = "x" * 200
        with pytest.raises(IOLimitError) as exc_info:
            check_request_size(data, 100)
        assert exc_info.value.code == "REQUEST_TOO_LARGE"

    def test_exactly_at_limit_is_allowed(self) -> None:
        data = b"x" * 100
        check_request_size(data, 100)  # Should not raise

    def test_error_includes_sizes(self) -> None:
        data = b"x" * 200
        with pytest.raises(IOLimitError) as exc_info:
            check_request_size(data, 100)
        error_msg = str(exc_info.value)
        assert "200" in error_msg
        assert "100" in error_msg

    def test_string_utf8_encoding_counted(self) -> None:
        # Each emoji is 4 bytes in UTF-8
        emoji = "\U0001F600" * 30  # 30 * 4 = 120 bytes
        with pytest.raises(IOLimitError):
            check_request_size(emoji, 100)

    def test_empty_data_allowed(self) -> None:
        check_request_size(b"", 0)  # 0 bytes <= 0 limit: edge case
        check_request_size(b"", 100)  # Should not raise

    def test_has_correlation_id(self) -> None:
        with pytest.raises(IOLimitError) as exc_info:
            check_request_size(b"x" * 200, 100)
        assert exc_info.value.correlation_id


class TestCheckResponseSize:
    """Tests for check_response_size function."""

    def test_allows_within_limit_bytes(self) -> None:
        data = b"response" * 10
        check_response_size(data, 1000)  # Should not raise

    def test_allows_within_limit_string(self) -> None:
        data = "response" * 10
        check_response_size(data, 1000)  # Should not raise

    def test_raises_when_exceeds_limit(self) -> None:
        data = b"x" * 500
        with pytest.raises(IOLimitError) as exc_info:
            check_response_size(data, 100)
        assert exc_info.value.code == "RESPONSE_TOO_LARGE"

    def test_exactly_at_limit_is_allowed(self) -> None:
        data = b"x" * 100
        check_response_size(data, 100)  # Should not raise

    def test_error_includes_sizes(self) -> None:
        data = b"x" * 500
        with pytest.raises(IOLimitError) as exc_info:
            check_response_size(data, 100)
        error_msg = str(exc_info.value)
        assert "500" in error_msg
        assert "100" in error_msg
