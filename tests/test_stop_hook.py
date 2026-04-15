"""Unit tests for ``hooks/stop_hook.py``.

Covers the three loop-prevention layers (``stop_hook_active``, per-session
marker, env-var opt-out), the block-then-approve sequence across two Stop
events for the same session, graceful degradation on malformed stdin, and
subprocess end-to-end exit behaviour.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import stop_hook  # type: ignore[import-not-found]


@pytest.fixture()
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated project dir with .claude/ subdir and no env leakage."""
    (tmp_path / ".claude").mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.delenv("PLATXA_MEMORY_STOP_SYNTH_DISABLE", raising=False)
    monkeypatch.delenv("PLATXA_CODE_AGENT_PROGRESS_FILE_PATH", raising=False)
    return tmp_path


def test_blocks_on_first_stop_and_writes_marker(project: Path) -> None:
    payload = {"session_id": "sess-abc", "stop_hook_active": False}
    action, message = stop_hook.decide(payload, project)
    assert action == "block"
    assert "memory-synthesizer" in message
    assert (project / ".claude" / ".memory-synthesized-sess-abc").is_file()


def test_approves_when_marker_exists(project: Path) -> None:
    marker = project / ".claude" / ".memory-synthesized-sess-abc"
    marker.write_text("1")
    action, message = stop_hook.decide({"session_id": "sess-abc"}, project)
    assert action == "approve"
    assert "already ran" in message


def test_approves_when_stop_hook_active(project: Path) -> None:
    action, message = stop_hook.decide(
        {"session_id": "sess-abc", "stop_hook_active": True}, project
    )
    assert action == "approve"
    assert "loop" in message
    assert not (project / ".claude" / ".memory-synthesized-sess-abc").exists()


def test_disabled_via_env(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLATXA_MEMORY_STOP_SYNTH_DISABLE", "1")
    action, _ = stop_hook.decide({"session_id": "sess-abc"}, project)
    assert action == "approve"
    assert not (project / ".claude" / ".memory-synthesized-sess-abc").exists()


def test_second_stop_in_same_session_is_approve(project: Path) -> None:
    payload = {"session_id": "sess-xyz"}
    first_action, _ = stop_hook.decide(payload, project)
    second_action, _ = stop_hook.decide(payload, project)
    assert first_action == "block"
    assert second_action == "approve"


def test_digest_uses_progress_log_tail(project: Path) -> None:
    log = project / ".claude" / "claude-progress.txt"
    log.write_text("line-1\nline-2\nline-3\n")
    action, message = stop_hook.decide({"session_id": "sid"}, project)
    assert action == "block"
    assert "line-3" in message


def test_digest_handles_missing_progress_log(project: Path) -> None:
    action, message = stop_hook.decide({"session_id": "sid"}, project)
    assert action == "block"
    assert "progress log empty" in message


def test_session_id_sanitized(project: Path) -> None:
    payload = {"session_id": "sess/../../evil"}
    action, _ = stop_hook.decide(payload, project)
    assert action == "block"
    markers = list((project / ".claude").glob(".memory-synthesized-*"))
    assert len(markers) == 1
    assert ".." not in markers[0].name
    assert "/" not in markers[0].name


def test_malformed_payload_does_not_crash(project: Path) -> None:
    action, _ = stop_hook.decide({}, project)
    assert action in {"approve", "block"}


def _run_subprocess(payload: dict, project: Path) -> subprocess.CompletedProcess[str]:
    hook_path = Path(__file__).resolve().parent.parent / "hooks" / "stop_hook.py"
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project)}
    env.pop("PLATXA_MEMORY_STOP_SYNTH_DISABLE", None)
    return subprocess.run(
        [sys.executable, str(hook_path)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )


def test_subprocess_emits_block_json_and_exit_zero(tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    result = _run_subprocess({"session_id": "sid-1"}, tmp_path)
    assert result.returncode == 0
    out = json.loads(result.stdout.strip())
    assert out["decision"] == "block"


def test_subprocess_emits_approve_on_second_run(tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    _run_subprocess({"session_id": "sid-2"}, tmp_path)
    second = _run_subprocess({"session_id": "sid-2"}, tmp_path)
    assert second.returncode == 0
    out = json.loads(second.stdout.strip())
    assert out.get("hookSpecificOutput", {}).get("hookEventName") == "Stop"


def test_subprocess_handles_empty_stdin(tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    hook_path = Path(__file__).resolve().parent.parent / "hooks" / "stop_hook.py"
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    env.pop("PLATXA_MEMORY_STOP_SYNTH_DISABLE", None)
    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input="",
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert result.returncode == 0
    # Empty payload → no session id → treated as first stop for "unknown" session.
    out = json.loads(result.stdout.strip())
    assert "decision" in out or "hookSpecificOutput" in out
