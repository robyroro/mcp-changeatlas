"""MCP stdio server. The configured root is fixed for the server lifetime."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from mcp.server import MCPServer

from changeatlas import __version__
from changeatlas.service import ChangeAtlas


def create_server(root: Path) -> MCPServer:
    atlas = ChangeAtlas(root)
    server = MCPServer(
        "ChangeAtlas",
        title="ChangeAtlas",
        description="Local Git change impact and related test discovery",
        version=__version__,
    )

    @server.tool()
    def repository_overview() -> dict[str, object]:
        """Show index size, skipped files and exact analysis coverage for this repository."""
        return atlas.overview()

    @server.tool()
    def analyze_changes(
        base_ref: str = "HEAD", include_untracked: bool = False, max_depth: int = 4
    ) -> dict[str, object]:
        """Trace changed files to local dependents and candidate tests with import paths."""
        return atlas.changes(base_ref, include_untracked, max_depth)

    @server.tool()
    def trace_file(
        path: str, direction: Literal["dependents", "dependencies"] = "dependents",
        max_depth: int = 4,
    ) -> dict[str, object]:
        """Trace local imports into or out of a tracked repository file."""
        return dict(atlas.trace(path, direction, max_depth))

    @server.tool()
    def find_tests(path: str, max_depth: int = 4) -> dict[str, object]:
        """Find tracked tests linked by local imports to a source file."""
        return atlas.tests_for(path, max_depth)

    return server
