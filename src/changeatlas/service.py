"""Public analysis operations shared by CLI and MCP."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from changeatlas.git import changed_paths, repository_root
from changeatlas.index import ImportIndex, WalkResult, is_test


class ChangeAtlas:
    def __init__(self, root: Path):
        self.root = repository_root(root)

    def _index(self) -> ImportIndex:
        return ImportIndex.build(self.root)

    def overview(self) -> dict[str, object]:
        index = self._index()
        return {
            "repository": str(self.root),
            "indexed_files": len(index.files),
            "test_files": sum(is_test(path) for path in index.files),
            "import_edges": sum(len(targets) for targets in index.edges.values()),
            "skipped": index.skipped[:50],
            "skipped_count": len(index.skipped),
            "truncated": index.truncated or len(index.skipped) > 50,
            "coverage": (
                "Tracked local Python and relative JS/TS imports only; "
                "runtime and configured aliases are not resolved."
            ),
        }

    def trace(
        self, path: str, direction: Literal["dependents", "dependencies"] = "dependents",
        max_depth: int = 4,
    ) -> WalkResult:
        if direction not in ("dependents", "dependencies"):
            raise ValueError("direction must be dependents or dependencies")
        return self._index().walk(path, direction, max_depth)

    def tests_for(self, path: str, max_depth: int = 4) -> dict[str, object]:
        return self._index().tests_for(path, max_depth)

    def changes(
        self, base_ref: str = "HEAD", include_untracked: bool = False, max_depth: int = 4
    ) -> dict[str, object]:
        if not 1 <= max_depth <= 8:
            raise ValueError("max_depth must be between 1 and 8")
        index = self._index()
        changed = changed_paths(self.root, base_ref, include_untracked)
        tests: dict[str, list[str]] = {}
        dependents: dict[str, list[str]] = {}
        unindexed: list[str] = []
        limited = False
        for path in changed[:200]:
            if path not in index.files:
                unindexed.append(path)
                continue
            result = index.walk(path, "dependents", max_depth)
            limited = limited or bool(result["limited"])
            for item in result["items"]:
                target = str(item["path"])
                evidence = list(item["evidence"])
                if is_test(target):
                    tests.setdefault(target, evidence)
                else:
                    dependents.setdefault(target, evidence)
            if is_test(path):
                tests.setdefault(path, [path])
        return {
            "base_ref": base_ref,
            "changed_files": changed[:200],
            "changed_count": len(changed),
            "affected_files": [
                {"path": path, "evidence": evidence}
                for path, evidence in sorted(dependents.items())
            ],
            "candidate_tests": [
                {"path": path, "evidence": evidence} for path, evidence in sorted(tests.items())
            ],
            "unindexed_changes": unindexed,
            "skipped": index.skipped[:50],
            "skipped_count": len(index.skipped),
            "incomplete": bool(index.skipped) or limited or len(changed) > 200 or bool(unindexed),
            "limits": [
                "Import links are static evidence, not proof that a test covers a behavior.",
                "Deleted, unsupported and skipped files have no import graph.",
                "Untracked files are omitted unless include_untracked is true.",
                "Python runtime imports and JS/TS aliases are not resolved.",
            ],
        }
