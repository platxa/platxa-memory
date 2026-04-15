"""Validates the CLAUDE.md + AGENTS.md skeleton templates.

Spec verification criterion for feature #32:
    "Template is valid markdown; imports under 5-hop limit; length compliant"

The tests cover:
- Both files exist and are non-empty.
- CLAUDE.md is <= 200 lines (the spec's length cap).
- All active ``@import`` references (not inside HTML comments) resolve to
  paths that look well-formed: relative, no ``..``, no absolute prefix,
  existing target under ``templates/`` OR a valid placeholder path (for
  imports users will uncomment after copying the template into their repo).
- Transitive import depth does not exceed Claude Code's 5-hop limit.
- AGENTS.md imports CLAUDE.md so the two stay in sync.
- Basic Markdown well-formedness: each heading hierarchy level appears
  before its subheadings (no jump from # to ### without ## in between).
"""

from __future__ import annotations

import re
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
CLAUDE_MD = TEMPLATES_DIR / "CLAUDE.md"
AGENTS_MD = TEMPLATES_DIR / "AGENTS.md"

MAX_LINES = 200
MAX_HOP_DEPTH = 5

# Match @import at start of line (possibly after whitespace), capturing the path.
# Disallows the @ appearing inside URLs or e-mail addresses.
IMPORT_RE = re.compile(r"^\s*@([A-Za-z0-9_./\-]+\.md)\s*$", re.MULTILINE)


# --- helpers ---------------------------------------------------------------


def _strip_html_comments(text: str) -> str:
    """Remove <!-- ... --> blocks (non-greedy, multi-line) before scanning."""
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def _active_imports(text: str) -> list[str]:
    """Return @import paths that are NOT inside HTML comments."""
    stripped = _strip_html_comments(text)
    return IMPORT_RE.findall(stripped)


