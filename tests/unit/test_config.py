"""Unit tests for mcp_chassis.config module."""

import os
from pathlib import Path
from typing import Any

import pytest

from mcp_chassis.config import (
    ServerConfig,
    ServerSettings,
)


class TestServerConfigDefaults:
    """Tests for default configuration values."""

    def test_default_server_name(self) -> None:
        config = ServerConfig()
        assert config.server.name == "mcp-chassis-server"

    def test_default_transport(self) -> None:
        config = ServerConfig()
        assert config.server.transport == "stdio"

    def test_default_log_level(self) -> None:
        config = ServerConfig()
        assert config.server.log_level == "INFO"

    def test_default_security_profile(self) -> None:
        config = ServerConfig()
        assert config.security.profile == "strict"

    def test_default_rate_limits_enabled(self) -> None:
        config = ServerConfig()
        assert config.security.rate_limits.enabled is True

    def test_default_auth_disabled(self) -> None:
        config = ServerConfig()
        assert config.security.auth.enabled is False

    def test_frozen_config(self) -> None:
        config = ServerConfig()
        with pytest.raises((AttributeError, TypeError)):
            config.server = ServerSettings()  # type: ignore[misc]


class TestServerConfigLoad:
    """Tests for loading configuration from TOML files."""

    def test_load_from_toml(self, tmp_path: Path) -> None:
        toml_content = b"""
[server]
name = "my-server"
log_level = "DEBUG"

[security]
profile = "moderate"
"""
        config_file = tmp_path / "config.toml"
        config_file.write_bytes(toml_content)
        config = ServerConfig.load(config_file)
        assert config.server.name == "my-server"
        assert config.server.log_level == "DEBUG"
        assert config.security.profile == "moderate"

    def test_load_nonexistent_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            ServerConfig.load(tmp_path / "nonexistent.toml")

    def test_load_defaults_without_file(self) -> None:
        # Load without specifying a file — falls back to defaults if default.toml is present
        # or returns default config otherwise
        config = ServerConfig.load(None)
        assert config.server.transport == "stdio"

    def test_load_full_security_section(self, tmp_path: Path) -> None:
        toml_content = b"""
[security]
profile = "permissive"

[security.rate_limits]
enabled = false
global_rpm = 200

[security.io_limits]
max_request_size = 2097152
"""
        config_file = tmp_path / "config.toml"
        config_file.write_bytes(toml_content)
        config = ServerConfig.load(config_file)
        assert config.security.profile == "permissive"
        assert config.security.rate_limits.enabled is False
        assert config.security.rate_limits.global_rpm == 200
        assert config.security.io_limits.max_request_size == 2_097_152

    def test_invalid_transport_raises(self, tmp_path: Path) -> None:
        toml_content = b"""
[server]
transport = "invalid-transport"
"""
        config_file = tmp_path / "config.toml"
        config_file.write_bytes(toml_content)
        with pytest.raises(ValueError, match="Invalid transport"):
            ServerConfig.load(config_file)

    def test_invalid_log_level_raises(self, tmp_path: Path) -> None:
        toml_content = b"""
[server]
log_level = "VERBOSE"
"""
        config_file = tmp_path / "config.toml"
        config_file.write_bytes(toml_content)
        with pytest.raises(ValueError, match="Invalid log_level"):
            ServerConfig.load(config_file)

    def test_invalid_profile_raises(self, tmp_path: Path) -> None:
        toml_content = b"""
[security]
profile = "ultra-strict"
"""
        config_file = tmp_path / "config.toml"
        config_file.write_bytes(toml_content)
        with pytest.raises(ValueError, match="Invalid profile"):
            ServerConfig.load(config_file)


