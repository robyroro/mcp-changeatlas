"""Small, read-only Git boundary. User values are never shell commands."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


class RepositoryError(ValueError):
    """The configured repository or requested revision cannot be inspected."""


def _git(root: Path, *args: str) -> bytes:
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    result = subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-C", str(root), *args],
        capture_output=True,
        check=False,
        timeout=30,
        env=env,
    )
    if result.returncode:
        message = result.stderr.decode("utf-8", "replace").strip().splitlines()
        raise RepositoryError(message[-1] if message else "Git command failed")
    return result.stdout


def repository_root(configured: Path) -> Path:
    root = configured.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise RepositoryError("Repository root must be a directory")
    actual = Path(_git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    if actual != root:
        raise RepositoryError("Configure the Git repository root, not a subdirectory")
    return root


def tracked_paths(root: Path) -> list[str]:
    raw = _git(root, "ls-files", "-z", "--cached")
    return sorted({os.fsdecode(part) for part in raw.split(b"\0") if part})


def resolve_commit(root: Path, ref: str) -> str:
    if not ref or len(ref) > 200 or "\0" in ref or ref.startswith("-"):
        raise RepositoryError("Invalid Git revision")
    raw = _git(root, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}")
    sha = raw.decode("ascii", "replace").strip()
    if len(sha) not in (40, 64) or any(char not in "0123456789abcdef" for char in sha):
        raise RepositoryError("Git did not return a commit ID")
    return sha


def changed_paths(root: Path, base_ref: str, include_untracked: bool = False) -> list[str]:
    base = resolve_commit(root, base_ref)
    raw = _git(root, "diff", "--no-ext-diff", "--no-renames", "--name-only", "-z", base, "--")
    paths = {os.fsdecode(part) for part in raw.split(b"\0") if part}
    if include_untracked:
        raw = _git(root, "ls-files", "--others", "--exclude-standard", "-z")
        paths.update(os.fsdecode(part) for part in raw.split(b"\0") if part)
    return sorted(paths)


def safe_file(root: Path, relative: str) -> Path | None:
    if not relative or "\0" in relative or Path(relative).is_absolute():
        return None
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    return path