def _resolve_import_target(base: Path, import_path: str) -> Path | None:
    """Resolve an @import relative to ``base`` and return the file path if it
    exists within the templates/ tree; otherwise None (it may be a skeleton
    placeholder like ``.claude/rules/foo.md`` that only exists after copy).
    """
    candidate = (base.parent / import_path).resolve()
    try:
        candidate.relative_to(TEMPLATES_DIR.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _max_import_depth(start: Path, visited: set[Path] | None = None) -> int:
    """Walk @imports recursively through files that resolve on disk. Skeleton
    placeholders (unresolvable) count as a single hop and terminate descent.
    """
    if visited is None:
        visited = set()
    if start in visited:
        return 0  # cycle — treat as depth 0 to avoid double-counting.
    visited.add(start)

    text = start.read_text(encoding="utf-8")
    imports = _active_imports(text)
    if not imports:
        return 0

    best = 0
    for imp in imports:
        target = _resolve_import_target(start, imp)
        if target is None:
            depth = 1  # unresolved leaf counts as one hop
        else:
            depth = 1 + _max_import_depth(target, visited.copy())
        best = max(best, depth)
    return best


# --- tests ------------------------------------------------------------------


def test_claude_md_exists_and_non_empty() -> None:
    assert CLAUDE_MD.is_file(), f"{CLAUDE_MD} missing"
    assert CLAUDE_MD.stat().st_size > 0


def test_agents_md_exists_and_non_empty() -> None:
    assert AGENTS_MD.is_file(), f"{AGENTS_MD} missing"
    assert AGENTS_MD.stat().st_size > 0


def test_claude_md_length_under_200_lines() -> None:
    n = sum(1 for _ in CLAUDE_MD.read_text(encoding="utf-8").splitlines())
    assert n <= MAX_LINES, f"CLAUDE.md is {n} lines; spec cap is {MAX_LINES}"


def test_agents_md_length_under_200_lines() -> None:
    # AGENTS.md is a shim; any real bloat is a smell.
    n = sum(1 for _ in AGENTS_MD.read_text(encoding="utf-8").splitlines())
    assert n <= MAX_LINES


def test_agents_md_imports_claude_md() -> None:
    imports = _active_imports(AGENTS_MD.read_text(encoding="utf-8"))
    assert "CLAUDE.md" in imports, "AGENTS.md must @import CLAUDE.md so the two stay in sync"


def test_claude_md_active_imports_are_commented_placeholders() -> None:
    # The skeleton should ship with all stack imports INSIDE HTML comments
    # so copying the template doesn't trigger resolution errors. Users
    # uncomment the line for their stack. The only active import anywhere
    # in templates/ should be AGENTS.md -> CLAUDE.md.
    active = _active_imports(CLAUDE_MD.read_text(encoding="utf-8"))
    assert active == [], f"CLAUDE.md skeleton should have no active @imports; found: {active}"


def test_import_depth_within_limit_from_agents() -> None:
    depth = _max_import_depth(AGENTS_MD)
    assert depth <= MAX_HOP_DEPTH, f"AGENTS.md transitive depth {depth} > {MAX_HOP_DEPTH}"


def test_import_depth_within_limit_from_claude() -> None:
    depth = _max_import_depth(CLAUDE_MD)
    assert depth <= MAX_HOP_DEPTH, f"CLAUDE.md transitive depth {depth} > {MAX_HOP_DEPTH}"


def test_no_import_uses_absolute_or_parent_traversal() -> None:
    for f in (CLAUDE_MD, AGENTS_MD):
        text = _strip_html_comments(f.read_text(encoding="utf-8"))
        for match in re.finditer(r"^\s*@(\S+\.md)", text, re.MULTILINE):
            imp = match.group(1)
            assert not imp.startswith("/"), f"{f.name}: absolute import {imp!r}"
            assert ".." not in Path(imp).parts, f"{f.name}: parent traversal in {imp!r}"


def test_heading_hierarchy_well_formed() -> None:
    # No heading level should skip a parent (e.g. "#" directly followed by "###").
    # Skip fenced code blocks — a shell comment like "# TODO: ..." inside
    # ```bash fences is not a Markdown heading.
    text = CLAUDE_MD.read_text(encoding="utf-8")
    prev_level = 0
    in_fence = False
    for i, line in enumerate(text.splitlines(), start=1):
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = re.match(r"^(#{1,6})\s", line)
        if not match:
            continue
        level = len(match.group(1))
        if prev_level and level > prev_level + 1:
            raise AssertionError(
                f"{CLAUDE_MD.name}:{i}: heading jumped from H{prev_level} to H{level}"
            )
        prev_level = level


def test_commented_imports_reference_shipped_rule_files() -> None:
    # Every commented-out @import line in CLAUDE.md must name a rule file
    # that actually exists under the MATCHING stack directory. A loose
    # "any stack has it" check would miss a relocated or renamed file.
    text = CLAUDE_MD.read_text(encoding="utf-8")
    comment_imports = re.findall(r"<!--\s*@\.claude/rules/([A-Za-z0-9_\-]+\.md)\s*-->", text)
    assert comment_imports, "expected commented @.claude/rules/* placeholders"

    # Build the (stack, filename) matrix actually shipped.
    shipped_pairs = {
        (p.parent.parent.parent.name, p.name) for p in TEMPLATES_DIR.glob("*/.claude/rules/*.md")
    }

    # 7 stacks × 2 rule files each = 14 ships total (see feature #31).
    assert len(shipped_pairs) == 14, f"expected 14 stack rule files, found {len(shipped_pairs)}"
    stacks_with_rules = {stack for stack, _ in shipped_pairs}
    assert len(stacks_with_rules) == 7, (
        f"expected 7 stacks with rules, found {len(stacks_with_rules)}: {sorted(stacks_with_rules)}"
    )
    for stack in stacks_with_rules:
        count = sum(1 for s, _ in shipped_pairs if s == stack)
        assert count == 2, f"stack {stack!r} has {count} rule files, expected 2"

    # Every commented import must match a shipped (stack, filename) pair
    # where the filename prefix identifies the stack
    # ("python-style.md" -> stack "python", "monorepo-workspaces.md" -> "monorepo").
    for filename in comment_imports:
        prefix = filename.split("-", 1)[0]
        assert (prefix, filename) in shipped_pairs, (
            f"commented import {filename!r} has no shipped counterpart at "
            f"templates/{prefix}/.claude/rules/{filename}"
        )


def test_import_regex_is_anchored() -> None:
    # Guard-rail: @foo in the middle of prose must NOT be picked up.
    sample = "This is a sentence mentioning @something inline.\n@CLAUDE.md\n"
    assert _active_imports(sample) == ["CLAUDE.md"]
