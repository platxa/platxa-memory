#!/usr/bin/env python3
"""PreCompact hook for platxa-memory.

Fires just before Claude Code compacts the session. Scans the progress log
(.claude/claude-progress.txt) for unsaved session insights — any feature
whose most recent record is NOT a terminal status (PASSED / FAILED /
SKIPPED) — and blocks the compaction with exit 2 when anything is
outstanding. The user can override via ``PLATXA_MEMORY_PRECOMPACT_OVERRIDE=1``.

RESOLVED is deliberately NOT terminal: a feature that went BLOCKED →
RESOLVED has recovered from an obstacle but has not yet been verified
passed/failed/skipped, so the insight about the recovery is still worth
saving before compaction evicts it.

Rationale: Claude Code compaction drops the conversation buffer. If a feature
is half-done and the progress log reflects that, compaction without
save-first will amnesia the only durable record of where work stood.

Hard constraint (see CLAUDE.md): stdlib only — no SDK, no API, no LLM.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DEFAULT_PROGRESS_PATH = ".claude/claude-progress.txt"
# How many tail lines to scan for pending-work detection. The progress log
# is append-only; old entries cannot become "unsaved" retroactively.
TAIL_LIMIT = 200

# Terminal statuses that close an opened feature/task. Anything else
# (STARTED, PROGRESS, BLOCKED, RESOLVED, or an unknown verb) leaves the
# feature open from this hook's perspective.
TERMINAL_STATUSES = frozenset({"PASSED", "FAILED", "SKIPPED"})


def _progress_path() -> Path:
    override = os.environ.get("PLATXA_CODE_AGENT_PROGRESS_FILE_PATH", "")
    raw = override.strip() or DEFAULT_PROGRESS_PATH
    return Path(raw)


def _override_active() -> bool:
    return os.environ.get("PLATXA_MEMORY_PRECOMPACT_OVERRIDE", "").strip() == "1"


def _tail(path: Path, limit: int) -> list[str]:
    """Return the last ``limit`` non-empty lines from ``path`` (newest last)."""
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            lines = [line.rstrip("\n") for line in fh if line.strip()]
    except OSError:
        return []
    return lines[-limit:]


def _parse_record(line: str) -> tuple[str, str] | None:
    """Parse a progress-log line into (feature_id, status) or return None.

    Shape: ``[ts] [session=sid] [agent=name] [feature=#ID] STATUS message``.
    We only care about the feature id and the STATUS token.
    """
    # Locate "[feature=#" marker; bail fast on malformed lines.
    key = "[feature=#"
    start = line.find(key)
    if start < 0:
        return None
    start += len(key)
    end = line.find("]", start)
    if end < 0:
        return None
    feature_id = line[start:end].strip()
    # After "] " we expect STATUS as the next whitespace-delimited token.
    remainder = line[end + 1 :].lstrip()
    if not remainder:
        return None
    status = remainder.split(None, 1)[0]
    return feature_id, status


def pending_features(lines: list[str]) -> list[str]:
    """Return feature IDs whose most recent record is NOT a terminal status.

    A feature is "pending" if its LAST log entry is anything other than
    PASSED, FAILED, or SKIPPED (i.e. STARTED, PROGRESS, BLOCKED, RESOLVED,
    or an unknown verb). We walk newest-to-oldest and track the first
    status we see per feature id.
    """
    seen: dict[str, str] = {}
    for line in reversed(lines):
        rec = _parse_record(line)
        if rec is None:
            continue
        fid, status = rec
        if fid == "-":
            # Ignore session-level or tool-level entries without a feature id.
            continue
        if fid in seen:
            continue
        seen[fid] = status

    return sorted(fid for fid, status in seen.items() if status not in TERMINAL_STATUSES)


def _emit(decision: str, message: str) -> None:
    """Write the PreCompact JSON envelope to stdout. No side effects."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreCompact",
            "decision": decision,
            "reason": message,
        }
    }
    sys.stdout.write(json.dumps(payload))
    sys.stdout.write("\n")


def main() -> int:
    # Consume stdin — the PreCompact payload fields are not needed here.
    try:
        sys.stdin.read()
    except OSError:
        pass

    try:
        lines = _tail(_progress_path(), TAIL_LIMIT)
        pending = pending_features(lines)
    except Exception as exc:
        # A hook MUST NOT crash the session. On failure, allow compact.
        sys.stderr.write(f"[platxa-memory pre_compact_hook] {type(exc).__name__}: {exc}\n")
        _emit("approve", "[platxa-memory] hook error; compaction allowed")
        return 0

    if not pending:
        _emit("approve", "[platxa-memory] no unsaved insights detected")
        return 0

    if _override_active():
        sys.stderr.write("[platxa-memory pre_compact_hook] override active; allowing compact\n")
        _emit(
            "approve",
            f"[platxa-memory] override active; {len(pending)} pending feature(s) acknowledged",
        )
        return 0

    # Block: exit 2 is the Claude Code convention for a hook-enforced halt.
    ids = ", ".join(f"#{fid}" for fid in pending)
    msg = (
        f"[platxa-memory] {len(pending)} feature(s) with unsaved insights: {ids}. "
        "Complete them, or set PLATXA_MEMORY_PRECOMPACT_OVERRIDE=1 to compact anyway."
    )
    sys.stderr.write(msg + "\n")
    _emit("block", msg)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
