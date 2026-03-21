"""Unit tests for _load_env_file in mcp_chassis.__main__."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mcp_chassis.__main__ import _load_env_file


@pytest.fixture()
def env_file(tmp_path: Path) -> Path:
    """Return a path inside tmp_path for writing .env content."""
    return tmp_path / ".env"


class TestLoadEnvFile:
    """Tests for _load_env_file."""

    def test_simple_key_value(self, env_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env_file.write_text("MY_TEST_KEY=hello\n")
        monkeypatch.delenv("MY_TEST_KEY", raising=False)
        _load_env_file(env_file)
        assert os.environ["MY_TEST_KEY"] == "hello"

    def test_skips_blank_lines(self, env_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env_file.write_text("\nKEY_BLANK=yes\n\n")
        monkeypatch.delenv("KEY_BLANK", raising=False)
        _load_env_file(env_file)
        assert os.environ["KEY_BLANK"] == "yes"

    def test_skips_comment_lines(self, env_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env_file.write_text("# this is a comment\nKEY_COMMENT=yes\n")
        monkeypatch.delenv("KEY_COMMENT", raising=False)
        _load_env_file(env_file)
        assert os.environ["KEY_COMMENT"] == "yes"
        assert "# this is a comment" not in os.environ

    def test_skips_lines_without_equals(
        self, env_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_file.write_text("NO_EQUALS_HERE\nGOOD_KEY=val\n")
        monkeypatch.delenv("GOOD_KEY", raising=False)
        _load_env_file(env_file)
        assert os.environ["GOOD_KEY"] == "val"

    def test_strips_double_quotes(
        self, env_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_file.write_text('QUOTED_KEY="quoted value"\n')
        monkeypatch.delenv("QUOTED_KEY", raising=False)
        _load_env_file(env_file)
        assert os.environ["QUOTED_KEY"] == "quoted value"

    def test_strips_single_quotes(
        self, env_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_file.write_text("SINGLE_Q='single quoted'\n")
        monkeypatch.delenv("SINGLE_Q", raising=False)
        _load_env_file(env_file)
        assert os.environ["SINGLE_Q"] == "single quoted"

    def test_does_not_override_existing_env(
        self, env_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_file.write_text("EXISTING_KEY=from_file\n")
        monkeypatch.setenv("EXISTING_KEY", "already_set")
        _load_env_file(env_file)
        assert os.environ["EXISTING_KEY"] == "already_set"

    def test_strips_export_prefix(
        self, env_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_file.write_text("export EXPORTED_KEY=exported_val\n")
        monkeypatch.delenv("EXPORTED_KEY", raising=False)
        _load_env_file(env_file)
        assert os.environ["EXPORTED_KEY"] == "exported_val"

    def test_value_with_equals_sign(
        self, env_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_file.write_text("URL_KEY=https://example.com?a=1&b=2\n")
        monkeypatch.delenv("URL_KEY", raising=False)
        _load_env_file(env_file)
        assert os.environ["URL_KEY"] == "https://example.com?a=1&b=2"

    def test_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            _load_env_file(tmp_path / "nonexistent.env")

    def test_multiple_keys(self, env_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env_file.write_text("MULTI_A=one\nMULTI_B=two\nMULTI_C=three\n")
        for key in ("MULTI_A", "MULTI_B", "MULTI_C"):
            monkeypatch.delenv(key, raising=False)
        _load_env_file(env_file)
        assert os.environ["MULTI_A"] == "one"
        assert os.environ["MULTI_B"] == "two"
        assert os.environ["MULTI_C"] == "three"

    def test_empty_value(self, env_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env_file.write_text("EMPTY_KEY=\n")
        monkeypatch.delenv("EMPTY_KEY", raising=False)
        _load_env_file(env_file)
        assert os.environ["EMPTY_KEY"] == ""

    def test_whitespace_around_key_and_value(
        self, env_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_file.write_text("  SPACED_KEY  =  spaced_value  \n")
        monkeypatch.delenv("SPACED_KEY", raising=False)
        _load_env_file(env_file)
        assert os.environ["SPACED_KEY"] == "spaced_value"
