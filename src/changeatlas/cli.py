"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from changeatlas.git import RepositoryError
from changeatlas.server import create_server
from changeatlas.service import ChangeAtlas


def main() -> int:
    parser = argparse.ArgumentParser(prog="mcp-changeatlas", description="Local Git change impact")
    parser.add_argument(
        "--root", type=Path, default=Path(os.environ.get("CHANGEATLAS_ROOT", ".")),
        help="Exact Git repository root (or CHANGEATLAS_ROOT)",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="Run MCP over stdio")
    commands.add_parser("overview", help="Show analysis coverage as JSON")
    changes = commands.add_parser("changes", help="Analyze changes against a commit")
    changes.add_argument("--base", default="HEAD")
    changes.add_argument("--untracked", action="store_true")
    trace = commands.add_parser("trace", help="Trace a tracked source file")
    trace.add_argument("path")
    trace.add_argument("--direction", choices=["dependents", "dependencies"], default="dependents")
    tests = commands.add_parser("tests", help="Find related tests")
    tests.add_argument("path")
    args = parser.parse_args()
    try:
        if args.command == "serve":
            create_server(args.root).run(transport="stdio")
            return 0
        atlas = ChangeAtlas(args.root)
        result: object
        if args.command == "overview":
            result = atlas.overview()
        elif args.command == "changes":
            result = atlas.changes(args.base, args.untracked)
        elif args.command == "trace":
            result = atlas.trace(args.path, args.direction)
        else:
            result = atlas.tests_for(args.path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, RepositoryError) as exc:
        print(f"changeatlas: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
