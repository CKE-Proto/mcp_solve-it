"""Configuration loading and validation for the MCP Chassis server.

Config is loaded from a TOML file (stdlib tomllib) with environment variable
overrides using the MCP_ prefix. All settings are exposed as frozen dataclasses.
"""

import copy
import logging
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_VALID_TRANSPORTS = {"stdio"}
_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_VALID_PROFILES = {"strict", "moderate", "permissive"}
_VALID_AUTH_PROVIDERS = {"none", "token"}
_VALID_SANITIZATION_LEVELS = {"strict", "moderate", "permissive"}


@dataclass(frozen=True)
class RateLimitConfig:
    """Rate limiting configuration.

    Attributes:
        enabled: Whether rate limiting is active.
        global_rpm: Global requests per minute across all tools.
        per_tool_rpm: Per-tool requests per minute.
        burst_size: Token bucket burst allowance.
    """

    enabled: bool = True
    global_rpm: int = 60
    per_tool_rpm: int = 30
    burst_size: int = 10


@dataclass(frozen=True)
class IOLimitConfig:
    """I/O size limit configuration.

    Attributes:
        max_request_size: Maximum request payload in bytes.
        max_response_size: Maximum response payload in bytes.
    """

    max_request_size: int = 1_048_576  # 1 MB
    max_response_size: int = 5_242_880  # 5 MB


@dataclass(frozen=True)
class ValidationConfig:
    """Input validation configuration.

    Attributes:
        enabled: Whether input validation is active.
        max_string_length: Maximum length of any string value.
        max_array_length: Maximum number of elements in any array.
        max_object_depth: Maximum nesting depth of objects/arrays.
    """

    enabled: bool = True
    max_string_length: int = 10_000
    max_array_length: int = 100
    max_object_depth: int = 10


@dataclass(frozen=True)
class SanitizationConfig:
    """Input sanitization configuration.

    Attributes:
        enabled: Whether input sanitization is active.
        level: Sanitization strictness level ('strict', 'moderate', 'permissive').
    """

    enabled: bool = True
    level: str = "strict"


@dataclass(frozen=True)
class AuthConfig:
    """Authentication configuration.

    Attributes:
        enabled: Whether authentication is enforced.
        provider: Auth provider type ('none', 'token').
        token: Optional token for TokenAuthProvider (prefer env var).
    """

    enabled: bool = False
    provider: str = "none"
    token: str = ""


