#!/usr/bin/env python3
"""PostCompact hook for platxa-memory.

Fires immediately after Claude Code compacts the session. Re-injects the
contents that Claude most likely just lost to compaction: the auto-memory
``MEMORY.md`` index (plus a budgeted slice of sibling ``*.md`` topic files)
and every ``*.md`` file under ``.claude/rules/``. Output is a single
``additionalContext`` string inside the PostCompact JSON envelope.

Design notes:
- This hook is the mirror image of ``session_start_hook.py`` but scoped to
  what compaction specifically evicts: long-lived project rules and the
  auto-memory index. It intentionally does NOT re-inject instincts — those
  belong to SessionStart and the PostCompact context is already tight.
- Token budget is shared with ``session_start_hook`` via the same
  ``PLATXA_MEMORY_TOKEN_BUDGET`` env var so operators tune one number.
- Critical invariant: hooks MUST NOT crash the session. Any exception
  falls through to a benign additionalContext and exit 0.

Hard constraint (see CLAUDE.md): stdlib only — no SDK, no API, no LLM.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# --- constants --------------------------------------------------------------

CHARS_PER_TOKEN = 4  # documented heuristic; matches session_start_hook
DEFAULT_BUDGET_TOKENS = 25_000
MIN_BUDGET_TOKENS = 500
HARD_CAP_TOKENS = 200_000


def _token_budget() -> int:
    """Resolve the memory-token budget from env with sane fallbacks."""
    raw = os.environ.get("PLATXA_MEMORY_TOKEN_BUDGET", "")
    if not raw.strip():
        return DEFAULT_BUDGET_TOKENS
    try:
        val = int(raw)
    except ValueError:
        return DEFAULT_BUDGET_TOKENS
    if val < MIN_BUDGET_TOKENS or val > HARD_CAP_TOKENS:
        return DEFAULT_BUDGET_TOKENS
    return val


def _project_dir() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())


def _auto_memory_candidate() -> Path | None:
    """Find the user's most-recently-modified auto-memory dir.

    Claude Code hashes the repo path into an internal key which the hook
    cannot compute, so we fall back to the same mtime heuristic used by
    session_start_hook. ``PLATXA_MEMORY_AUTO_DIR`` overrides.
    """
    override = os.environ.get("PLATXA_MEMORY_AUTO_DIR", "").strip()
    if override:
        p = Path(override).expanduser()
        return p if p.is_dir() else None

    root = Path.home() / ".claude" / "projects"
    if not root.is_dir():
        return None

    candidates: list[tuple[float, Path]] = []
    try:
        for entry in root.iterdir():
            mem = entry / "memory"
            if mem.is_dir():
                candidates.append((mem.stat().st_mtime, mem))
    except OSError:
        return None

    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _read_text_safe(path: Path, max_chars: int) -> str:
    """Read up to ``max_chars`` characters from ``path``. Returns '' on failure."""
    if max_chars <= 0 or not path.is_file():
        return ""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return fh.read(max_chars)
    except OSError:
        return ""


def _collect_memory(auto_dir: Path | None, budget_chars: int) -> tuple[str, int]:
    """Assemble ``MEMORY.md`` plus sibling topic files under the budget."""
    if auto_dir is None or budget_chars <= 0:
        return "", 0

    parts: list[str] = []
    used = 0
    index = auto_dir / "MEMORY.md"
    if index.is_file():
        body = _read_text_safe(index, budget_chars - used)
        if body:
            parts.append(f"=== MEMORY.md ({index}) ===\n{body}")
            used += len(body)

    try:
        topic_files = sorted(p for p in auto_dir.glob("*.md") if p.name != "MEMORY.md")
    except OSError:
        topic_files = []

    for topic in topic_files:
        remaining = budget_chars - used
        if remaining <= 0:
            break
        body = _read_text_safe(topic, remaining)
        if body:
            parts.append(f"=== {topic.name} ===\n{body}")
            used += len(body)

    return "\n\n".join(parts), used


def _collect_rules(project: Path, budget_chars: int) -> tuple[str, int]:
    """Assemble every .md file under ``.claude/rules/`` under the budget.

    Rules are path-scoped (their YAML frontmatter declares which file globs
    they target), but after compaction Claude has lost the scoping context
    too. Re-inject the rule bodies in full so the path-scope hook on the
    NEXT file read can re-trigger them if applicable.
    """
    rules_dir = project / ".claude" / "rules"
    if not rules_dir.is_dir() or budget_chars <= 0:
        return "", 0

    try:
        rule_files = sorted(rules_dir.glob("*.md"))
    except OSError:
        return "", 0

    parts: list[str] = []
    used = 0
    for rule in rule_files:
        remaining = budget_chars - used
        if remaining <= 0:
            break
        body = _read_text_safe(rule, remaining)
        if body:
            parts.append(f"=== .claude/rules/{rule.name} ===\n{body}")
            used += len(body)

    return "\n\n".join(parts), used


def build_context() -> dict:
    """Build the additionalContext payload. Never raises."""
    budget_tokens = _token_budget()
    budget_chars = budget_tokens * CHARS_PER_TOKEN
    project = _project_dir()
    auto_dir = _auto_memory_candidate()

    # Split budget 60/40 between memory and rules: memory is usually larger,
    # but rules are non-negotiable after a compact (they encode the how).
    mem_budget = int(budget_chars * 0.6)
    rules_budget = budget_chars - mem_budget

    memory_text, mem_used = _collect_memory(auto_dir, mem_budget)
    rules_text, rules_used = _collect_rules(project, rules_budget)

    lines: list[str] = [
        f"[platxa-memory post-compact] project={project}",
        (
            f"[platxa-memory post-compact] auto-memory: {auto_dir}"
            if auto_dir is not None
            else "[platxa-memory post-compact] auto-memory: (none detected)"
        ),
        (
            f"[platxa-memory post-compact] budget={budget_tokens} tok "
            f"(memory={mem_used // CHARS_PER_TOKEN} tok, "
            f"rules={rules_used // CHARS_PER_TOKEN} tok)"
        ),
    ]
    if memory_text:
        lines.append("")
        lines.append(memory_text)
    if rules_text:
        lines.append("")
        lines.append(rules_text)

    additional = "\n".join(lines)
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostCompact",
            "additionalContext": additional,
        }
    }


def main() -> int:
    # Consume stdin — PostCompact payload fields are not used here.
    try:
        sys.stdin.read()
    except OSError:
        pass

    try:
        payload = build_context()
    except Exception as exc:
        sys.stderr.write(f"[platxa-memory post_compact_hook] {type(exc).__name__}: {exc}\n")
        payload = {
            "hookSpecificOutput": {
                "hookEventName": "PostCompact",
                "additionalContext": "[platxa-memory] post-compact hook failed; see stderr",
            }
        }

    sys.stdout.write(json.dumps(payload))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
