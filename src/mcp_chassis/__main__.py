"""CLI entry point for the MCP Chassis server.

Allows running as:
    python -m mcp_chassis
    python -m mcp_chassis --config /path/to/config.toml
    python -m mcp_chassis --env-file /path/to/.env
    python -m mcp_chassis --version
    python -m mcp_chassis --log-level DEBUG

Environment variables:
    MCP_CHASSIS_CONFIG — path to config file
    MCP_LOG_LEVEL — log level override
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

import mcp_chassis
from mcp_chassis.config import ServerConfig
from mcp_chassis.logging_config import configure_logging

logger = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).

    Returns:
        Parsed argument namespace.
    """
    parser = argparse.ArgumentParser(
        prog="mcp-chassis",
        description="MCP Chassis Server — forkable MCP server with security middleware.",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="Path to TOML configuration file (default: config/default.toml).",
    )
    parser.add_argument(
        "--env-file",
        metavar="PATH",
        help=(
            "Path to a .env file of KEY=VALUE lines to load into the "
            "environment before starting. Blank lines and lines starting "
            "with # are ignored. Does not override variables already set."
        ),
    )
    parser.add_argument(
        "--log-level",
        metavar="LEVEL",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Log level override (also set via MCP_LOG_LEVEL env var).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"mcp-chassis {mcp_chassis.__version__}",
    )
    return parser.parse_args(argv)


def _load_env_file(env_path: Path) -> None:
    """Load KEY=VALUE pairs from a .env file into os.environ.

    Skips blank lines, lines starting with ``#``, and lines without ``=``.
    Strips optional ``export `` prefix. Values may be optionally quoted with
    single or double quotes. Variables already present in the environment are
    NOT overwritten.

    Args:
        env_path: Path to the .env file.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    with env_path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Strip optional 'export ' prefix
            if line.startswith("export "):
                line = line[len("export "):]
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Strip matching quotes
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            if key and key not in os.environ:
                os.environ[key] = value
    logger.debug("Loaded environment from %s", env_path)


async def _run_server(config_path: Path | None, log_level: str | None) -> None:
    """Load configuration, create, and run the server.

    Args:
        config_path: Optional explicit path to config file.
        log_level: Optional log level override from CLI.
    """
    try:
        config = ServerConfig.load(config_path)
    except Exception as exc:
        logger.critical("Failed to load configuration: %s", exc)
        sys.exit(1)

    # CLI log level overrides config
    effective_log_level = log_level or config.server.log_level
    configure_logging(effective_log_level)

    logger.info(
        "Loaded configuration: server='%s' transport='%s' security_profile='%s'",
        config.server.name,
        config.server.transport,
        config.security.profile,
    )

    from mcp_chassis.server import ChassisServer

    try:
        server = ChassisServer(config)
    except (ValueError, FileNotFoundError) as exc:
        logger.critical("Failed to initialize server: %s", exc)
        sys.exit(1)

    # Install signal handlers — first signal triggers graceful shutdown,
    # second force-exits.
    loop = asyncio.get_running_loop()
    shutdown_requested = False

    def _force_exit() -> None:
        """Force-exit the process when graceful shutdown exceeds the timeout."""
        logger.warning("Graceful shutdown timed out, forcing exit")
        os._exit(1)

    def _handle_signal(sig: signal.Signals) -> None:
        """Handle SIGTERM/SIGINT: first signal initiates graceful shutdown, second force-exits."""
        nonlocal shutdown_requested
        if shutdown_requested:
            logger.warning("Forced exit on repeated %s", sig.name)
            os._exit(1)
        shutdown_requested = True
        logger.info("Received signal %s, initiating graceful shutdown", sig.name)
        # Propagate shutdown through the server → transport chain.
        # This is a sync callback, so schedule the coroutine on the loop.
        loop.create_task(server.shutdown())
        # Close stdin to unblock any blocking readline() in the stdio
        # transport's reader thread. Without this, the thread stays blocked
        # and the task group / event loop cannot shut down.
        try:
            sys.stdin.close()
        except OSError:
            pass
        # Safety net: force exit if graceful shutdown doesn't complete
        loop.call_later(5.0, _force_exit)

    try:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, _handle_signal, sig)
    except NotImplementedError:
        # Signal handlers not supported on Windows — log and continue
        logger.warning("Signal handlers not supported on this platform")

    await server.run()
    logger.info("Server stopped")


def main(argv: list[str] | None = None) -> None:
    """Main entry point for the MCP Chassis server.

    Args:
        argv: Optional argument list for testing (defaults to sys.argv[1:]).
    """
    args = _parse_args(argv)

    # Bootstrap logging with defaults before loading full config
    configure_logging(args.log_level or "INFO")

    # Load .env file before anything reads the environment
    if args.env_file:
        env_path = Path(args.env_file)
        try:
            _load_env_file(env_path)
        except FileNotFoundError:
            logger.critical("Env file not found: %s", env_path)
            sys.exit(1)

    config_path = Path(args.config) if args.config else None

    asyncio.run(_run_server(config_path, args.log_level))


if __name__ == "__main__":
    main()