@dataclass(frozen=True)
class SecurityConfig:
    """Top-level security configuration.

    Attributes:
        profile: Named security profile.
        rate_limits: Rate limit settings.
        io_limits: I/O size limit settings.
        input_validation: Input validation settings.
        input_sanitization: Input sanitization settings.
        auth: Authentication settings.
        detailed_errors: Whether error responses include internal details.
    """

    profile: str = "strict"
    rate_limits: RateLimitConfig = field(default_factory=RateLimitConfig)
    io_limits: IOLimitConfig = field(default_factory=IOLimitConfig)
    input_validation: ValidationConfig = field(default_factory=ValidationConfig)
    input_sanitization: SanitizationConfig = field(default_factory=SanitizationConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    detailed_errors: bool = False


@dataclass(frozen=True)
class ServerSettings:
    """Core server settings.

    Attributes:
        name: Server display name.
        version: Server version string.
        transport: Transport type ('stdio', 'sse', 'streamable-http').
        log_level: Logging level name.
    """

    name: str = "mcp-chassis-server"
    version: str = "0.1.0"
    transport: str = "stdio"
    log_level: str = "INFO"


@dataclass(frozen=True)
class ExtensionSettings:
    """Extension auto-discovery settings.

    Attributes:
        auto_discover: Whether to auto-discover extensions.
        init_module: Optional Python module to import before extension discovery.
            If set, the module's ``on_init(server)`` function is called to set up
            shared state (e.g., database connections, knowledge base instances)
            that extensions can access via the server instance.
    """

    auto_discover: bool = True
    init_module: str = ""


@dataclass(frozen=True)
class DiagnosticSettings:
    """Diagnostics and health check settings.

    Attributes:
        health_check_enabled: Whether to register the health check tool.
        include_config_summary: Whether health check includes config summary.
    """

    health_check_enabled: bool = True
    include_config_summary: bool = False



@dataclass(frozen=True)
class ServerConfig:
    """Top-level server configuration.

    Attributes:
        server: Core server settings.
        security: Security configuration.
        extensions: Extension discovery settings.
        diagnostics: Diagnostics settings.
        app: Fork-specific configuration pass-through. The ``[app]`` TOML
            section is loaded as a plain dict and made available to init hooks
            and extensions via ``server._config.app``. The template does not
            validate or interpret this section — forks define its structure.
    """

    server: ServerSettings = field(default_factory=ServerSettings)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    extensions: ExtensionSettings = field(default_factory=ExtensionSettings)
    diagnostics: DiagnosticSettings = field(default_factory=DiagnosticSettings)
    app: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, config_path: Path | None = None) -> "ServerConfig":
        """Load configuration from a TOML file with environment variable overrides.

        Config file search order (first match wins):
        1. Explicit ``config_path`` argument (from ``--config`` CLI flag)
        2. ``MCP_CHASSIS_CONFIG`` environment variable
        3. ``./config/default.toml`` relative to the current working directory
        4. ``config/default.toml`` relative to the package source tree (editable installs)

        After the config file is loaded, environment variable overrides (MCP_ prefix)
        are applied on top.

        Args:
            config_path: Optional explicit path to a TOML config file.

        Returns:
            A validated ServerConfig instance.
        """
        raw: dict[str, Any] = {}

        # Determine config file path using search order
        path = config_path
        source = "argument" if path else None

        if path is None:
            env_path = os.environ.get("MCP_CHASSIS_CONFIG")
            if env_path:
                path = Path(env_path)
                source = "MCP_CHASSIS_CONFIG"

        if path is None:
            cwd_default = Path("config") / "default.toml"
            if cwd_default.exists():
                path = cwd_default
                source = "working directory"

        if path is None:
            repo_default = Path(__file__).parent.parent.parent / "config" / "default.toml"
            if repo_default.exists():
                path = repo_default
                source = "package source tree"

        if path is not None:
            if not path.exists():
                raise FileNotFoundError(f"Config file not found: {path}")
            with open(path, "rb") as f:
                raw = tomllib.load(f)
            logger.info("Loaded config from %s (source: %s)", path.resolve(), source)
        else:
            logger.warning(
                "No config file found (searched: --config, MCP_CHASSIS_CONFIG, "
                "./config/default.toml, package source tree). Using built-in defaults."
            )

        raw = _apply_env_overrides(raw)
        return _build_config(raw)

    @classmethod
    def from_profile(cls, profile: str) -> "ServerConfig":
        """Create a configuration using a named security profile as base.

        Args:
            profile: Profile name ('strict', 'moderate', 'permissive').

        Returns:
            A ServerConfig with settings from the named profile.

        Raises:
            ValueError: If the profile name is unknown.
        """
        if profile not in _VALID_PROFILES:
            raise ValueError(f"Unknown profile '{profile}'. Valid: {_VALID_PROFILES}")
        raw: dict[str, Any] = {"security": {"profile": profile}}
        raw = _apply_env_overrides(raw)
        return _build_config(raw)


