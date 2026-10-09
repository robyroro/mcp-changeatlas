# ChangeAtlas

<!-- mcp-name: io.github.robyroro/mcp-changeatlas -->

ChangeAtlas shows which local files and tests may be affected by a Git change. It follows static imports and returns the file path behind every link, so you can inspect the evidence yourself. It runs on your machine, reads your repository, and does not send its contents to a service.

It is useful when you have changed a module and want a short, grounded list of places to check before committing. It does not decide whether a change is safe or whether a test covers a behavior.

## Install

Requires Python 3.11 or newer and Git.

```bash
pip install mcp-changeatlas
```

Point it at the exact root of a Git repository:

```bash
mcp-changeatlas --root /path/to/repo overview
mcp-changeatlas --root /path/to/repo changes --base HEAD
mcp-changeatlas --root /path/to/repo trace src/app/core.py
mcp-changeatlas --root /path/to/repo tests src/app/core.py
```

For an MCP client, configure a stdio server with command `mcp-changeatlas` and arguments `--root`, the repository path, and `serve`. For example:

```json
{
  "mcpServers": {
    "changeatlas": {
      "command": "mcp-changeatlas",
      "args": ["--root", "/path/to/repo", "serve"]
    }
  }
}
```

The four tools are `repository_overview`, `analyze_changes`, `trace_file`, and `find_tests`. The root is set by the person running the server and cannot be changed by a tool call.

The Docker image is for directory build checks and a self-contained demo. It analyzes the repository snapshot inside the image. To analyze your own work, install the package locally and set `--root` to your repository.

## How it works

ChangeAtlas reads tracked Python, JavaScript, and TypeScript files and builds a local import graph. Python imports are parsed with the standard library AST. JS/TS relative import, export, and `require` links are found statically. It follows reverse links from a changed file to nearby modules and tests, up to a chosen depth. Results include the file chain that led to each suggestion.

`analyze_changes` compares the working tree, including staged changes, with a Git commit. `include_untracked` adds untracked file names. It never runs project code, test commands, package managers, or Git hooks. It resolves paths and rejects files that point outside the configured repository. File and result counts have fixed limits.

This first release resolves local Python imports and relative JS/TS imports. It cannot follow runtime imports, package aliases, monorepo path mappings, or non-code dependencies. Deleted and unsupported files are shown under `unindexed_changes`; an incomplete result is marked as such. A suggested test is a path through imports, not a coverage claim.

## Development

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
pytest
ruff check .
mypy
python -m build
```

## Publishing

The package name and MCP Registry name are set in `pyproject.toml`, `README.md`, and `server.json`. Before the first PyPI release, create a pending trusted publisher for `robyroro/mcp-changeatlas`, workflow `release.yml`, environment `pypi`. Then publish a GitHub release tagged with the matching package version. The release workflow runs tests and publishes the wheel and source archive through PyPI's trusted publishing flow.

Once the exact version is visible on PyPI, run the `Publish to MCP Registry` GitHub Actions workflow. It validates `server.json` and publishes it with GitHub OIDC, following the [Registry publisher guide](https://github.com/modelcontextprotocol/registry/blob/main/docs/modelcontextprotocol-io/github-actions.mdx). The registry is a separate publication step. A repository or PyPI release alone does not create a registry listing.

## License

MIT
