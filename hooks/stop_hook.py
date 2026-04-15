#!/usr/bin/env python3
"""Stop hook for platxa-memory.

Fires when Claude Code is about to stop. Builds a short session digest from
the progress-log tail and returns a ``block`` decision instructing Claude to
dispatch the ``memory-synthesizer`` agent exactly once before the session
ends. Loop prevention is layered:

1. Honour ``stop_hook_active`` in the stdin payload — Claude Code sets this
   flag when the Stop hook has already blocked in the current stop-cycle,
   and re-blocking would trap the session.
2. Per-session marker file ``.claude/.memory-synthesized-<session_id>``.
   Written on block emission AND by the PreToolUse guard when the main
   model dispatches memory-synthesizer proactively mid-session. Subsequent
   Stop events for the same session see the marker and approve.
3. Explicit opt-out via ``PLATXA_MEMORY_STOP_SYNTH_DISABLE=1``.
4. Graceful degradation: any exception falls through to approve so the
   session is never trapped.

Hard constraint (see CLAUDE.md): stdlib only — no SDK, no API, no LLM.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DEFAULT_PROGRESS_PATH = ".claude/claude-progress.txt"
MARKER_DIR = ".claude"
MARKER_PREFIX = ".memory-synthesized-"
TAIL_LINES = 20
MAX_DIGEST_CHARS = 4000


def _project_dir() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())


def _progress_path(project: Path) -> Path:
    override = os.environ.get("PLATXA_CODE_AGENT_PROGRESS_FILE_PATH", "").strip()
    return Path(override) if override else project / DEFAULT_PROGRESS_PATH


def _marker_path(project: Path, session_id: str) -> Path:
    safe_sid = "".join(c for c in session_id if c.isalnum() or c in "-_") or "unknown"
    return project / MARKER_DIR / f"{MARKER_PREFIX}{safe_sid}"


def _disabled() -> bool:
    return os.environ.get("PLATXA_MEMORY_STOP_SYNTH_DISABLE", "").strip() == "1"


def _tail(path: Path, limit: int) -> list[str]:
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            lines = [line.rstrip("\n") for line in fh if line.strip()]
    except OSError:
        return []
    return lines[-limit:]


def _build_digest(project: Path) -> str:
    """Assemble a compact digest: progress tail only. The main model fills in
    conversation-level insights from its own context when dispatching the agent.
    """
    tail = _tail(_progress_path(project), TAIL_LINES)
    if not tail:
        return "(progress log empty or missing)"
    digest = "\n".join(tail)
    if len(digest) > MAX_DIGEST_CHARS:
        digest = digest[-MAX_DIGEST_CHARS:]
    return digest


def _write_marker(marker: Path) -> bool:
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("1", encoding="utf-8")
        return True
    except OSError:
        return False


def _emit_approve(reason: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": reason,
        }
    }
    sys.stdout.write(json.dumps(payload))
    sys.stdout.write("\n")


def _emit_block(reason: str) -> None:
    payload = {"decision": "block", "reason": reason}
    sys.stdout.write(json.dumps(payload))
    sys.stdout.write("\n")


def _read_payload() -> dict:
    try:
        raw = sys.stdin.read()
    except OSError:
        return {}
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def decide(payload: dict, project: Path) -> tuple[str, str]:
    """Pure decision function. Returns (action, message).

    action ∈ {"approve", "block"}. Isolated for unit testing.
    """
    if _disabled():
        return "approve", "[platxa-memory] stop synthesis disabled via env"

    if payload.get("stop_hook_active") is True:
        return "approve", "[platxa-memory] stop_hook_active set; skipping to avoid loop"

    session_id = str(payload.get("session_id") or "unknown")
    marker = _marker_path(project, session_id)
    if marker.exists():
        return "approve", f"[platxa-memory] synthesis already ran for session {session_id}"

    # First stop of this session → block and instruct the model to dispatch.
    digest = _build_digest(project)
    if not _write_marker(marker):
        # Cannot persist marker; allow to prevent trapping the session.
        return "approve", "[platxa-memory] marker write failed; skipping synthesis"

    instruction = (
        "[platxa-memory] Before ending the session, dispatch the "
        "memory-synthesizer agent exactly once via the Task tool "
        '(subagent_type="memory-synthesizer"). Pass this session digest as '
        "input so the agent can persist durable insights to MEMORY.md and "
        "topic files.\n\n"
        "=== session digest (progress-log tail) ===\n"
        f"{digest}\n"
        "=== end digest ==="
    )
    return "block", instruction


def main() -> int:
    try:
        payload = _read_payload()
        project = _project_dir()
        action, message = decide(payload, project)
    except Exception as exc:
        sys.stderr.write(f"[platxa-memory stop_hook] {type(exc).__name__}: {exc}\n")
        _emit_approve("[platxa-memory] stop hook failed; allowing stop")
        return 0

    if action == "block":
        _emit_block(message)
        # Exit 0 with JSON decision — Claude Code reads the decision field.
        return 0

    _emit_approve(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
