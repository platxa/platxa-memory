"""Validates the stack-profile template bundle under ``templates/``.

The spec's verification criterion for feature #31 is:
    "Each template renders into valid .claude/rules/ structure;
     paths: use correct globs"

These tests enforce that every shipped template:
- exists at the expected path
- contains a non-empty ``.claude/rules/`` directory
- every ``*.md`` under that directory has valid YAML frontmatter with
  ``name``, ``description``, and ``paths`` fields
- every glob in ``paths`` is a relative, non-empty string

YAML frontmatter is parsed with a minimal stdlib-only parser (the plugin
itself is stdlib-only) so the tests run in any environment.
"""

from __future__ import annotations

from pathlib import Path

import pytest

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

EXPECTED_STACKS = (
    "python",
    "typescript",
    "go",
    "rust",
    "java",
    "ruby",
    "monorepo",
)


# --- minimal YAML frontmatter parser ----------------------------------------


def _parse_frontmatter(text: str) -> dict[str, object]:
    """Parse a '--- ... ---' YAML frontmatter block.

    Supports the exact subset used by our rule files: scalar ``name`` and
    ``description`` entries, plus a ``paths:`` list with dash-prefixed
    string items. Raises ``ValueError`` on malformed input.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing opening '---' fence")
    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i
            break
    if end is None:
        raise ValueError("missing closing '---' fence")

    body = lines[1:end]
    out: dict[str, object] = {}
    i = 0
    while i < len(body):
        line = body[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        if line.startswith(" ") or line.startswith("\t"):
            raise ValueError(f"unexpected indent at top-level: {line!r}")
        if ":" not in line:
            raise ValueError(f"malformed frontmatter line: {line!r}")
        key, _, rest = line.partition(":")
        key = key.strip()
        rest = rest.strip()
        if rest:
            out[key] = _parse_scalar(rest)
            i += 1
            continue
        # List under this key: subsequent lines start with "  - ".
        items: list[str] = []
        i += 1
        while i < len(body):
            nxt = body[i]
            stripped = nxt.strip()
            if not stripped or stripped.startswith("#"):
                i += 1
                continue
            if not nxt.startswith(" "):
                break
            if not stripped.startswith("- "):
                raise ValueError(f"expected list item, got: {nxt!r}")
            items.append(_parse_scalar(stripped[2:].strip()))
            i += 1
        out[key] = items
    return out


def _parse_scalar(value: str) -> str:
    value = value.strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


# --- discovery helpers ------------------------------------------------------


def _rule_files(stack: str) -> list[Path]:
    rules = TEMPLATES_DIR / stack / ".claude" / "rules"
    if not rules.is_dir():
        return []
    return sorted(rules.glob("*.md"))


# --- tests ------------------------------------------------------------------


def test_templates_readme_exists() -> None:
    readme = TEMPLATES_DIR / "README.md"
    assert readme.is_file(), f"{readme} missing"
    assert readme.stat().st_size > 0


@pytest.mark.parametrize("stack", EXPECTED_STACKS)
def test_each_stack_has_claude_rules_dir(stack: str) -> None:
    rules = TEMPLATES_DIR / stack / ".claude" / "rules"
    assert rules.is_dir(), f"missing .claude/rules/ for {stack}"
    mds = list(rules.glob("*.md"))
    assert mds, f"{stack}/.claude/rules/ must contain at least one .md rule"


@pytest.mark.parametrize("stack", EXPECTED_STACKS)
def test_every_rule_has_frontmatter_with_paths(stack: str) -> None:
    files = _rule_files(stack)
    assert files, f"no rule files for {stack}"
    for path in files:
        text = path.read_text(encoding="utf-8")
        try:
            fm = _parse_frontmatter(text)
        except ValueError as exc:
            pytest.fail(f"{path}: frontmatter parse failed: {exc}")

        # Required keys
        for key in ("name", "description", "paths"):
            assert key in fm, f"{path}: missing '{key}' in frontmatter"

        name = fm["name"]
        desc = fm["description"]
        paths = fm["paths"]
        assert isinstance(name, str) and name.strip(), f"{path}: empty name"
        assert isinstance(desc, str) and desc.strip(), f"{path}: empty description"
        assert isinstance(paths, list) and paths, f"{path}: paths must be non-empty list"

        for glob in paths:
            assert isinstance(glob, str), f"{path}: glob must be string, got {glob!r}"
            assert glob.strip(), f"{path}: empty glob entry"
            assert not glob.startswith("/"), f"{path}: absolute glob {glob!r}"
            # Reject obviously-broken globs (unbalanced brackets).
            assert glob.count("[") == glob.count("]"), f"{path}: unbalanced brackets in {glob!r}"


@pytest.mark.parametrize("stack", EXPECTED_STACKS)
def test_rule_body_is_non_empty(stack: str) -> None:
    for path in _rule_files(stack):
        text = path.read_text(encoding="utf-8")
        _, _, body = text.partition("---\n")
        _, _, body = body.partition("---\n")
        assert body.strip(), f"{path}: body is empty after frontmatter"


def test_frontmatter_names_are_unique_within_repo() -> None:
    seen: dict[str, Path] = {}
    for stack in EXPECTED_STACKS:
        for path in _rule_files(stack):
            fm = _parse_frontmatter(path.read_text(encoding="utf-8"))
            name = fm["name"]
            assert isinstance(name, str)
            assert name not in seen, f"duplicate rule name {name!r} in {path} and {seen[name]}"
            seen[name] = path


def test_stack_names_match_detect_stack_labels() -> None:
    # Every template directory name must match one of the CLI's stack labels
    # (except "monorepo" which the CLI does not auto-detect). This keeps the
    # template set aligned with what `platxa-memory detect-stack` can return.
    cli_labels = {
        "python",
        "typescript",
        "javascript",
        "go",
        "rust",
        "java",
        "ruby",
        "generic",
    }
    for stack in EXPECTED_STACKS:
        if stack == "monorepo":
            continue
        assert stack in cli_labels, f"template {stack!r} not a CLI stack label"


def test_frontmatter_parser_smoke() -> None:
    # Guard-rail: the minimal parser must handle the exact shape we ship.
    text = """---
name: sample
description: one-liner
paths:
  - "a/**/*.py"
  - "b/c.py"
---

body
"""
    fm = _parse_frontmatter(text)
    assert fm["name"] == "sample"
    assert fm["description"] == "one-liner"
    assert fm["paths"] == ["a/**/*.py", "b/c.py"]


def test_frontmatter_parser_rejects_missing_fence() -> None:
    with pytest.raises(ValueError):
        _parse_frontmatter("no fence here\nname: x\n")
