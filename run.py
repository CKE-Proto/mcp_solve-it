#!/usr/bin/env python3
"""Launcher for the SOLVE-IT MCP Server.

Adds the project's src/ directory to sys.path so that mcp_chassis is
importable without requiring ``pip install``.  All command-line arguments
are forwarded to the server (e.g. --config, --log-level).

Usage:
    python3 run.py --config /path/to/config/default.toml
    python3 run.py --config config/default.toml --log-level DEBUG
"""

import sys
from pathlib import Path

# Ensure src/ is on the import path
_SRC_DIR = str(Path(__file__).resolve().parent / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from mcp_chassis.__main__ import main

if __name__ == "__main__":
    main()
