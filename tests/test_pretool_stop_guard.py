"""Unit tests for ``hooks/pretool_stop_guard.py``.

Verifies that the guard observes memory-synthesizer dispatches and writes the
per-session marker, ignores all other tool calls, and never denies execution.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pretool_stop_guard  # type: ignore[import-not-found]
import pytest


@pytest.fixture()
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / ".claude").mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    return tmp_path


def test_is_synthesizer_dispatch_true() -> None:
    assert pretool_stop_guard.is_synthesizer_dispatch(
        {"tool_name": "Task", "tool_input": {"subagent_type": "memory-synthesizer"}}
    )


def test_is_synthesizer_dispatch_other_agent() -> None:
    assert not pretool_stop_guard.is_synthesizer_dispatch(
        {"tool_name": "Task", "tool_input": {"subagent_type": "memory-curator"}}
    )


def test_is_synthesizer_dispatch_other_tool() -> None:
    assert not pretool_stop_guard.is_synthesizer_dispatch(
        {"tool_name": "Read", "tool_input": {"subagent_type": "memory-synthesizer"}}
    )


def test_is_synthesizer_dispatch_missing_tool_input() -> None:
    assert not pretool_stop_guard.is_synthesizer_dispatch({"tool_name": "Task"})


def test_is_synthesizer_dispatch_malformed_tool_input() -> None:
    assert not pretool_stop_guard.is_synthesizer_dispatch(
        {"tool_name": "Task", "tool_input": "not-a-dict"}
    )


def test_marker_path_sanitizes_session_id(project: Path) -> None:
    p = pretool_stop_guard._marker_path(project, "../../etc/passwd")
    assert ".." not in p.name
    assert "/" not in p.name
    assert p.name.startswith(".memory-synthesized-")


def _run_subprocess(payload: dict, project: Path) -> subprocess.CompletedProcess[str]:
    hook_path = Path(__file__).resolve().parent.parent / "hooks" / "pretool_stop_guard.py"
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project)}
    return subprocess.run(
        [sys.executable, str(hook_path)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )


def test_subprocess_writes_marker_for_synthesizer_dispatch(tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    payload = {
        "session_id": "sid-a",
        "tool_name": "Task",
        "tool_input": {"subagent_type": "memory-synthesizer"},
    }
    result = _run_subprocess(payload, tmp_path)
    assert result.returncode == 0
    out = json.loads(result.stdout.strip())
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert (tmp_path / ".claude" / ".memory-synthesized-sid-a").is_file()


def test_subprocess_no_marker_for_other_tools(tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    payload = {"session_id": "sid-b", "tool_name": "Read", "tool_input": {"file_path": "x"}}
    result = _run_subprocess(payload, tmp_path)
    assert result.returncode == 0
    out = json.loads(result.stdout.strip())
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert not any((tmp_path / ".claude").glob(".memory-synthesized-*"))


def test_subprocess_always_allows_even_on_malformed_input(tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    hook_path = Path(__file__).resolve().parent.parent / "hooks" / "pretool_stop_guard.py"
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input="{{not json",
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert result.returncode == 0
    out = json.loads(result.stdout.strip())
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