def _apply_env_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    """Apply MCP_ prefixed environment variable overrides to raw config dict.

    Supported overrides:
    - MCP_LOG_LEVEL → server.log_level
    - MCP_SECURITY_PROFILE → security.profile
    - MCP_AUTH_TOKEN → security.auth.token
    - MCP_RATE_LIMIT_ENABLED → security.rate_limits.enabled

    Args:
        raw: The raw config dictionary (modified in place via copy).

    Returns:
        A new dict with environment variable overrides applied.
    """
    result = copy.deepcopy(raw)

    if val := os.environ.get("MCP_LOG_LEVEL"):
        result.setdefault("server", {})["log_level"] = val

    if val := os.environ.get("MCP_SECURITY_PROFILE"):
        result.setdefault("security", {})["profile"] = val

    if val := os.environ.get("MCP_AUTH_TOKEN"):
        result.setdefault("security", {}).setdefault("auth", {})["token"] = val

    if val := os.environ.get("MCP_RATE_LIMIT_ENABLED"):
        enabled = val.lower() in ("1", "true", "yes")
        result.setdefault("security", {}).setdefault("rate_limits", {})["enabled"] = enabled

    return result


def _check_positive(value: int, name: str) -> None:
    """Raise ValueError if a numeric config value is not positive.

    Args:
        value: The integer value to check.
        name: The config field name (used in the error message).

    Raises:
        ValueError: If value is less than 1.
    """
    if value < 1:
        raise ValueError(f"Config field '{name}' must be >= 1, got {value}")


def _build_config(raw: dict[str, Any]) -> ServerConfig:
    """Build a validated ServerConfig from a raw dict.

    Args:
        raw: Raw configuration dictionary from TOML.

    Returns:
        A validated ServerConfig.

    Raises:
        ValueError: If any config value is invalid.
    """
    server_raw = raw.get("server", {})
    security_raw = raw.get("security", {})
    extensions_raw = raw.get("extensions", {})
    diagnostics_raw = raw.get("diagnostics", {})
    app_raw = raw.get("app", {})

    server = _build_server_settings(server_raw)
    security = _build_security_config(security_raw)
    extensions = _build_extension_settings(extensions_raw)
    diagnostics = _build_diagnostic_settings(diagnostics_raw)

    return ServerConfig(
        server=server,
        security=security,
        extensions=extensions,
        diagnostics=diagnostics,
        app=app_raw,
    )


def _build_server_settings(raw: dict[str, Any]) -> ServerSettings:
    """Build ServerSettings from a raw dict, validating values.

    Args:
        raw: Raw server section dict.

    Returns:
        Validated ServerSettings.

    Raises:
        ValueError: If transport or log_level is invalid.
    """
    transport = raw.get("transport", "stdio")
    if transport not in _VALID_TRANSPORTS:
        raise ValueError(f"Invalid transport '{transport}'. Valid: {_VALID_TRANSPORTS}")

    log_level = raw.get("log_level", "INFO").upper()
    if log_level not in _VALID_LOG_LEVELS:
        raise ValueError(f"Invalid log_level '{log_level}'. Valid: {_VALID_LOG_LEVELS}")

    return ServerSettings(
        name=str(raw.get("name", "mcp-chassis-server")),
        version=str(raw.get("version", "0.1.0")),
        transport=transport,
        log_level=log_level,
    )


