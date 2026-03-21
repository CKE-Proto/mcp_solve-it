"""Unit tests for mcp_chassis.security.sanitization module."""

import pytest

from mcp_chassis.errors import SanitizationError
from mcp_chassis.security.sanitization import sanitize_input


class TestStrictSanitization:
    """Tests for strict sanitization level."""

    def test_removes_null_bytes(self) -> None:
        result = sanitize_input("hello\x00world", "strict")
        assert "\x00" not in result

    def test_removes_control_chars(self) -> None:
        result = sanitize_input("hello\x01\x02\x03world", "strict")
        assert "\x01" not in result
        assert "\x02" not in result
        assert "\x03" not in result

    def test_preserves_tab_and_cr(self) -> None:
        result = sanitize_input("line1\ttabbed\r", "strict")
        assert "\t" in result
        assert "\r" in result

    def test_strips_newline_as_shell_metachar(self) -> None:
        """Newline is stripped in strict mode (command separator in shell)."""
        result = sanitize_input("line1\nline2", "strict")
        assert "\n" not in result

    def test_removes_path_traversal(self) -> None:
        result = sanitize_input("path/../secret", "strict")
        assert "../" not in result

    def test_removes_path_traversal_backslash(self) -> None:
        result = sanitize_input("path\\..\\secret", "strict")
        assert "..\\" not in result

    def test_removes_stacked_path_traversal(self) -> None:
        """....// collapses to ../ after one pass — must be caught."""
        result = sanitize_input("path/....//secret", "strict")
        assert "../" not in result
        assert ".." not in result

    def test_removes_deeply_stacked_path_traversal(self) -> None:
        """Multiple layers of stacking."""
        result = sanitize_input("......///secret", "strict")
        assert "../" not in result

    def test_removes_url_encoded_path_traversal(self) -> None:
        """%2e%2e%2f is ../ percent-encoded."""
        result = sanitize_input("path/%2e%2e%2fsecret", "strict")
        assert "../" not in result
        assert "%2e" not in result.lower()

    def test_removes_mixed_case_url_encoded_traversal(self) -> None:
        result = sanitize_input("path/%2E%2E%2Fsecret", "strict")
        assert "../" not in result

    def test_removes_url_encoded_backslash_traversal(self) -> None:
        result = sanitize_input("path/%2e%2e%5csecret", "strict")
        assert "..\\" not in result

    def test_removes_stacked_backslash_traversal(self) -> None:
        result = sanitize_input("path\\....\\\\secret", "strict")
        assert "..\\" not in result

    def test_removes_shell_metacharacters(self) -> None:
        dangerous = "cmd; rm -rf / | evil & $PATH `whoami`"
        result = sanitize_input(dangerous, "strict")
        for char in (";", "|", "&", "$", "`"):
            assert char not in result

    def test_removes_quotes(self) -> None:
        """Single and double quotes can break out of shell quoting contexts."""
        result = sanitize_input("""it's a "test" value""", "strict")
        assert "'" not in result
        assert '"' not in result

    def test_removes_tilde(self) -> None:
        """Tilde expands to $HOME in shell contexts."""
        result = sanitize_input("~root/.ssh/authorized_keys", "strict")
        assert "~" not in result

    def test_removes_newline_as_command_separator(self) -> None:
        """Newline acts as a command separator in shell contexts."""
        result = sanitize_input("safe\nrm -rf /", "strict")
        assert "\n" not in result

    def test_plain_string_unchanged(self) -> None:
        result = sanitize_input("Hello World 123", "strict")
        assert result == "Hello World 123"

    def test_normalizes_unicode(self) -> None:
        # NFC normalization should not break normal strings
        result = sanitize_input("café", "strict")
        assert result == "café"

    def test_empty_string(self) -> None:
        result = sanitize_input("", "strict")
        assert result == ""


class TestModerateSanitization:
    """Tests for moderate sanitization level."""

    def test_removes_null_bytes(self) -> None:
        result = sanitize_input("hello\x00world", "moderate")
        assert "\x00" not in result

    def test_removes_control_chars(self) -> None:
        result = sanitize_input("bad\x01char", "moderate")
        assert "\x01" not in result

    def test_removes_path_traversal(self) -> None:
        result = sanitize_input("../etc/passwd", "moderate")
        assert "../" not in result

    def test_removes_stacked_path_traversal(self) -> None:
        result = sanitize_input("....//etc/passwd", "moderate")
        assert "../" not in result

    def test_removes_url_encoded_path_traversal(self) -> None:
        result = sanitize_input("%2e%2e%2fetc/passwd", "moderate")
        assert "../" not in result

    def test_preserves_shell_metacharacters(self) -> None:
        # Moderate does NOT strip shell metacharacters
        result = sanitize_input("cmd | grep foo", "moderate")
        assert "|" in result

    def test_preserves_dollar(self) -> None:
        result = sanitize_input("price: $10", "moderate")
        assert "$" in result


