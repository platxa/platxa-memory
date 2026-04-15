"""Validates ``.github/workflows/ci.yml`` structure.

Spec verification criterion for feature #45:
    "CI green on a reference commit; regressions fail the build"

The "CI green" half requires actual GitHub Actions runs and lives outside
this test suite. This module enforces the shape that makes those runs
meaningful:

- The workflow file exists and parses as YAML (minimal stdlib-only
  parser — we don't add PyYAML to the dev deps just for this).
- The required triggers are wired (``push`` on main + tags, ``pull_request``
  on main).
- The canonical quality gates are present as named steps inside the
  test job (``ruff check``, ``ruff format --check``, ``pyright``,
  ``pytest``).
- The Python matrix covers 3.10, 3.11, 3.12 (pyproject declares
  ``requires-python = ">=3.10"``).
- A manifest job runs JSON-structure checks on ``plugin.json`` and
  ``marketplace-entry.json``.
- The release gate is tag-scoped and depends on the quality jobs.

The parser is a narrow line-based reader — good enough for the two
invariants we care about (step names + job names + trigger keys). If
the workflow file stops being literally readable this way, the tests
will correctly fail and we'll upgrade to PyYAML.
"""

from __future__ import annotations

import re
from pathlib import Path

CI = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"


def _text() -> str:
    return CI.read_text(encoding="utf-8")


def _step_names(text: str) -> list[str]:
    """Return every ``- name: <X>`` step name as a list."""
    return re.findall(r"^\s*-\s*name:\s*(.+?)\s*$", text, re.MULTILINE)


def _top_level_block(text: str, key: str) -> str:
    """Return the indented block under a top-level ``key:`` line, or ''."""
    lines = text.splitlines()
    inside = False
    out: list[str] = []
    for line in lines:
        if not inside:
            if re.match(rf"^{re.escape(key)}:\s*$", line):
                inside = True
            continue
        if line and not line.startswith((" ", "\t")):
            break
        out.append(line)
    return "\n".join(out)


# --- existence + parse ----------------------------------------------------


def test_ci_workflow_exists() -> None:
    assert CI.is_file(), f"{CI} missing"
    assert CI.stat().st_size > 0


def test_ci_workflow_parses_as_yaml_shape() -> None:
    # Not a full YAML parser — just sanity-checks that the file has the
    # top-level keys we need (``name``, ``on``, ``jobs``).
    text = _text()
    for key in ("name:", "on:", "jobs:"):
        assert key in text, f"ci.yml missing top-level {key!r}"


# --- triggers -------------------------------------------------------------


def test_triggers_include_push_and_pr_and_tags() -> None:
    on_block = _top_level_block(_text(), "on")
    # Sanity-check the three triggers we care about.
    assert "push:" in on_block, "CI should trigger on push"
    assert "pull_request:" in on_block, "CI should trigger on pull_request"
    assert re.search(r'tags:\s*\[\s*"v\*"\s*\]', on_block) or 'tags: ["v*"]' in on_block, (
        'CI should trigger on tags matching "v*"'
    )


# --- required quality gates ------------------------------------------------


def test_ruff_check_step_present() -> None:
    names = _step_names(_text())
    assert any("Ruff check" in n for n in names), f"'Ruff check' step missing; steps: {names}"


def test_ruff_format_step_present() -> None:
    names = _step_names(_text())
    assert any("Ruff format" in n for n in names), f"'Ruff format' step missing; steps: {names}"
    # Silent-gate guard: `ruff format .` without `--check` rewrites files
    # and exits 0 unconditionally, turning the gate into a no-op. Pin the
    # literal flag so it cannot silently regress.
    assert "ruff format --check" in _text(), (
        "`ruff format` step must use `--check` so the gate actually fails "
        "on unformatted code; without it CI would always be green"
    )


def test_pyright_step_present() -> None:
    names = _step_names(_text())
    assert any("Pyright" in n for n in names), f"Pyright step missing; steps: {names}"


def test_pytest_step_present() -> None:
    names = _step_names(_text())
    assert any("Pytest" in n.lower() or "pytest" in n.lower() for n in names), (
        f"Pytest step missing; steps: {names}"
    )


# --- python version matrix ------------------------------------------------


def test_python_matrix_covers_supported_versions() -> None:
    text = _text()
    # pyproject.toml declares requires-python = ">=3.10"; ensure matrix
    # exercises at least three consecutive point releases.
    for version in ("3.10", "3.11", "3.12"):
        assert f'"{version}"' in text, f"Python matrix missing {version!r}"


# --- manifest job ---------------------------------------------------------


def test_manifest_validation_job_exists() -> None:
    text = _text()
    # Job key names show up left-aligned in the ``jobs:`` block.
    jobs_block = _top_level_block(text, "jobs")
    assert re.search(r"^\s{2}manifest:\s*$", jobs_block, re.MULTILINE), (
        "CI should have a 'manifest' job that validates plugin.json + marketplace-entry.json"
    )
    assert "plugin.json" in text, "manifest job must reference plugin.json"
    assert "marketplace-entry.json" in text, "manifest job must reference marketplace-entry.json"


def test_manifest_job_validates_hook_commands() -> None:
    text = _text()
    # Regression guard against the prior "Stop + PreToolUse missing"
    # drift — CI must check every hook command resolves to a real file.
    # We pin the load-bearing fragments of the heredoc rather than just
    # the `CLAUDE_PLUGIN_ROOT` substring (which appears in plugin.json
    # regardless and would pass even if the check were deleted).
    assert "Path(rel).is_file()" in text, (
        "manifest job must call Path(rel).is_file() to verify hook commands "
        "point at real files on disk"
    )
    assert '{"command", "http"}' in text, (
        "manifest job must whitelist hook types against the CLAUDE.md hard "
        "constraint (command and http only)"
    )
    assert "Verify every hook command points at a real file" in text, (
        "manifest job should keep a named step describing the hook-path check "
        "so failures are attributable in CI logs"
    )


# --- release gate ---------------------------------------------------------


def test_release_gate_is_tag_scoped_and_depends_on_quality_jobs() -> None:
    text = _text()
    jobs_block = _top_level_block(text, "jobs")
    assert re.search(r"^\s{2}release-gate:\s*$", jobs_block, re.MULTILINE), (
        "CI should have a 'release-gate' job"
    )
    # Gate must only run on version tags.
    assert "startsWith(github.ref, 'refs/tags/v')" in text, (
        "release gate must be scoped to 'refs/tags/v*' tags"
    )
    # Gate must wait for test + manifest jobs.
    assert re.search(r"needs:\s*\[\s*test\s*,\s*manifest\s*\]", text), (
        "release gate must declare needs: [test, manifest]"
    )


# --- cache + concurrency --------------------------------------------------


def test_pip_cache_is_enabled() -> None:
    # Tiny optimisation guard — without `cache: pip` the matrix reinstalls
    # ruff + pyright + pytest on every run.
    assert "cache: pip" in _text()


def test_concurrency_group_is_set() -> None:
    # Cancelling superseded PR runs keeps CI queue latency bounded.
    text = _text()
    assert "concurrency:" in text
    assert "cancel-in-progress" in text
