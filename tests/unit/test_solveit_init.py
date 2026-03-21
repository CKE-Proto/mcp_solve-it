"""Tests for the SOLVE-IT init hook."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mcp_chassis.extensions.solveit_init import on_init

_SOLVEIT_PATH = str(
    (Path(__file__).resolve().parents[3] / "solve-it" / "solve-it-main").resolve()
)


def _make_server(app_config: dict | None = None) -> MagicMock:
    server = MagicMock()
    server._config = MagicMock()
    server._config.app = app_config or {}
    return server


class TestOnInitSuccess:
    def test_kb_attached_to_server(self) -> None:
        server = _make_server({"solveit_data_path": _SOLVEIT_PATH})
        on_init(server)
        assert server._kb is not None
        assert hasattr(server._kb, "get_technique")

    def test_kb_has_techniques(self) -> None:
        server = _make_server({"solveit_data_path": _SOLVEIT_PATH})
        on_init(server)
        assert len(server._kb.list_techniques()) > 0

    def test_kb_has_weaknesses(self) -> None:
        server = _make_server({"solveit_data_path": _SOLVEIT_PATH})
        on_init(server)
        assert len(server._kb.list_weaknesses()) > 0

    def test_kb_has_mitigations(self) -> None:
        server = _make_server({"solveit_data_path": _SOLVEIT_PATH})
        on_init(server)
        assert len(server._kb.list_mitigations()) > 0

    def test_no_kb_error_on_success(self) -> None:
        server = _make_server({"solveit_data_path": _SOLVEIT_PATH})
        on_init(server)
        assert server._kb_error is None

    def test_custom_objective_mapping(self) -> None:
        server = _make_server({
            "solveit_data_path": _SOLVEIT_PATH,
            "objective_mapping": "solve-it.json",
        })
        on_init(server)
        assert server._kb is not None


class TestOnInitFailureDegradedMode:
    """Tests for KB load failure with init_required=False (degraded mode)."""

    def test_bad_path_sets_kb_none(self) -> None:
        server = _make_server({
            "solveit_data_path": "/nonexistent/path",
            "init_required": False,
        })
        on_init(server)
        assert server._kb is None

    def test_bad_path_sets_error_message(self) -> None:
        server = _make_server({
            "solveit_data_path": "/nonexistent/path",
            "init_required": False,
        })
        on_init(server)
        assert server._kb_error is not None
        assert isinstance(server._kb_error, str)
        assert len(server._kb_error) > 0

    def test_bad_path_logs_error(self, caplog: pytest.LogCaptureFixture) -> None:
        server = _make_server({
            "solveit_data_path": "/nonexistent/path",
            "init_required": False,
        })
        with caplog.at_level(logging.ERROR):
            on_init(server)
        assert any("failed" in r.message.lower() or "error" in r.message.lower()
                    for r in caplog.records)


class TestOnInitFailureRequired:
    """Tests for KB load failure with init_required=True (default — exits)."""

    def test_bad_path_exits_by_default(self) -> None:
        server = _make_server({"solveit_data_path": "/nonexistent/path"})
        with pytest.raises(SystemExit) as exc_info:
            on_init(server)
        assert exc_info.value.code == 1

    def test_bad_path_exits_with_explicit_true(self) -> None:
        server = _make_server({
            "solveit_data_path": "/nonexistent/path",
            "init_required": True,
        })
        with pytest.raises(SystemExit) as exc_info:
            on_init(server)
        assert exc_info.value.code == 1

    def test_exit_still_sets_kb_error(self) -> None:
        server = _make_server({"solveit_data_path": "/nonexistent/path"})
        with pytest.raises(SystemExit):
            on_init(server)
        assert server._kb is None
        assert server._kb_error is not None


class TestEnvVarOverrides:
    """Tests for MCP_APP_* environment variable overrides."""

    def test_env_overrides_data_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_APP_SOLVEIT_DATA_PATH", _SOLVEIT_PATH)
        server = _make_server({})  # no TOML config — env var provides the path
        on_init(server)
        assert server._kb is not None

    def test_env_overrides_toml(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_APP_SOLVEIT_DATA_PATH", _SOLVEIT_PATH)
        # TOML has a bad path, but env var should win
        server = _make_server({"solveit_data_path": "/bad/toml/path"})
        on_init(server)
        assert server._kb is not None

    def test_env_overrides_init_required(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_APP_INIT_REQUIRED", "false")
        # Bad path + init_required=true in TOML, but env var sets false
        server = _make_server({
            "solveit_data_path": "/nonexistent/path",
            "init_required": True,
        })
        on_init(server)  # should NOT exit because env var overrides to false
        assert server._kb is None

    def test_env_override_bool_true_variants(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for truthy in ("true", "True", "TRUE", "1", "yes"):
            monkeypatch.setenv("MCP_APP_INIT_REQUIRED", truthy)
            server = _make_server({
                "solveit_data_path": "/nonexistent/path",
            })
            with pytest.raises(SystemExit):
                on_init(server)

    def test_env_override_bool_false_variants(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for falsy in ("false", "False", "FALSE", "0", "no"):
            monkeypatch.setenv("MCP_APP_INIT_REQUIRED", falsy)
            server = _make_server({
                "solveit_data_path": "/nonexistent/path",
            })
            on_init(server)  # should not exit
            assert server._kb is None

    def test_unset_env_vars_do_not_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MCP_APP_SOLVEIT_DATA_PATH", raising=False)
        server = _make_server({"solveit_data_path": _SOLVEIT_PATH})
        on_init(server)
        assert server._kb is not None


class TestTypedConfig:
    """Tests for SolveItAppConfig validation and typo warnings."""

    def test_app_config_attached_to_server(self) -> None:
        server = _make_server({"solveit_data_path": _SOLVEIT_PATH})
        on_init(server)
        assert hasattr(server, "_app_config")
        assert server._app_config.solveit_data_path == _SOLVEIT_PATH

    def test_unrecognized_key_logs_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        server = _make_server({
            "solveit_data_path": _SOLVEIT_PATH,
            "solvit_data_paht": "/typo",  # intentional typo
        })
        with caplog.at_level(logging.WARNING):
            on_init(server)
        assert any("solvit_data_paht" in r.message for r in caplog.records)

    def test_defaults_applied_for_missing_keys(self) -> None:
        server = _make_server({"solveit_data_path": _SOLVEIT_PATH})
        on_init(server)
        cfg = server._app_config
        assert cfg.objective_mapping == "solve-it.json"
        assert cfg.enable_extensions is True
        assert cfg.init_required is True
        assert cfg.enable_full_detail_tools is False

    def test_search_config_defaults(self) -> None:
        server = _make_server({"solveit_data_path": _SOLVEIT_PATH})
        on_init(server)
        assert server._app_config.search.enable_item_types_filter is True
        assert server._app_config.search.enable_substring_match is True
        assert server._app_config.search.enable_search_logic is True

    def test_search_config_overrides(self) -> None:
        server = _make_server({
            "solveit_data_path": _SOLVEIT_PATH,
            "search": {
                "enable_item_types_filter": False,
                "enable_substring_match": False,
            },
        })
        on_init(server)
        assert server._app_config.search.enable_item_types_filter is False
        assert server._app_config.search.enable_substring_match is False
        assert server._app_config.search.enable_search_logic is True  # default


class TestOnInitExtensions:
    def test_extensions_enabled_by_default(self) -> None:
        server = _make_server({"solveit_data_path": _SOLVEIT_PATH})
        on_init(server)
        assert server._kb is not None

    def test_extensions_disabled(self) -> None:
        server = _make_server({
            "solveit_data_path": _SOLVEIT_PATH,
            "enable_extensions": False,
        })
        on_init(server)
        assert server._kb is not None
