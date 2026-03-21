"""Unit tests for mcp_chassis.extensions module."""

from pathlib import Path
from unittest.mock import patch

from mcp_chassis.extensions import _check_file_permissions


class TestFilePermissionsPlatformCheck:
    """Tests for platform-aware file permissions checking."""

    def test_windows_skips_permission_check(self, tmp_path: Path) -> None:
        """On Windows, _check_file_permissions should return True (skip check)."""
        test_file = tmp_path / "ext.py"
        test_file.write_text("# extension")
        with patch("mcp_chassis.extensions.sys") as mock_sys:
            mock_sys.platform = "win32"
            assert _check_file_permissions(test_file) is True

    def test_non_windows_checks_permissions(self, tmp_path: Path) -> None:
        """On non-Windows, _check_file_permissions should check S_IWOTH."""
        test_file = tmp_path / "ext.py"
        test_file.write_text("# extension")
        # File created by tmp_path won't be world-writable, so should pass
        with patch("mcp_chassis.extensions.sys") as mock_sys:
            mock_sys.platform = "linux"
            assert _check_file_permissions(test_file) is True
