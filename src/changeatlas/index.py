"""Deterministic import graph for tracked Python and JS/TS files."""

from __future__ import annotations

import ast
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal, TypedDict

from changeatlas.git import safe_file, tracked_paths

SUFFIXES = {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}
JS_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs")
MAX_FILES = 5000
MAX_FILE_BYTES = 512_000
MAX_TOTAL_BYTES = 20_000_000
MAX_RESULTS = 200
JS_TOKEN = re.compile(
    r"//[^\n]*|/\*[\s\S]*?\*/|"  # comments
    r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|'  # quoted strings
    r"`(?:\\.|[^`\\])*`|"  # template literals are deliberately unsupported
    r"[A-Za-z_$][\w$]*|[^\s]"
)


class WalkItem(TypedDict):
    path: str
    hops: int
    evidence: list[str]


class WalkResult(TypedDict):
    source: str
    direction: str
    items: list[WalkItem]
    limited: bool


def is_test(path: str) -> bool:
    name = PurePosixPath(path).name
    return (
        name.startswith("test_") and name.endswith(".py")
        or name.endswith("_test.py")
        or bool(re.search(r"\.(test|spec)\.[cm]?[jt]sx?$", name))
    )


def _python_modules(path: str) -> list[str]:
    part = PurePosixPath(path)
    stem_parts = list(part.with_suffix("").parts)
    if stem_parts[0] == "src":
        stem_parts.pop(0)
    if stem_parts[-1] == "__init__":
        stem_parts.pop()
    return [".".join(stem_parts)] if stem_parts else []


def _python_imports(text: str, path: str) -> set[str]:
    tree = ast.parse(text, filename=path)
    current = _python_modules(path)
    package = current[0].split(".") if current else []
    if not path.endswith("/__init__.py"):
        package = package[:-1]
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                keep = len(package) - node.level + 1
                if keep < 0:
                    continue
                prefix = package[:keep]
            else:
                prefix = []
            base = ".".join([*prefix, *node.module.split(".")]) if node.module else ".".join(prefix)
            if base:
                imports.add(base)
                imports.update(f"{base}.{alias.name}" for alias in node.names if alias.name != "*")
    return imports


def _js_specifiers(text: str) -> set[str]:
    tokens = [
        token.group()
        for token in JS_TOKEN.finditer(text)
        if not token.group().startswith(("//", "/*"))
    ]
    found: set[str] = set()
    for i, token in enumerate(tokens):
        if token in ("require", "import") and i + 2 < len(tokens) and tokens[i + 1] == "(":
            value = tokens[i + 2]
            if value.startswith(("'", '"')):
                found.add(value[1:-1])
        if token == "import" and i + 1 < len(tokens) and tokens[i + 1].startswith(("'", '"')):
            found.add(tokens[i + 1][1:-1])
        if token not in ("import", "export"):
            continue
        for j in range(i + 1, min(i + 100, len(tokens) - 1)):
            if tokens[j] == ";":
                break
            if tokens[j] == "from" and tokens[j + 1].startswith(("'", '"')):
                found.add(tokens[j + 1][1:-1])
                break
    return {value for value in found if value.startswith(".")}


def _js_imports(text: str, path: str, known: set[str]) -> set[str]:
    directory = PurePosixPath(path).parent
    imports: set[str] = set()
    for specifier in _js_specifiers(text):
        target = PurePosixPath(directory, specifier)
        parts: list[str] = []
        for part in target.parts:
            if part == "..":
                if not parts:
                    break
                parts.pop()
            elif part != ".":
                parts.append(part)
        else:
            base = "/".join(parts)
            candidates = [base, *(base + ext for ext in JS_SUFFIXES)]
            candidates.extend(f"{base}/index{ext}" for ext in JS_SUFFIXES)
            imports.update(candidate for candidate in candidates if candidate in known)
    return imports


