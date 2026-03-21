"""SOLVE-IT init hook — load the KnowledgeBase before extension discovery.

This module is referenced by ``[extensions] init_module`` in config.
The chassis calls ``on_init(server)`` during startup, before tool
extensions are discovered and registered.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp_chassis.server import ChassisServer

logger = logging.getLogger(__name__)


# ── Typed app config ────────────────────────────────────────────────────

@dataclass
class SearchConfig:
    """Typed configuration for ``[app.search]``."""

    enable_item_types_filter: bool = True
    enable_substring_match: bool = True
    enable_search_logic: bool = True


@dataclass
class SolveItAppConfig:
    """Typed configuration for the ``[app]`` TOML section.

    Constructed from the raw ``dict`` in ``server._config.app``. Provides
    defaults, type safety, and validation. Unrecognized top-level keys
    are logged as warnings to catch typos early.

    Attributes:
        solveit_data_path: Path to the SOLVE-IT repository root.
        objective_mapping: Mapping file name in the SOLVE-IT data/ directory.
        enable_extensions: Whether to load SOLVE-IT-X extension data.
        init_required: If True, exit on KB load failure instead of degrading.
        enable_full_detail_tools: Whether to register full-detail listing tools.
        search: Search parameter visibility flags.
    """

    solveit_data_path: str = "../solve-it/solve-it-main"
    objective_mapping: str = "solve-it.json"
    enable_extensions: bool = True
    init_required: bool = True
    enable_full_detail_tools: bool = False
    search: SearchConfig = field(default_factory=SearchConfig)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> SolveItAppConfig:
        """Build a validated config from the raw ``[app]`` dict.

        Extracts known keys, builds nested ``SearchConfig``, and warns
        about any unrecognized top-level keys.

        Args:
            raw: The raw ``[app]`` config dict from TOML.

        Returns:
            A validated ``SolveItAppConfig`` instance.
        """
        # Warn about unrecognized top-level keys
        known_keys = {f.name for f in fields(cls)}
        for key in raw:
            if key not in known_keys:
                logger.warning(
                    "Unrecognized [app] config key: '%s'. "
                    "Known keys: %s",
                    key, ", ".join(sorted(known_keys)),
                )

        # Build nested search config
        search_raw = raw.get("search", {})
        search = SearchConfig(
            enable_item_types_filter=search_raw.get("enable_item_types_filter", True),
            enable_substring_match=search_raw.get("enable_substring_match", True),
            enable_search_logic=search_raw.get("enable_search_logic", True),
        )

        return cls(
            solveit_data_path=raw.get("solveit_data_path", cls.solveit_data_path),
            objective_mapping=raw.get("objective_mapping", cls.objective_mapping),
            enable_extensions=raw.get("enable_extensions", cls.enable_extensions),
            init_required=raw.get("init_required", cls.init_required),
            enable_full_detail_tools=raw.get("enable_full_detail_tools", cls.enable_full_detail_tools),
            search=search,
        )


# ── Environment variable overrides ──────────────────────────────────────

# Format: (env_var_name, config_key, type)
# Env vars override TOML values when set.
_ENV_OVERRIDES: list[tuple[str, str, type]] = [
    ("MCP_APP_SOLVEIT_DATA_PATH", "solveit_data_path", str),
    ("MCP_APP_OBJECTIVE_MAPPING", "objective_mapping", str),
    ("MCP_APP_ENABLE_EXTENSIONS", "enable_extensions", bool),
    ("MCP_APP_INIT_REQUIRED", "init_required", bool),
    ("MCP_APP_ENABLE_FULL_DETAIL_TOOLS", "enable_full_detail_tools", bool),
]


def _apply_env_overrides(app_config: dict[str, Any]) -> None:
    """Apply MCP_APP_* environment variable overrides to the app config dict.

    Modifies ``app_config`` in place before it is parsed into
    ``SolveItAppConfig``. Boolean values are parsed from common
    truthy/falsy strings (``true/false``, ``1/0``, ``yes/no``).
    Env vars that are not set are skipped.

    Args:
        app_config: The ``[app]`` config dict to override.
    """
    for env_var, config_key, value_type in _ENV_OVERRIDES:
        raw = os.environ.get(env_var)
        if raw is None:
            continue
        if value_type is bool:
            app_config[config_key] = raw.lower() in ("1", "true", "yes")
        else:
            app_config[config_key] = raw
        logger.info("Config override: %s=%r (from %s)", config_key, app_config[config_key], env_var)


# ── Init hook ───────────────────────────────────────────────────────────

def on_init(server: ChassisServer) -> None:
    """Load the SOLVE-IT KnowledgeBase and attach it to the server.

    Reads configuration from ``server._config.app`` with optional
    environment variable overrides (``MCP_APP_*`` prefix). The raw dict
    is validated into a ``SolveItAppConfig`` dataclass — unrecognized
    keys are logged as warnings to catch typos.

    On success, sets ``server._kb`` to the KnowledgeBase instance,
    ``server._kb_error`` to None, and ``server._app_config`` to the
    validated config. On failure, sets ``server._kb`` to None and
    ``server._kb_error`` to a descriptive error string. If
    ``init_required`` is True, the process exits instead of continuing.

    Args:
        server: The ChassisServer instance.
    """
    raw_config = server._config.app
    _apply_env_overrides(raw_config)
    config = SolveItAppConfig.from_raw(raw_config)
    server._app_config = config

    data_path = Path(config.solveit_data_path).resolve()

    try:
        str_path = str(data_path)
        if str_path not in sys.path:
            sys.path.insert(0, str_path)

        from solve_it_library import KnowledgeBase

        kb = KnowledgeBase(
            base_path=str_path,
            mapping_file=config.objective_mapping,
            enable_extensions=config.enable_extensions,
        )

        server._kb = kb
        server._kb_error = None

        n_t = len(kb.list_techniques())
        n_w = len(kb.list_weaknesses())
        n_m = len(kb.list_mitigations())
        logger.info(
            "SOLVE-IT KB loaded: %d techniques, %d weaknesses, %d mitigations "
            "(path: %s, mapping: %s, extensions: %s)",
            n_t, n_w, n_m, data_path, config.objective_mapping, config.enable_extensions,
        )
    except Exception as exc:
        msg = f"Failed to load SOLVE-IT KB from '{data_path}': {exc}"
        logger.error(msg)
        server._kb = None
        server._kb_error = msg

        if config.init_required:
            # sys.exit() raises SystemExit (a BaseException), which bypasses
            # the chassis's `except Exception` handler in _run_init_hook().
            # This ensures the server stops with a clear error rather than
            # starting in a degraded state with no useful tools.
            logger.critical(
                "Exiting: init_required=true and KB failed to load. "
                "Set init_required=false in [app] config to allow degraded startup."
            )
            sys.exit(1)
