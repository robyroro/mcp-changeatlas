from __future__ import annotations

import sys

import pytest
from mcp import Client, StdioServerParameters

from changeatlas.server import create_server
from tests.test_analysis import repo as repo_fixture

repo = repo_fixture


@pytest.mark.anyio
async def test_in_process_mcp_tools(repo) -> None:
    async with Client(create_server(repo)) as client:
        assert client.server_info.version == "0.1.0"
        tools = await client.list_tools()
        assert {tool.name for tool in tools.tools} == {
            "repository_overview",
            "analyze_changes",
            "trace_file",
            "find_tests",
        }
        result = await client.call_tool("find_tests", {"path": "src/app/core.py"})
        assert result.structured_content["tests"][0]["path"] == "tests/test_api.py"


@pytest.mark.anyio
async def test_stdio_mcp_tools(repo) -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "changeatlas.cli", "--root", str(repo), "serve"],
    )
    async with Client(params) as client:
        result = await client.call_tool("repository_overview", {})
        assert result.structured_content["indexed_files"] == 7


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