def _build_security_config(raw: dict[str, Any]) -> SecurityConfig:
    """Build SecurityConfig from a raw dict.

    Args:
        raw: Raw security section dict.

    Returns:
        Validated SecurityConfig.

    Raises:
        ValueError: If profile is invalid.
    """
    from mcp_chassis.security.profiles import get_profile

    profile = raw.get("profile", "strict")
    if profile not in _VALID_PROFILES:
        raise ValueError(f"Invalid profile '{profile}'. Valid: {_VALID_PROFILES}")

    # Seed defaults from the named profile, then apply any explicit overrides
    profile_defaults = get_profile(profile)
    rl_raw = {**profile_defaults.get("rate_limits", {}), **raw.get("rate_limits", {})}
    io_raw = {**profile_defaults.get("io_limits", {}), **raw.get("io_limits", {})}
    val_raw = {**profile_defaults.get("input_validation", {}), **raw.get("input_validation", {})}
    san_defaults = profile_defaults.get("input_sanitization", {})
    san_raw = {**san_defaults, **raw.get("input_sanitization", {})}
    auth_raw = {**profile_defaults.get("auth", {}), **raw.get("auth", {})}

    # detailed_errors: profile default, overridable by user config
    detailed_errors_default = profile_defaults.get("detailed_errors", False)
    detailed_errors = bool(raw.get("detailed_errors", detailed_errors_default))

    rl_enabled = bool(rl_raw.get("enabled", True))
    global_rpm = int(rl_raw.get("global_rpm", 60))
    per_tool_rpm = int(rl_raw.get("per_tool_rpm", 30))
    burst_size = int(rl_raw.get("burst_size", 10))
    if rl_enabled:
        _check_positive(global_rpm, "global_rpm")
        _check_positive(per_tool_rpm, "per_tool_rpm")
        _check_positive(burst_size, "burst_size")

    rate_limits = RateLimitConfig(
        enabled=rl_enabled,
        global_rpm=global_rpm,
        per_tool_rpm=per_tool_rpm,
        burst_size=burst_size,
    )

    max_request_size = int(io_raw.get("max_request_size", 1_048_576))
    max_response_size = int(io_raw.get("max_response_size", 5_242_880))
    _check_positive(max_request_size, "max_request_size")
    _check_positive(max_response_size, "max_response_size")

    io_limits = IOLimitConfig(
        max_request_size=max_request_size,
        max_response_size=max_response_size,
    )

    max_string_length = int(val_raw.get("max_string_length", 10_000))
    max_array_length = int(val_raw.get("max_array_length", 100))
    max_object_depth = int(val_raw.get("max_object_depth", 10))
    _check_positive(max_string_length, "max_string_length")
    _check_positive(max_array_length, "max_array_length")
    _check_positive(max_object_depth, "max_object_depth")

    validation = ValidationConfig(
        enabled=bool(val_raw.get("enabled", True)),
        max_string_length=max_string_length,
        max_array_length=max_array_length,
        max_object_depth=max_object_depth,
    )

    san_level = san_raw.get("level", "strict")
    if san_level not in _VALID_SANITIZATION_LEVELS:
        raise ValueError(
            f"Invalid sanitization level '{san_level}'. Valid: {_VALID_SANITIZATION_LEVELS}"
        )

    sanitization = SanitizationConfig(
        enabled=bool(san_raw.get("enabled", True)),
        level=san_level,
    )

    auth_provider = auth_raw.get("provider", "none")
    if auth_provider not in _VALID_AUTH_PROVIDERS:
        raise ValueError(
            f"Invalid auth provider '{auth_provider}'. Valid: {_VALID_AUTH_PROVIDERS}"
        )

    auth = AuthConfig(
        enabled=bool(auth_raw.get("enabled", False)),
        provider=auth_provider,
        token=str(auth_raw.get("token", "")),
    )

    return SecurityConfig(
        profile=profile,
        rate_limits=rate_limits,
        io_limits=io_limits,
        input_validation=validation,
        input_sanitization=sanitization,
        auth=auth,
        detailed_errors=detailed_errors,
    )


def _build_extension_settings(raw: dict[str, Any]) -> ExtensionSettings:
    """Build ExtensionSettings from a raw dict.

    Args:
        raw: Raw extensions section dict.

    Returns:
        ExtensionSettings.
    """
    return ExtensionSettings(
        auto_discover=bool(raw.get("auto_discover", True)),
        init_module=str(raw.get("init_module", "")),
    )


def _build_diagnostic_settings(raw: dict[str, Any]) -> DiagnosticSettings:
    """Build DiagnosticSettings from a raw dict.

    Args:
        raw: Raw diagnostics section dict.

    Returns:
        DiagnosticSettings.
    """
    return DiagnosticSettings(
        health_check_enabled=bool(raw.get("health_check_enabled", True)),
        include_config_summary=bool(raw.get("include_config_summary", False)),
    )


