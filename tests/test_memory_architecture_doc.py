"""Validates ``docs/memory-architecture.md``.

Documentation rots when it lies about file paths or drifts from the code
it describes. These tests pin the document to concrete reality:

- Every file path quoted in backticks must exist in the repo.
- All 5 architecture layers must be present (headers + descriptions).
- At least one ASCII/visual diagram must be shipped.
- Hook references must align with the hooks actually in ``hooks/``.
- Agent / skill references must align with the shipped directories.

The test avoids a Markdown AST parser — a regex pass over fenced-code
blocks and backtick spans is enough to enforce the invariants we care
about.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOC = REPO / "docs" / "memory-architecture.md"

EXPECTED_LAYER_HEADERS = (
    "1. CLAUDE.md hierarchy",
    "2. Path-scoped rules",
    "3. Auto memory",
    "4. Agent memory",
    "5. Instincts",
)

EXPECTED_HOOKS = (
    "hooks/session_start_hook.py",
    "hooks/pre_compact_hook.py",
    "hooks/post_compact_hook.py",
    "hooks/stop_hook.py",
    "hooks/pretool_stop_guard.py",
)

EXPECTED_SECTIONS = (
    "The five layers",
    "Loading order",
    "`/compact` survival matrix",
    "Per-project routing",
)


# --- helpers ---------------------------------------------------------------


def _doc_text() -> str:
    return DOC.read_text(encoding="utf-8")


def _backtick_paths(text: str) -> list[str]:
    """Return every backticked token that looks like a repo-relative path."""
    # Matches foo/bar.ext, foo/bar/*.md, a/b/c.py patterns. Rejects URLs
    # (anything containing ://), shell commands (start with `$`), and
    # bare env vars.
    hits: list[str] = []
    for match in re.finditer(r"`([A-Za-z0-9_./\-*<>{}]+)`", text):
        token = match.group(1)
        if "://" in token or token.startswith("$"):
            continue
        if token.startswith("/"):
            # Claude Code slash-commands (`/compact`, `/specify`, …) are
            # not repo-relative paths.
            continue
        if "/" not in token:
            continue
        if token.endswith("/"):
            continue
        hits.append(token)
    return hits


def _has_placeholders(path: str) -> bool:
    return any(ch in path for ch in "<>{}*")


# --- existence tests -------------------------------------------------------


def test_doc_exists_and_non_empty() -> None:
    assert DOC.is_file()
    assert DOC.stat().st_size > 0


def test_doc_is_non_trivial_length() -> None:
    # A 5-layer architecture + compact matrix + routing section cannot be
    # captured in a handful of lines; if it is, something is missing.
    lines = _doc_text().splitlines()
    assert len(lines) > 80, f"doc is only {len(lines)} lines — suspiciously thin"


# --- structural tests -----------------------------------------------------


def test_all_five_layers_present() -> None:
    text = _doc_text()
    for header in EXPECTED_LAYER_HEADERS:
        assert header in text, f"missing layer header: {header!r}"


def test_expected_top_level_sections_present() -> None:
    text = _doc_text()
    for section in EXPECTED_SECTIONS:
        assert section in text, f"missing section: {section!r}"


def test_ascii_diagram_present() -> None:
    text = _doc_text()
    # Box-drawing characters used in the layer diagram.
    assert "┌" in text and "└" in text, "expected a box-and-arrow ASCII diagram"


def test_compact_survival_matrix_is_a_table() -> None:
    text = _doc_text()
    assert "| Layer" in text or "| Layer " in text, (
        "expected a Markdown table in the /compact survival section"
    )
    # Each layer must appear in the table with a survival verdict.
    for layer in (
        "CLAUDE.md hierarchy",
        "Path-scoped rules",
        "Auto memory",
        "Agent memory",
        "Instincts",
    ):
        assert layer in text, f"matrix missing layer {layer!r}"


def _row_for(text: str, layer_name: str) -> str:
    """Return the matrix row mentioning ``layer_name`` (one line)."""
    for line in text.splitlines():
        if line.lstrip().startswith("|") and layer_name in line:
            return line
    raise AssertionError(f"no matrix row mentions {layer_name!r}")


def test_survival_row_1_attributes_claude_md_to_claude_code_not_hook() -> None:
    # Regression guard: the PostCompact hook does NOT re-inject the
    # CLAUDE.md hierarchy. Claude Code re-reads those files natively.
    # A previous revision of this doc wrongly attributed the recovery to
    # `PostCompact re-injects .claude/rules/*.md bodies` in row 1.
    row = _row_for(_doc_text(), "CLAUDE.md hierarchy")
    assert "Re-read natively" in row or "Claude Code" in row, (
        "row 1 must credit Claude Code (not PostCompact) with CLAUDE.md recovery"
    )
    assert ".claude/rules" not in row, (
        "row 1 (CLAUDE.md hierarchy) must NOT reference .claude/rules — that is row 2's mechanism"
    )


def test_survival_row_2_names_postcompact_and_rules() -> None:
    row = _row_for(_doc_text(), "Path-scoped rules")
    assert "PostCompact" in row
    assert ".claude/rules" in row


def test_survival_row_3_names_postcompact_and_memory_files() -> None:
    row = _row_for(_doc_text(), "Auto memory")
    assert "PostCompact" in row
    assert "MEMORY.md" in row


def test_survival_row_4_re_reads_on_dispatch() -> None:
    row = _row_for(_doc_text(), "Agent memory")
    assert "dispatched" in row or "dispatch" in row


def test_survival_row_5_not_re_injected() -> None:
    row = _row_for(_doc_text(), "Instincts")
    assert "Not re-injected" in row or "re-hydrate" in row


# --- path-truth tests -----------------------------------------------------


def test_all_hook_paths_exist() -> None:
    text = _doc_text()
    for hook in EXPECTED_HOOKS:
        assert hook in text, f"doc must reference {hook!r}"
        assert (REPO / hook).is_file(), f"{hook} referenced but not shipped"


def test_backticked_paths_that_look_concrete_exist() -> None:
    # Every backticked token containing a '/' and lacking placeholder
    # characters must correspond to a real file on disk. Tokens with <>
    # / {} / * are treated as patterns and skipped.
    text = _doc_text()
    missing: list[str] = []
    for token in _backtick_paths(text):
        if _has_placeholders(token):
            continue
        if (REPO / token).exists():
            continue
        missing.append(token)
    assert not missing, f"backticked paths referenced but missing: {missing}"


def test_referenced_agents_exist() -> None:
    agents_dir = REPO / "agents"
    text = _doc_text()
    for agent in ("memory-curator", "memory-synthesizer", "memory-researcher", "memory-auditor"):
        assert agent in text, f"doc must mention the {agent} agent"
        assert (agents_dir / f"{agent}.md").is_file(), f"{agent}.md not shipped"


def test_referenced_skills_exist() -> None:
    skills_dir = REPO / "skills"
    text = _doc_text()
    for skill in ("memory-init", "memory-status", "memory-search", "memory-doctor"):
        assert skill in text, f"doc must mention the {skill} skill"
        assert (skills_dir / skill / "SKILL.md").is_file(), f"{skill}/SKILL.md not shipped"


def test_referenced_cli_exists() -> None:
    text = _doc_text()
    assert "bin/platxa-memory" in text
    assert (REPO / "bin" / "platxa-memory").is_file()


def test_referenced_src_modules_exist() -> None:
    text = _doc_text()
    for module in ("src/platxa_memory/stack.py", "src/platxa_memory/atomic.py"):
        assert module in text, f"doc must reference {module}"
        assert (REPO / module).is_file()


# --- environment-variable tests -------------------------------------------


def test_documented_env_vars_are_the_ones_hooks_read() -> None:
    text = _doc_text()
    # Env vars that actually affect hook behaviour (grep the hooks/ tree
    # to verify the canonical list). The doc must at least mention them.
    canonical = {
        "PLATXA_MEMORY_TOKEN_BUDGET",
        "PLATXA_MEMORY_AUTO_DIR",
        "PLATXA_MEMORY_PRECOMPACT_OVERRIDE",
        "PLATXA_MEMORY_STOP_SYNTH_DISABLE",
        "CLAUDE_PROJECT_DIR",
    }
    missing = [v for v in canonical if v not in text]
    assert not missing, f"doc is silent about env vars: {missing}"
