"""Shared fixtures for end-to-end tests.

Each test gets an isolated ``scratch_project`` tmp dir populated with:

- A stack marker (``pyproject.toml`` by default; individual tests can
  override) so the detector resolves to a known stack.
- Git-repo metadata (``.git/``) so the scratch dir looks like a repo.
- Empty ``.claude/`` scaffolding so hook path-writes work.

The fixtures also compute the repo root (two levels up from this file)
once and expose it as ``repo_root`` so tests can reference
``bin/platxa-memory`` and the ``hooks/`` / ``templates/`` trees without
every test recomputing paths.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLI_PATH = REPO_ROOT / "bin" / "platxa-memory"
HOOKS_DIR = REPO_ROOT / "hooks"
TEMPLATES_DIR = REPO_ROOT / "templates"


@pytest.fixture()
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture()
def cli_path() -> Path:
    return CLI_PATH


@pytest.fixture()
def hooks_dir() -> Path:
    return HOOKS_DIR


@pytest.fixture()
def templates_dir() -> Path:
    return TEMPLATES_DIR


@pytest.fixture()
def scratch_project(tmp_path: Path) -> Path:
    """A minimally populated scratch project: Python marker + .git + .claude."""
    project = tmp_path / "scratch"
    project.mkdir()
    (project / "pyproject.toml").write_text('[project]\nname = "scratch"\nversion = "0.0.0"\n')
    (project / ".git").mkdir()
    (project / ".claude").mkdir()
    return project


@pytest.fixture()
def auto_memory_dir(tmp_path: Path) -> Path:
    """A fresh auto-memory directory the test can populate + hand to hooks."""
    auto = tmp_path / "auto-memory"
    auto.mkdir()
    return auto
