#!/usr/bin/env python3
"""SessionStart hook for platxa-memory.

Reads the user-project auto memory (MEMORY.md + topic files), scans instincts,
detects the primary stack, and emits a single ``additionalContext`` string
inside the Claude Code SessionStart JSON envelope. Respects an opt-in token
budget and degrades gracefully when any source dir is missing.

Hard constraint (see CLAUDE.md): stdlib only — no Anthropic SDK, no API, no
LLM calls. This script does deterministic file IO and string shaping.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# --- constants --------------------------------------------------------------

CHARS_PER_TOKEN = 4  # documented rough estimate; see skills/memory-status
DEFAULT_BUDGET_TOKENS = 25_000
MIN_BUDGET_TOKENS = 500  # refuse smaller budgets — they cannot carry MEMORY.md
HARD_CAP_TOKENS = 200_000  # refuse larger budgets; misconfig guard

STACK_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("python", ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")),
    ("typescript", ("tsconfig.json",)),
    ("javascript", ("package.json",)),
    ("go", ("go.mod",)),
    ("rust", ("Cargo.toml",)),
)


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
    """Resolve the current project directory."""
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())


def _detect_stack(project: Path) -> str:
    """Return the primary stack name or ``generic`` when no marker matches."""
    for stack, markers in STACK_MARKERS:
        for marker in markers:
            if (project / marker).is_file():
                return stack
    return "generic"


def _auto_memory_candidate() -> Path | None:
    """Locate the most-recently-modified auto-memory dir under ``~/.claude/projects``.

    Claude Code hashes the repo path into an internal key, which we cannot
    compute here. The most-recent-mtime heuristic is an honest best-effort —
    downstream consumers can override by exporting ``PLATXA_MEMORY_AUTO_DIR``.
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
    """Assemble a single text block from MEMORY.md + topic files under the budget.

    Returns (text, chars_used). Always safe — missing dirs produce ''.
    """
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


def _collect_instincts(project: Path, budget_chars: int) -> tuple[str, int]:
    """Collect instinct file names/confidence if any. Bodies are NOT dumped."""
    if budget_chars <= 0:
        return "", 0
    roots = [project / ".claude" / "instincts", Path.home() / ".claude" / "instincts"]
    lines: list[str] = []
    for root in roots:
        if not root.is_dir():
            continue
        try:
            for p in sorted(root.iterdir()):
                if p.suffix.lower() in {".yaml", ".yml", ".json"}:
                    lines.append(f"- {p}")
        except OSError:
            continue
    if not lines:
        return "", 0
    text = "=== instincts (index only) ===\n" + "\n".join(lines)
    if len(text) > budget_chars:
        text = text[:budget_chars]
    return text, len(text)


def build_context() -> dict:
    """Build the additionalContext payload. Always returns a dict (never raises)."""
    budget_tokens = _token_budget()
    budget_chars = budget_tokens * CHARS_PER_TOKEN
    project = _project_dir()
    stack = _detect_stack(project)
    auto_dir = _auto_memory_candidate()

    memory_text, mem_used = _collect_memory(auto_dir, budget_chars)
    remaining = max(0, budget_chars - mem_used)
    instincts_text, ins_used = _collect_instincts(project, remaining)

    lines: list[str] = [
        f"[platxa-memory] stack={stack} project={project}",
        (
            f"[platxa-memory] auto-memory: {auto_dir}"
            if auto_dir is not None
            else "[platxa-memory] auto-memory: (none detected — ~/.claude/projects missing or empty)"
        ),
        (
            f"[platxa-memory] budget={budget_tokens} tok "
            f"(mem={mem_used // CHARS_PER_TOKEN} tok, instincts={ins_used // CHARS_PER_TOKEN} tok)"
        ),
    ]
    if memory_text:
        lines.append("")
        lines.append(memory_text)
    if instincts_text:
        lines.append("")
        lines.append(instincts_text)

    additional = "\n".join(lines)
    return {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": additional,
        }
    }


def main() -> int:
    # Consume stdin but do not parse — SessionStart payload is not used here.
    try:
        sys.stdin.read()
    except OSError:
        pass

    try:
        payload = build_context()
    except Exception as exc:  # graceful: hooks MUST NOT crash the session
        # Log to stderr so the message in additionalContext is actually actionable.
        sys.stderr.write(f"[platxa-memory session_start_hook] {type(exc).__name__}: {exc}\n")
        payload = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "[platxa-memory] hook failed silently; see stderr for details",
            }
        }

    sys.stdout.write(json.dumps(payload))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