class TestEnvVarOverrides:
    """Tests for environment variable overrides."""

    def test_log_level_override(self, tmp_path: Path) -> None:
        toml_content = b"[server]\nlog_level = 'INFO'\n"
        config_file = tmp_path / "c.toml"
        config_file.write_bytes(toml_content)
        os.environ["MCP_LOG_LEVEL"] = "DEBUG"
        try:
            config = ServerConfig.load(config_file)
            assert config.server.log_level == "DEBUG"
        finally:
            del os.environ["MCP_LOG_LEVEL"]

    def test_security_profile_override(self, tmp_path: Path) -> None:
        toml_content = b"[security]\nprofile = 'strict'\n"
        config_file = tmp_path / "c.toml"
        config_file.write_bytes(toml_content)
        os.environ["MCP_SECURITY_PROFILE"] = "permissive"
        try:
            config = ServerConfig.load(config_file)
            assert config.security.profile == "permissive"
        finally:
            del os.environ["MCP_SECURITY_PROFILE"]

    def test_auth_token_override(self, tmp_path: Path) -> None:
        toml_content = b"[security.auth]\nprovider = 'token'\nenabled = true\n"
        config_file = tmp_path / "c.toml"
        config_file.write_bytes(toml_content)
        os.environ["MCP_AUTH_TOKEN"] = "secret-token-123"
        try:
            config = ServerConfig.load(config_file)
            assert config.security.auth.token == "secret-token-123"
        finally:
            del os.environ["MCP_AUTH_TOKEN"]

    def test_rate_limit_disabled_override(self, tmp_path: Path) -> None:
        toml_content = b"[security.rate_limits]\nenabled = true\n"
        config_file = tmp_path / "c.toml"
        config_file.write_bytes(toml_content)
        os.environ["MCP_RATE_LIMIT_ENABLED"] = "false"
        try:
            config = ServerConfig.load(config_file)
            assert config.security.rate_limits.enabled is False
        finally:
            del os.environ["MCP_RATE_LIMIT_ENABLED"]

    def test_template_config_env_var(self, tmp_path: Path) -> None:
        toml_content = b"[server]\nname = 'env-configured-server'\n"
        config_file = tmp_path / "c.toml"
        config_file.write_bytes(toml_content)
        os.environ["MCP_CHASSIS_CONFIG"] = str(config_file)
        try:
            config = ServerConfig.load(None)
            assert config.server.name == "env-configured-server"
        finally:
            del os.environ["MCP_CHASSIS_CONFIG"]


