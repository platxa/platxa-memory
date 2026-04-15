#!/usr/bin/env python3
"""PreToolUse guard hook for platxa-memory.

Fires before every tool call. Its sole job is to detect proactive dispatches
of the ``memory-synthesizer`` agent (i.e. the main model invoking the agent
mid-session, not through the Stop-hook path) and write the per-session marker
that the Stop hook reads. Without this guard the Stop hook could emit a
``block`` after the agent has already run, re-dispatching it and wasting a
turn on redundant synthesis.

The hook NEVER denies a tool call — it only observes. All execution paths
emit an ``allow`` permission decision and exit 0.

Hard constraint (see CLAUDE.md): stdlib only — no SDK, no API, no LLM.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

MARKER_DIR = ".claude"
MARKER_PREFIX = ".memory-synthesized-"
TARGET_AGENT = "memory-synthesizer"


def _project_dir() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())


def _marker_path(project: Path, session_id: str) -> Path:
    safe_sid = "".join(c for c in session_id if c.isalnum() or c in "-_") or "unknown"
    return project / MARKER_DIR / f"{MARKER_PREFIX}{safe_sid}"


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


def is_synthesizer_dispatch(payload: dict) -> bool:
    """True when the payload describes a Task dispatch to memory-synthesizer.

    Pure predicate — isolated for unit testing.
    """
    if payload.get("tool_name") != "Task":
        return False
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return False
    subagent = tool_input.get("subagent_type")
    return isinstance(subagent, str) and subagent.strip() == TARGET_AGENT


def _write_marker(marker: Path) -> bool:
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("1", encoding="utf-8")
        return True
    except OSError:
        return False


def _emit_allow(reason: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": reason,
        }
    }
    sys.stdout.write(json.dumps(payload))
    sys.stdout.write("\n")


def main() -> int:
    try:
        payload = _read_payload()
        if is_synthesizer_dispatch(payload):
            session_id = str(payload.get("session_id") or "unknown")
            marker = _marker_path(_project_dir(), session_id)
            ok = _write_marker(marker)
            reason = (
                f"[platxa-memory] marked session {session_id} as synthesized"
                if ok
                else "[platxa-memory] marker write failed; Stop hook may re-dispatch"
            )
            _emit_allow(reason)
            return 0
    except Exception as exc:
        sys.stderr.write(f"[platxa-memory pretool_stop_guard] {type(exc).__name__}: {exc}\n")
        # Fall through to default allow.

    _emit_allow("[platxa-memory] no action")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
