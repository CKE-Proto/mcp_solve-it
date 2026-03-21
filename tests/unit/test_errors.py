"""Unit tests for mcp_chassis.errors module."""


from mcp_chassis.errors import (
    AuthError,
    ExtensionError,
    IOLimitError,
    RateLimitError,
    SanitizationError,
    ChassisError,
    ValidationError,
)


class TestChassisError:
    """Tests for ChassisError base class."""

    def test_has_correlation_id(self) -> None:
        err = ChassisError("test message", "TEST_CODE")
        assert hasattr(err, "correlation_id")
        assert len(err.correlation_id) == 12

    def test_correlation_id_is_hex(self) -> None:
        err = ChassisError("msg", "CODE")
        int(err.correlation_id, 16)  # Should not raise

    def test_has_code(self) -> None:
        err = ChassisError("msg", "MY_CODE")
        assert err.code == "MY_CODE"

    def test_str_includes_correlation_id(self) -> None:
        err = ChassisError("test message", "CODE")
        assert err.correlation_id in str(err)

    def test_unique_correlation_ids(self) -> None:
        err1 = ChassisError("msg", "C")
        err2 = ChassisError("msg", "C")
        assert err1.correlation_id != err2.correlation_id

    def test_is_exception(self) -> None:
        err = ChassisError("msg", "C")
        assert isinstance(err, Exception)


class TestValidationError:
    """Tests for ValidationError."""

    def test_default_code(self) -> None:
        err = ValidationError("bad input")
        assert err.code == "VALIDATION_ERROR"

    def test_custom_code(self) -> None:
        err = ValidationError("msg", "CUSTOM")
        assert err.code == "CUSTOM"

    def test_is_template_error(self) -> None:
        err = ValidationError("msg")
        assert isinstance(err, ChassisError)

    def test_message(self) -> None:
        err = ValidationError("field X is invalid")
        assert "field X is invalid" in str(err)


class TestSanitizationError:
    """Tests for SanitizationError."""

    def test_default_code(self) -> None:
        err = SanitizationError("bad input")
        assert err.code == "SANITIZATION_ERROR"

    def test_is_template_error(self) -> None:
        assert isinstance(SanitizationError("msg"), ChassisError)


class TestRateLimitError:
    """Tests for RateLimitError."""

    def test_default_code(self) -> None:
        err = RateLimitError("too fast")
        assert err.code == "RATE_LIMIT_EXCEEDED"

    def test_retry_after_default(self) -> None:
        err = RateLimitError("too fast")
        assert err.retry_after == 0.0

    def test_retry_after_custom(self) -> None:
        err = RateLimitError("too fast", retry_after=5.5)
        assert err.retry_after == 5.5

    def test_is_template_error(self) -> None:
        assert isinstance(RateLimitError("msg"), ChassisError)


class TestIOLimitError:
    """Tests for IOLimitError."""

    def test_default_code(self) -> None:
        err = IOLimitError("too big")
        assert err.code == "IO_LIMIT_EXCEEDED"

    def test_is_template_error(self) -> None:
        assert isinstance(IOLimitError("msg"), ChassisError)


class TestAuthError:
    """Tests for AuthError."""

    def test_default_code(self) -> None:
        err = AuthError("unauthorized")
        assert err.code == "AUTH_ERROR"

    def test_is_template_error(self) -> None:
        assert isinstance(AuthError("msg"), ChassisError)


class TestExtensionError:
    """Tests for ExtensionError."""

    def test_default_code(self) -> None:
        err = ExtensionError("load failed")
        assert err.code == "EXTENSION_ERROR"

    def test_is_template_error(self) -> None:
        assert isinstance(ExtensionError("msg"), ChassisError)