class TestConfigFileSearchOrder:
    """Tests for config file search order: --config, env var, CWD, repo-relative."""

    def test_cwd_config_found(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Config at ./config/default.toml is found when no explicit path or env var."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "default.toml"
        config_file.write_bytes(b"[server]\nname = 'cwd-server'\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("MCP_CHASSIS_CONFIG", raising=False)
        config = ServerConfig.load(None)
        assert config.server.name == "cwd-server"

    def test_env_var_takes_priority_over_cwd(self, tmp_path: Path, monkeypatch: Any) -> None:
        """MCP_CHASSIS_CONFIG takes priority over CWD config."""
        # Set up CWD config
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "default.toml").write_bytes(b"[server]\nname = 'cwd-server'\n")
        monkeypatch.chdir(tmp_path)

        # Set up env var config in a different location
        env_config = tmp_path / "env-config.toml"
        env_config.write_bytes(b"[server]\nname = 'env-server'\n")
        monkeypatch.setenv("MCP_CHASSIS_CONFIG", str(env_config))

        config = ServerConfig.load(None)
        assert config.server.name == "env-server"

    def test_explicit_path_takes_priority_over_all(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """--config argument takes priority over env var and CWD."""
        # Set up env var
        env_config = tmp_path / "env-config.toml"
        env_config.write_bytes(b"[server]\nname = 'env-server'\n")
        monkeypatch.setenv("MCP_CHASSIS_CONFIG", str(env_config))

        # Explicit path
        explicit = tmp_path / "explicit.toml"
        explicit.write_bytes(b"[server]\nname = 'explicit-server'\n")

        config = ServerConfig.load(explicit)
        assert config.server.name == "explicit-server"

    def test_no_config_anywhere_uses_defaults(self, tmp_path: Path, monkeypatch: Any) -> None:
        """When no config file exists anywhere, dataclass defaults are used."""
        monkeypatch.chdir(tmp_path)  # empty dir, no config/default.toml
        monkeypatch.delenv("MCP_CHASSIS_CONFIG", raising=False)
        config = ServerConfig.load(None)
        # Should get the name from the package's bundled default.toml
        assert config.server.name == "solveit-mcp"


class TestNumericConfigValidation:
    """Tests that non-positive numeric config values are rejected at load time."""

    @pytest.mark.parametrize(
        "field",
        ["global_rpm", "per_tool_rpm", "burst_size"],
    )
    def test_zero_rate_limit_field_raises(self, tmp_path: Path, field: str) -> None:
        toml_content = f"[security.rate_limits]\n{field} = 0\n".encode()
        config_file = tmp_path / "c.toml"
        config_file.write_bytes(toml_content)
        with pytest.raises(ValueError, match=field):
            ServerConfig.load(config_file)

    @pytest.mark.parametrize(
        "field",
        ["global_rpm", "per_tool_rpm", "burst_size"],
    )
    def test_negative_rate_limit_field_raises(self, tmp_path: Path, field: str) -> None:
        toml_content = f"[security.rate_limits]\n{field} = -1\n".encode()
        config_file = tmp_path / "c.toml"
        config_file.write_bytes(toml_content)
        with pytest.raises(ValueError, match=field):
            ServerConfig.load(config_file)

    @pytest.mark.parametrize(
        "field",
        ["max_request_size", "max_response_size"],
    )
    def test_zero_io_limit_raises(self, tmp_path: Path, field: str) -> None:
        toml_content = f"[security.io_limits]\n{field} = 0\n".encode()
        config_file = tmp_path / "c.toml"
        config_file.write_bytes(toml_content)
        with pytest.raises(ValueError, match=field):
            ServerConfig.load(config_file)

    @pytest.mark.parametrize(
        "field",
        ["max_request_size", "max_response_size"],
    )
    def test_negative_io_limit_raises(self, tmp_path: Path, field: str) -> None:
        toml_content = f"[security.io_limits]\n{field} = -5\n".encode()
        config_file = tmp_path / "c.toml"
        config_file.write_bytes(toml_content)
        with pytest.raises(ValueError, match=field):
            ServerConfig.load(config_file)

    @pytest.mark.parametrize(
        "field",
        ["max_string_length", "max_array_length", "max_object_depth"],
    )
    def test_zero_validation_limit_raises(self, tmp_path: Path, field: str) -> None:
        toml_content = f"[security.input_validation]\n{field} = 0\n".encode()
        config_file = tmp_path / "c.toml"
        config_file.write_bytes(toml_content)
        with pytest.raises(ValueError, match=field):
            ServerConfig.load(config_file)

    @pytest.mark.parametrize(
        "field",
        ["max_string_length", "max_array_length", "max_object_depth"],
    )
    def test_negative_validation_limit_raises(self, tmp_path: Path, field: str) -> None:
        toml_content = f"[security.input_validation]\n{field} = -10\n".encode()
        config_file = tmp_path / "c.toml"
        config_file.write_bytes(toml_content)
        with pytest.raises(ValueError, match=field):
            ServerConfig.load(config_file)

    @pytest.mark.parametrize(
        "field",
        ["global_rpm", "per_tool_rpm", "burst_size"],
    )
    def test_zero_rate_limit_allowed_when_disabled(self, tmp_path: Path, field: str) -> None:
        """Zero rate limit values are fine when rate limiting is disabled."""
        toml_content = f"[security.rate_limits]\nenabled = false\n{field} = 0\n".encode()
        config_file = tmp_path / "c.toml"
        config_file.write_bytes(toml_content)
        config = ServerConfig.load(config_file)
        assert config.security.rate_limits.enabled is False

    def test_positive_values_accepted(self, tmp_path: Path) -> None:
        """Positive values for all numeric fields should load without error."""
        toml_content = b"""
[security.rate_limits]
global_rpm = 1
per_tool_rpm = 1
burst_size = 1

[security.io_limits]
max_request_size = 1
max_response_size = 1

[security.input_validation]
max_string_length = 1
max_array_length = 1
max_object_depth = 1
"""
        config_file = tmp_path / "c.toml"
        config_file.write_bytes(toml_content)
        config = ServerConfig.load(config_file)
        assert config.security.rate_limits.global_rpm == 1
        assert config.security.io_limits.max_request_size == 1
        assert config.security.input_validation.max_string_length == 1


class TestFromProfile:
    """Tests for ServerConfig.from_profile class method."""

    def test_strict_profile(self) -> None:
        config = ServerConfig.from_profile("strict")
        assert config.security.profile == "strict"

    def test_moderate_profile(self) -> None:
        config = ServerConfig.from_profile("moderate")
        assert config.security.profile == "moderate"

    def test_permissive_profile(self) -> None:
        config = ServerConfig.from_profile("permissive")
        assert config.security.profile == "permissive"

    def test_unknown_profile_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown profile"):
            ServerConfig.from_profile("unknown")

    def test_from_profile_applies_log_level_env_override(self) -> None:
        os.environ["MCP_LOG_LEVEL"] = "DEBUG"
        try:
            config = ServerConfig.from_profile("strict")
            assert config.server.log_level == "DEBUG"
        finally:
            del os.environ["MCP_LOG_LEVEL"]

    def test_from_profile_applies_auth_token_env_override(self) -> None:
        os.environ["MCP_AUTH_TOKEN"] = "env-secret"
        try:
            config = ServerConfig.from_profile("strict")
            assert config.security.auth.token == "env-secret"
        finally:
            del os.environ["MCP_AUTH_TOKEN"]

    def test_from_profile_applies_rate_limit_env_override(self) -> None:
        os.environ["MCP_RATE_LIMIT_ENABLED"] = "false"
        try:
            config = ServerConfig.from_profile("strict")
            assert config.security.rate_limits.enabled is False
        finally:
            del os.environ["MCP_RATE_LIMIT_ENABLED"]

    def test_from_profile_applies_security_profile_env_override(self) -> None:
        os.environ["MCP_SECURITY_PROFILE"] = "permissive"
        try:
            config = ServerConfig.from_profile("strict")
            assert config.security.profile == "permissive"
        finally:
            del os.environ["MCP_SECURITY_PROFILE"]


class TestAppConfig:
    """Tests for the generic [app] configuration pass-through."""

    def test_app_section_loaded_from_toml(self, tmp_path: Path) -> None:
        """[app] section passes through as a dict."""
        toml_content = b"""
[app]
base_path = "/data/projects"
mapping_file = "custom-map.json"
enable_extensions = false
threshold = 42
"""
        config_file = tmp_path / "c.toml"
        config_file.write_bytes(toml_content)
        config = ServerConfig.load(config_file)
        assert config.app["base_path"] == "/data/projects"
        assert config.app["mapping_file"] == "custom-map.json"
        assert config.app["enable_extensions"] is False
        assert config.app["threshold"] == 42

    def test_app_defaults_to_empty_dict(self) -> None:
        """ServerConfig() has an empty app dict by default."""
        config = ServerConfig()
        assert config.app == {}

    def test_app_nested_tables(self, tmp_path: Path) -> None:
        """[app] supports nested TOML tables."""
        toml_content = b"""
[app]
name = "my-fork"

[app.database]
host = "localhost"
port = 5432
"""
        config_file = tmp_path / "c.toml"
        config_file.write_bytes(toml_content)
        config = ServerConfig.load(config_file)
        assert config.app["name"] == "my-fork"
        assert config.app["database"]["host"] == "localhost"
        assert config.app["database"]["port"] == 5432

    def test_app_preserved_through_from_profile(self) -> None:
        """from_profile() includes an empty app dict."""
        config = ServerConfig.from_profile("strict")
        assert config.app == {}
