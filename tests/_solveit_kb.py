"""Locate a SOLVE-IT checkout for tests that need real KB data.

Checks ``SOLVEIT_TEST_DATA_PATH``, then ``MCP_APP_SOLVEIT_DATA_PATH``, then
the sibling ``../solve-it/solve-it-main`` used by the other tests.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

_DEFAULT = Path(__file__).resolve().parents[2] / "solve-it" / "solve-it-main"


def solveit_path() -> Path | None:
    """Return the SOLVE-IT repository root, or None if none is available."""
    for env in ("SOLVEIT_TEST_DATA_PATH", "MCP_APP_SOLVEIT_DATA_PATH"):
        value = os.environ.get(env)
        if value and (Path(value) / "solve_it_library").is_dir():
            return Path(value).resolve()
    if (_DEFAULT / "solve_it_library").is_dir():
        return _DEFAULT
    return None


def load_kb() -> Any | None:
    """Load the KnowledgeBase, or return None if unavailable."""
    path = solveit_path()
    if path is None:
        return None
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    try:
        from solve_it_library import KnowledgeBase
    except ImportError:
        return None
    return KnowledgeBase(base_path=str(path))
