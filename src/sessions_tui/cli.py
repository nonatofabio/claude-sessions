"""CLI entry point for the Sessions TUI."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    """Parse arguments and launch the TUI."""
    parser = argparse.ArgumentParser(
        description="Terminal UI for browsing Claude Code sessions",
    )
    parser.add_argument(
        "--projects-dir", type=Path,
        default=Path.home() / ".claude" / "projects",
        help="Path to Claude Code projects directory",
    )
    parser.add_argument(
        "--cache-path", type=Path,
        default=Path.home() / ".claude" / "sessions_tui_cache.json",
        help="Path to the JSON cache file",
    )
    parser.add_argument(
        "--refresh", action="store_true",
        help="Force full cache rebuild (ignore existing cache)",
    )
    parser.add_argument(
        "--no-active", action="store_true",
        help="Skip active session detection",
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Launch with synthetic demo data (no real sessions)",
    )
    args = parser.parse_args()

    from .app import SessionsTUI

    app = SessionsTUI(
        projects_dir=args.projects_dir,
        cache_path=args.cache_path,
        force_refresh=args.refresh,
        detect_active=not args.no_active,
        demo_mode=args.demo,
    )
    app.run()