class TestPermissiveSanitization:
    """Tests for permissive sanitization level."""

    def test_removes_only_null_bytes(self) -> None:
        result = sanitize_input("hello\x00world", "permissive")
        assert "\x00" not in result

    def test_preserves_control_chars(self) -> None:
        result = sanitize_input("hello\x01world", "permissive")
        assert "\x01" in result

    def test_preserves_path_traversal(self) -> None:
        result = sanitize_input("path/../file", "permissive")
        assert "../" in result

    def test_preserves_shell_metacharacters(self) -> None:
        result = sanitize_input("cmd; dangerous", "permissive")
        assert ";" in result


class TestRecursiveSanitization:
    """Tests for recursive sanitization of nested structures."""

    def test_sanitizes_dict_values(self) -> None:
        data = {"key": "value\x00"}
        result = sanitize_input(data, "strict")
        assert "\x00" not in result["key"]

    def test_sanitizes_list_elements(self) -> None:
        data = ["clean", "dirty\x00"]
        result = sanitize_input(data, "strict")
        assert "\x00" not in result[1]

    def test_sanitizes_nested_dict(self) -> None:
        data = {"outer": {"inner": "bad\x01char"}}
        result = sanitize_input(data, "strict")
        assert "\x01" not in result["outer"]["inner"]

    def test_non_string_passthrough(self) -> None:
        data = {"count": 42, "ratio": 3.14, "flag": True, "nothing": None}
        result = sanitize_input(data, "strict")
        assert result["count"] == 42
        assert result["ratio"] == 3.14
        assert result["flag"] is True
        assert result["nothing"] is None


class TestDictKeyCollisionDetection:
    """Tests for detecting dict key collisions after sanitization."""

    def test_path_traversal_key_collision_raises(self) -> None:
        """Two keys that collide after path traversal stripping should raise."""
        data = {"path../a": "value1", "patha": "value2"}
        with pytest.raises(SanitizationError, match="patha"):
            sanitize_input(data, "strict")

    def test_path_traversal_key_collision_moderate(self) -> None:
        """Collision detection applies at moderate level too."""
        data = {"path../x": "v1", "pathx": "v2"}
        with pytest.raises(SanitizationError, match="pathx"):
            sanitize_input(data, "moderate")

    def test_shell_metachar_key_collision_raises(self) -> None:
        """Two keys that collide after shell metachar stripping should raise."""
        data = {"file": "safe.txt", "fi;le": "evil.txt"}
        with pytest.raises(SanitizationError, match="file"):
            sanitize_input(data, "strict")

    def test_no_collision_no_error(self) -> None:
        """Distinct keys that remain distinct after sanitization are fine."""
        data = {"alpha": "a", "beta": "b"}
        result = sanitize_input(data, "strict")
        assert result == {"alpha": "a", "beta": "b"}

    def test_single_key_no_collision(self) -> None:
        """A single key can never collide."""
        data = {"path../a": "value"}
        result = sanitize_input(data, "strict")
        assert "patha" in result

    def test_collision_in_nested_dict_raises(self) -> None:
        """Collision detection applies recursively to nested dicts."""
        data = {"outer": {"path../x": "v1", "pathx": "v2"}}
        with pytest.raises(SanitizationError, match="pathx"):
            sanitize_input(data, "strict")

    def test_no_collision_at_permissive_level(self) -> None:
        """Permissive strips only null bytes, so key collision is unlikely.

        Keys containing null bytes that collide should still be caught.
        """
        data = {"ke\x00y": "v1", "key": "v2"}
        with pytest.raises(SanitizationError, match="key"):
            sanitize_input(data, "permissive")

    def test_non_string_keys_ignored(self) -> None:
        """Non-string keys are passed through and cannot collide from sanitization."""
        # JSON dicts have string keys, but Python allows other types
        data = {1: "a", 2: "b"}
        result = sanitize_input(data, "strict")
        assert result == {1: "a", 2: "b"}


class TestInvalidLevel:
    """Tests for invalid sanitization level handling."""

    def test_invalid_level_raises(self) -> None:
        with pytest.raises(SanitizationError):
            sanitize_input("text", "ultra-strict")
