"""Unit tests for :mod:`platxa_memory.stack`.

Covers the spec verification criterion for feature #35:
    "Correctly identifies Python/TS/Go/Rust/multi-stack;
     fails gracefully when only .git present"

The tree-walk behaviour is exercised with real ``tmp_path`` directories
so the tests also cover filesystem corner cases (symlink loops are out of
scope; the ``max_depth`` guard is what we test instead).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add src/ to sys.path so tests can import the package without pip install.
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from platxa_memory.stack import StackInfo, detect_stack  # noqa: E402

# --- helpers ---------------------------------------------------------------


def _touch(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


# --- single-stack detection -----------------------------------------------


def test_detect_python_by_pyproject(tmp_path: Path) -> None:
    _touch(tmp_path / "pyproject.toml", "[project]\nname='x'\n")
    info = detect_stack(tmp_path)
    assert info.primary == "python"
    assert info.secondary == ()
    assert len(info.markers) == 1
    assert info.markers[0][0] == "python"
    assert info.markers[0][1].name == "pyproject.toml"


def test_detect_python_by_setup_py(tmp_path: Path) -> None:
    _touch(tmp_path / "setup.py", "from setuptools import setup\nsetup()\n")
    info = detect_stack(tmp_path)
    assert info.primary == "python"


def test_detect_typescript_over_javascript(tmp_path: Path) -> None:
    # tsconfig.json + package.json at the same level → TS wins primary.
    _touch(tmp_path / "tsconfig.json", "{}")
    _touch(tmp_path / "package.json", "{}")
    info = detect_stack(tmp_path)
    assert info.primary == "typescript"
    assert info.secondary == ("javascript",)
    assert info.is_multi_stack


def test_detect_javascript_only(tmp_path: Path) -> None:
    _touch(tmp_path / "package.json", "{}")
    info = detect_stack(tmp_path)
    assert info.primary == "javascript"
    assert info.secondary == ()


def test_detect_go(tmp_path: Path) -> None:
    _touch(tmp_path / "go.mod", "module example.com/x\n")
    info = detect_stack(tmp_path)
    assert info.primary == "go"


def test_detect_rust(tmp_path: Path) -> None:
    _touch(tmp_path / "Cargo.toml", "[package]\nname = 'x'\n")
    info = detect_stack(tmp_path)
    assert info.primary == "rust"


def test_detect_java_gradle(tmp_path: Path) -> None:
    _touch(tmp_path / "build.gradle.kts", "")
    info = detect_stack(tmp_path)
    assert info.primary == "java"


def test_detect_java_maven(tmp_path: Path) -> None:
    _touch(tmp_path / "pom.xml", "<project/>")
    info = detect_stack(tmp_path)
    assert info.primary == "java"


def test_detect_ruby(tmp_path: Path) -> None:
    _touch(tmp_path / "Gemfile", "source 'https://rubygems.org'\n")
    info = detect_stack(tmp_path)
    assert info.primary == "ruby"


def test_detect_php(tmp_path: Path) -> None:
    _touch(tmp_path / "composer.json", "{}")
    info = detect_stack(tmp_path)
    assert info.primary == "php"


def test_detect_elixir(tmp_path: Path) -> None:
    _touch(tmp_path / "mix.exs", "defmodule X.MixProject do\nend\n")
    info = detect_stack(tmp_path)
    assert info.primary == "elixir"


# --- multi-stack handling --------------------------------------------------


def test_python_and_javascript_monorepo_root(tmp_path: Path) -> None:
    _touch(tmp_path / "pyproject.toml", "[project]\n")
    _touch(tmp_path / "package.json", "{}")
    info = detect_stack(tmp_path)
    assert info.primary == "python"
    assert "javascript" in info.secondary
    assert info.is_multi_stack
    # markers must contain both hits.
    stacks_in_markers = {s for s, _ in info.markers}
    assert {"python", "javascript"}.issubset(stacks_in_markers)


def test_python_multiple_markers_single_stack(tmp_path: Path) -> None:
    # pyproject.toml + requirements.txt → still python-primary, no secondary.
    _touch(tmp_path / "pyproject.toml", "[project]\n")
    _touch(tmp_path / "requirements.txt", "pytest\n")
    info = detect_stack(tmp_path)
    assert info.primary == "python"
    assert info.secondary == ()
    assert len(info.markers) == 2


def test_stacks_property_exposes_primary_and_secondary(tmp_path: Path) -> None:
    _touch(tmp_path / "tsconfig.json", "{}")
    _touch(tmp_path / "package.json", "{}")
    info = detect_stack(tmp_path)
    assert info.stacks == ("typescript", "javascript")


# --- tree walk -------------------------------------------------------------


def test_marker_at_ancestor_is_found(tmp_path: Path) -> None:
    _touch(tmp_path / "pyproject.toml", "[project]\n")
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    info = detect_stack(deep)
    assert info.primary == "python"
    assert info.markers[0][1] == (tmp_path / "pyproject.toml").resolve()


def test_nearest_ancestor_wins(tmp_path: Path) -> None:
    # Parent has pyproject, child has package.json → child wins (nearest).
    _touch(tmp_path / "pyproject.toml", "[project]\n")
    child = tmp_path / "web"
    child.mkdir()
    _touch(child / "package.json", "{}")
    info = detect_stack(child)
    assert info.primary == "javascript"
    assert info.secondary == ()  # python marker at parent level is ignored


def test_max_depth_guard(tmp_path: Path) -> None:
    # Marker is far above start; max_depth=1 prevents reaching it.
    _touch(tmp_path / "pyproject.toml", "[project]\n")
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    info = detect_stack(deep, max_depth=1)
    assert info.primary == "generic"


def test_accepts_file_path_as_start(tmp_path: Path) -> None:
    _touch(tmp_path / "pyproject.toml", "[project]\n")
    f = tmp_path / "some_module.py"
    f.write_text("x = 1\n")
    info = detect_stack(f)
    assert info.primary == "python"


# --- graceful fallback ----------------------------------------------------


def test_only_git_present_returns_generic(tmp_path: Path) -> None:
    # Spec verification criterion: "fails gracefully when only .git present"
    (tmp_path / ".git").mkdir()
    info = detect_stack(tmp_path)
    assert info.primary == "generic"
    assert info.secondary == ()
    assert info.markers == ()
    assert info.stacks == ()
    assert not info.is_multi_stack


def test_empty_directory_returns_generic(tmp_path: Path) -> None:
    info = detect_stack(tmp_path)
    assert info.primary == "generic"


def test_nonexistent_start_returns_generic(tmp_path: Path) -> None:
    bogus = tmp_path / "does-not-exist" / "deep" / "path"
    info = detect_stack(bogus)
    # bogus doesn't exist; walk from its parent upward finds nothing except
    # tmp_path siblings → generic.
    assert info.primary == "generic"


def test_string_start_is_accepted(tmp_path: Path) -> None:
    _touch(tmp_path / "go.mod", "module x\n")
    info = detect_stack(str(tmp_path))
    assert info.primary == "go"


# --- StackInfo properties -------------------------------------------------


def test_stackinfo_is_frozen() -> None:
    info = StackInfo(primary="python", secondary=(), markers=())
    with pytest.raises(AttributeError):
        info.primary = "go"  # type: ignore[misc]


def test_stacks_empty_for_generic() -> None:
    info = StackInfo(primary="generic", secondary=(), markers=())
    assert info.stacks == ()
    assert not info.is_multi_stack
