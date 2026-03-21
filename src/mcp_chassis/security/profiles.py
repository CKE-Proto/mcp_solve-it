"""Security profile definitions for the MCP Chassis server.

Three named profiles control the default security posture:
- strict (default): most restrictive, suitable for production
- moderate: balanced, suitable for development environments
- permissive: minimal restrictions, suitable for testing only
"""

import copy
from typing import Any

# Profile definitions as plain dicts matching the TOML config structure
PROFILES: dict[str, dict[str, Any]] = {
    "strict": {
        "rate_limits": {
            "enabled": True,
            "global_rpm": 60,
            "per_tool_rpm": 30,
            "burst_size": 10,
        },
        "io_limits": {
            "max_request_size": 1_048_576,   # 1 MB
            "max_response_size": 5_242_880,  # 5 MB
        },
        "input_validation": {
            "enabled": True,
            "max_string_length": 10_000,
            "max_array_length": 100,
            "max_object_depth": 10,
        },
        "input_sanitization": {
            "enabled": True,
            "level": "strict",
        },
        # Auth is disabled because the strict profile targets stdio transport,
        # where the OS provides process-level isolation. If you deploy over
        # HTTP transport, auth MUST be enabled — override with:
        #   [security.auth]
        #   enabled = true
        #   provider = "token"
        "auth": {
            "enabled": False,
            "provider": "none",
        },
        "detailed_errors": False,
    },
    "moderate": {
        "rate_limits": {
            "enabled": True,
            "global_rpm": 120,
            "per_tool_rpm": 60,
            "burst_size": 20,
        },
        "io_limits": {
            "max_request_size": 5_242_880,    # 5 MB
            "max_response_size": 20_971_520,  # 20 MB
        },
        "input_validation": {
            "enabled": True,
            "max_string_length": 50_000,
            "max_array_length": 500,
            "max_object_depth": 20,
        },
        "input_sanitization": {
            "enabled": True,
            "level": "moderate",
        },
        # Auth disabled — see strict profile comment for HTTP warning.
        "auth": {
            "enabled": False,
            "provider": "none",
        },
        "detailed_errors": True,
    },
    "permissive": {
        "rate_limits": {
            "enabled": False,
            "global_rpm": 0,
            "per_tool_rpm": 0,
            "burst_size": 0,
        },
        "io_limits": {
            "max_request_size": 52_428_800,  # 50 MB
            "max_response_size": 52_428_800,  # 50 MB
        },
        "input_validation": {
            "enabled": True,
            "max_string_length": 1_000_000,
            "max_array_length": 10_000,
            "max_object_depth": 50,
        },
        "input_sanitization": {
            "enabled": True,
            "level": "permissive",
        },
        # Auth disabled — see strict profile comment for HTTP warning.
        "auth": {
            "enabled": False,
            "provider": "none",
        },
        "detailed_errors": True,
    },
}


def get_profile(name: str) -> dict[str, Any]:
    """Return the profile definition for the given profile name.

    Args:
        name: Profile name ('strict', 'moderate', 'permissive').

    Returns:
        A copy of the profile dict.

    Raises:
        ValueError: If the profile name is not recognized.
    """
    if name not in PROFILES:
        raise ValueError(f"Unknown security profile '{name}'. Valid: {list(PROFILES)}")
    return copy.deepcopy(PROFILES[name])


def merge_profile_with_overrides(
    profile_name: str, overrides: dict[str, Any]
) -> dict[str, Any]:
    """Merge a named profile with user-supplied overrides.

    Profile values serve as defaults; overrides take precedence at the
    sub-key level (one level of nesting). Keys absent from overrides
    retain their profile defaults.

    Args:
        profile_name: Base profile name.
        overrides: User config dict with keys matching profile structure.

    Returns:
        Merged configuration dict.
    """
    result = get_profile(profile_name)
    for section, values in overrides.items():
        if section in result and isinstance(result[section], dict) and isinstance(values, dict):
            # Merge dict sections one level deep: override keys win,
            # profile keys absent from overrides are preserved.
            result[section] = {**result[section], **values}
        else:
            # Scalar values or new sections: override replaces entirely.
            result[section] = values
    return result
