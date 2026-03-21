"""Extension auto-discovery for the MCP Chassis server.

Scans the extensions/tools/, extensions/resources/, and extensions/prompts/
subdirectories for Python modules, imports each, and calls register(server)
if the function is present.

**Security note:** Importing a Python module executes all module-level code
before any further checks (e.g. register() existence) can run. Any .py file
placed in these directories will execute with the server's full privileges at
startup. To mitigate this, the discovery process checks file permissions before
import and skips files that are world-writable. Extension directories should be
writable only by trusted users/build processes.
"""

from __future__ import annotations

import importlib
import logging
import re
import stat
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_chassis.server import ChassisServer

logger = logging.getLogger(__name__)

_SUBDIRS = ["tools", "resources", "prompts"]
_VALID_MODULE_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _check_file_permissions(file_path: Path) -> bool:
    """Check that an extension file has safe permissions before import.

    Rejects files that are world-writable, as this indicates any local user
    could have modified the file. On platforms where permission checks are
    unavailable (e.g. some virtual filesystems), the check is skipped with
    a debug log.

    Args:
        file_path: Path to the extension .py file.

    Returns:
        True if the file is safe to import, False if it should be skipped.
    """
    if sys.platform == "win32":
        logger.debug(
            "Skipping permission check for '%s' — "
            "S_IWOTH is not meaningful on Windows",
            file_path,
        )
        return True

    try:
        file_stat = file_path.stat()
    except OSError as exc:
        logger.warning(
            "Cannot stat extension file '%s', skipping: %s", file_path, exc
        )
        return False

    if file_stat.st_mode & stat.S_IWOTH:
        logger.warning(
            "Extension file '%s' is world-writable (mode %o), skipping — "
            "this is a security risk. Fix with: chmod o-w '%s'",
            file_path,
            file_stat.st_mode & 0o777,
            file_path,
        )
        return False

    return True


def discover_extensions(server: ChassisServer) -> None:
    """Scan extension subdirectories and register all valid extensions.

    Scans tools/, resources/, and prompts/ subdirectories inside the
    extensions package for .py files (excluding __init__.py), imports each,
    and calls register(server) if the function exists. Errors in any single
    extension are logged and skipped — the server never crashes due to a bad
    extension.

    Args:
        server: The ChassisServer to register extensions with.
    """
    extensions_dir = Path(__file__).parent

    for subdir in _SUBDIRS:
        subdir_path = extensions_dir / subdir
        if not subdir_path.is_dir():
            logger.debug("Extension subdir '%s' not found, skipping", subdir)
            continue

        for module_path in sorted(subdir_path.glob("*.py")):
            if module_path.name == "__init__.py":
                continue

            stem = module_path.stem
            if not _VALID_MODULE_NAME_RE.match(stem):
                logger.warning(
                    "Skipping extension '%s': invalid module name '%s'",
                    module_path, stem,
                )
                continue

            if not _check_file_permissions(module_path):
                continue

            module_name = f"mcp_chassis.extensions.{subdir}.{stem}"
            _load_extension(module_name, module_path, server)


def _load_extension(
    module_name: str, file_path: Path, server: ChassisServer
) -> None:
    """Import a single extension module and call its register() function.

    Args:
        module_name: Fully qualified module name to import.
        file_path: Filesystem path to the module (for audit logging).
        server: The ChassisServer to pass to register().
    """
    logger.warning("Loading extension '%s' from %s", module_name, file_path)
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        logger.error("Failed to import extension '%s': %s", module_name, exc)
        return

    register_fn = getattr(module, "register", None)
    if register_fn is None:
        logger.debug("Extension '%s' has no register() function, skipping", module_name)
        return

    if not callable(register_fn):
        logger.warning(
            "Extension '%s' has a register attribute that is not callable, skipping",
            module_name,
        )
        return

    try:
        register_fn(server)
        logger.debug("Registered extension '%s'", module_name)
    except Exception as exc:
        logger.error("Extension '%s' register() raised an error: %s", module_name, exc)
