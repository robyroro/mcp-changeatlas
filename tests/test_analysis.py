from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from changeatlas.git import RepositoryError, safe_file
from changeatlas.index import ImportIndex, is_test
from changeatlas.service import ChangeAtlas


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "Test User")
    git(tmp_path, "config", "user.email", "test@example.invalid")
    files = {
        "src/app/__init__.py": "",
        "src/app/core.py": "def answer():\n    return 42\n",
        "src/app/api.py": "from .core import answer\n",
        "tests/test_api.py": "from app.api import answer\n",
        "web/util.ts": "export const answer = 42;\n",
        "web/view.tsx": 'import { answer } from "./util";\n',
        "web/view.test.tsx": 'import { View } from "./view";\n',
    }
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "fixture")
    return tmp_path


def test_python_impact_and_evidence(repo: Path) -> None:
    atlas = ChangeAtlas(repo)
    result = atlas.tests_for("src/app/core.py")
    assert result["tests"] == [
        {
            "path": "tests/test_api.py",
            "hops": 2,
            "evidence": ["src/app/core.py", "src/app/api.py", "tests/test_api.py"],
        }
    ]


def test_package_initializer_is_part_of_import_graph(repo: Path) -> None:
    result = ChangeAtlas(repo).tests_for("src/app/__init__.py")
    assert "tests/test_api.py" in {item["path"] for item in result["tests"]}


def test_js_impact_and_changes(repo: Path) -> None:
    (repo / "web/util.ts").write_text("export const answer = 43;\n", encoding="utf-8")
    result = ChangeAtlas(repo).changes()
    assert result["changed_files"] == ["web/util.ts"]
    assert result["candidate_tests"] == [
        {
            "path": "web/view.test.tsx",
            "evidence": ["web/util.ts", "web/view.tsx", "web/view.test.tsx"],
        }
    ]
    assert result["incomplete"] is False


def test_js_comments_and_strings_are_not_imports(repo: Path) -> None:
    (repo / "web/view.tsx").write_text(
        '// import "./util"\nconst note = "import ./util";\n', encoding="utf-8"
    )
    index = ImportIndex.build(repo)
    assert index.edges["web/view.tsx"] == set()


def test_fixture_file_is_not_a_runnable_test() -> None:
    assert is_test("tests/conftest.py") is False
    assert is_test("tests/test_api.py") is True


def test_staged_and_untracked_changes(repo: Path) -> None:
    (repo / "src/app/core.py").write_text("def answer():\n    return 43\n", encoding="utf-8")
    git(repo, "add", "src/app/core.py")
    (repo / "notes.txt").write_text("draft", encoding="utf-8")
    atlas = ChangeAtlas(repo)
    assert atlas.changes()["changed_files"] == ["src/app/core.py"]
    expanded = atlas.changes(include_untracked=True)
    assert expanded["changed_files"] == ["notes.txt", "src/app/core.py"]
    assert expanded["unindexed_changes"] == ["notes.txt"]
    assert expanded["incomplete"] is True


def test_unsafe_ref_and_path(repo: Path) -> None:
    atlas = ChangeAtlas(repo)
    with pytest.raises(RepositoryError):
        atlas.changes("--output=/tmp/no")
    with pytest.raises(ValueError):
        atlas.trace("../secret.py")
    assert safe_file(repo, "../secret.py") is None


def test_unreadable_and_external_symlink_not_indexed(repo: Path, tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside_changeatlas_test.py"
    outside.write_text("SECRET = 1", encoding="utf-8")
    link = repo / "src/app/outside.py"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Symlink creation is unavailable on this Windows account")
    git(repo, "add", "src/app/outside.py")
    index = ImportIndex.build(repo)
    assert "src/app/outside.py" not in index.files
    assert any("outside repository" in note for note in index.skipped)


def test_deleted_file_is_explicitly_incomplete(repo: Path) -> None:
    (repo / "src/app/api.py").unlink()
    result = ChangeAtlas(repo).changes()
    assert result["unindexed_changes"] == ["src/app/api.py"]
    assert result["incomplete"] is True


def test_parse_failure_is_explicitly_incomplete(repo: Path) -> None:
    (repo / "src/app/api.py").write_text("from .core import (\n", encoding="utf-8")
    result = ChangeAtlas(repo).changes()
    assert result["incomplete"] is True
    assert "src/app/api.py" not in [item["path"] for item in result["affected_files"]]
    assert "Python parse failed: src/app/api.py" in ChangeAtlas(repo).overview()["skipped"]