@dataclass
class ImportIndex:
    root: Path
    files: set[str] = field(default_factory=set)
    edges: dict[str, set[str]] = field(default_factory=dict)
    reverse: dict[str, set[str]] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    truncated: bool = False

    @classmethod
    def build(cls, root: Path) -> ImportIndex:
        paths = [p for p in tracked_paths(root) if PurePosixPath(p).suffix in SUFFIXES]
        index = cls(root=root)
        if len(paths) > MAX_FILES:
            index.truncated = True
            index.skipped.append(
                f"File limit reached: {len(paths)} supported files, {MAX_FILES} indexed"
            )
            paths = paths[:MAX_FILES]
        contents: dict[str, str] = {}
        total = 0
        for relative in paths:
            path = safe_file(root, relative)
            if path is None:
                index.skipped.append(f"Unavailable or outside repository: {relative}")
                continue
            try:
                size = path.stat().st_size
            except OSError:
                index.skipped.append(f"Unavailable file: {relative}")
                continue
            if size > MAX_FILE_BYTES:
                index.skipped.append(f"File too large: {relative}")
                continue
            if total + size > MAX_TOTAL_BYTES:
                index.truncated = True
                index.skipped.append("Total content limit reached")
                break
            try:
                contents[relative] = path.read_text(encoding="utf-8")
            except (UnicodeError, OSError):
                index.skipped.append(f"Unreadable UTF-8 file: {relative}")
                continue
            total += size
        index.files = set(contents)
        modules: dict[str, set[str]] = defaultdict(set)
        for relative in sorted(index.files):
            if relative.endswith(".py"):
                for module in _python_modules(relative):
                    modules[module].add(relative)
        for module, candidates in sorted(modules.items()):
            if len(candidates) > 1:
                index.skipped.append(f"Ambiguous Python module: {module}")
        reverse: dict[str, set[str]] = defaultdict(set)
        for relative, content in contents.items():
            if relative.endswith(".py"):
                try:
                    imports = _python_imports(content, relative)
                except (SyntaxError, RecursionError, ValueError):
                    index.skipped.append(f"Python parse failed: {relative}")
                    imports = set()
                imports_with_packages = {
                    ".".join(name.split(".")[:depth])
                    for name in imports
                    for depth in range(1, len(name.split(".")) + 1)
                }
                targets = {
                    next(iter(modules[name]))
                    for name in imports_with_packages
                    if name in modules and len(modules[name]) == 1
                }
            else:
                targets = _js_imports(content, relative, index.files)
            targets.discard(relative)
            index.edges[relative] = targets
            for target in targets:
                reverse[target].add(relative)
        index.reverse = dict(reverse)
        return index

    def walk(
        self, start: str, direction: Literal["dependents", "dependencies"], max_depth: int = 4
    ) -> WalkResult:
        if start not in self.files:
            raise ValueError("Path is not an indexed, tracked source file")
        if not 1 <= max_depth <= 8:
            raise ValueError("max_depth must be between 1 and 8")
        graph = self.reverse if direction == "dependents" else self.edges
        queue = deque([(start, [start])])
        seen = {start}
        items: list[WalkItem] = []
        limited = False
        while queue:
            node, chain = queue.popleft()
            if len(chain) - 1 >= max_depth:
                continue
            for neighbor in sorted(graph.get(node, ())):
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                path = [*chain, neighbor]
                items.append({"path": neighbor, "hops": len(path) - 1, "evidence": path})
                if len(items) >= MAX_RESULTS:
                    limited = True
                    queue.clear()
                    break
                queue.append((neighbor, path))
        return {"source": start, "direction": direction, "items": items, "limited": limited}

    def tests_for(self, start: str, max_depth: int = 4) -> dict[str, object]:
        result = self.walk(start, "dependents", max_depth)
        matches = [item for item in result["items"] if is_test(str(item["path"]))]
        if is_test(start):
            matches.insert(0, {"path": start, "hops": 0, "evidence": [start]})
        return {"source": start, "tests": matches, "limited": result["limited"]}
