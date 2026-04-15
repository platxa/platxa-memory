"""E2E: install → init → status happy path on a scratch project.

Spec verification criterion for feature #50:
    "E2E suite runs in CI on scratch repo; exercises install -> init -> status
     happy path"

We cannot run Claude Code's actual ``/plugin install`` or ``/memory-init``
from inside pytest — those are harness features. Instead we simulate
what each step does on disk (the observable side of the contract) and
verify the user-visible CLI + hook surface reacts correctly.

Flow:
1. **Install**: the plugin manifest parses, every hook script is
   executable and runs cleanly when invoked the way Claude Code would.
2. **Init**: copying the Python stack template's ``.claude/rules/``
   bundle plus the ``CLAUDE.md`` skeleton into the scratch project
   reproduces what ``/memory-init`` outputs — the files land where the
   plugin expects them.
3. **Status**: the CLI ``detect-stack`` and ``health`` subcommands
   report the correct stack and transition from ``uninitialized`` to
   ``ok`` after ``MEMORY.md`` is written.

Every interaction uses ``subprocess`` so the shebang, argparse wiring,
stdin envelope parsing, and exit codes are exercised together.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _run_cli(
    cli_path: Path,
    *args: str,
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ}
    env.pop("CLAUDE_PROJECT_DIR", None)
    env.pop("PLATXA_MEMORY_AUTO_DIR", None)
    env.pop("PLATXA_MEMORY_STOP_SYNTH_DISABLE", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(cli_path), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def _run_hook(
    hook_path: Path,
    payload: dict,
    *,
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ}
    env.pop("PLATXA_MEMORY_STOP_SYNTH_DISABLE", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(hook_path)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


# --- stage 1: install (manifest + hooks) ----------------------------------


def test_plugin_manifest_is_installable(repo_root: Path) -> None:
    manifest = repo_root / ".claude-plugin" / "plugin.json"
    data = json.loads(manifest.read_text())
    assert data["name"] == "platxa-memory"
    # Every hook command must resolve relative to CLAUDE_PLUGIN_ROOT — the
    # envelope Claude Code hands to `/plugin install`.
    prefix = "${CLAUDE_PLUGIN_ROOT}/"
    for event, groups in data.get("hooks", {}).items():
        for group in groups:
            for handler in group.get("hooks", []):
                cmd = handler["command"]
                assert cmd.startswith(prefix), f"{event}: {cmd!r}"
                target = repo_root / cmd[len(prefix) :]
                assert target.is_file(), f"{event}: {target} missing"


def test_all_hook_scripts_are_python_executable(hooks_dir: Path) -> None:
    for hook in hooks_dir.glob("*.py"):
        first = hook.read_text(encoding="utf-8").splitlines()[0]
        assert first.startswith("#!"), f"{hook.name} missing shebang"
        assert "python" in first, f"{hook.name} shebang must name python"


# --- stage 2: init (template copy-in) --------------------------------------


def test_memory_init_simulation_python(scratch_project: Path, templates_dir: Path) -> None:
    """Simulate what ``/memory-init`` writes for a Python project."""
    # 1. Stack profile: copy templates/python/.claude/rules/ -> scratch/.claude/rules/
    src_rules = templates_dir / "python" / ".claude" / "rules"
    dest_rules = scratch_project / ".claude" / "rules"
    shutil.copytree(src_rules, dest_rules)

    # 2. CLAUDE.md skeleton
    shutil.copy(templates_dir / "CLAUDE.md", scratch_project / "CLAUDE.md")

    # 3. Agent-memory seed
    agent_mem = scratch_project / ".claude" / "agent-memory"
    agent_mem.mkdir()
    (agent_mem / "MEMORY.md").write_text("# Agent memory index\n")

    # 4. CLAUDE.local.md + .gitignore entry
    (scratch_project / "CLAUDE.local.md").write_text("")
    (scratch_project / ".gitignore").write_text("CLAUDE.local.md\n.claude/\n")

    # Verify the layout is what downstream hooks expect to see.
    assert (scratch_project / "CLAUDE.md").is_file()
    assert (scratch_project / "CLAUDE.local.md").is_file()
    assert (dest_rules / "python-style.md").is_file()
    assert (dest_rules / "python-testing.md").is_file()
    assert (agent_mem / "MEMORY.md").is_file()
    assert "CLAUDE.local.md" in (scratch_project / ".gitignore").read_text()


# --- stage 3: status (CLI + hook visibility) -------------------------------


def test_detect_stack_sees_scratch_project(cli_path: Path, scratch_project: Path) -> None:
    result = _run_cli(cli_path, "detect-stack", "--project", str(scratch_project))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "python"


def test_health_reports_uninitialized_then_ok(
    cli_path: Path, scratch_project: Path, auto_memory_dir: Path
) -> None:
    # Before MEMORY.md exists, health must report uninitialized (exit 1).
    before = _run_cli(
        cli_path,
        "health",
        "--project",
        str(scratch_project),
        "--auto-dir",
        str(auto_memory_dir),
        "--format",
        "json",
    )
    assert before.returncode == 1, before.stdout
    assert json.loads(before.stdout)["status"] == "uninitialized"

    # Seed the auto-memory index and re-check.
    (auto_memory_dir / "MEMORY.md").write_text("# Memory index\n")
    (auto_memory_dir / "feedback_x.md").write_text("a rule\n")
    after = _run_cli(
        cli_path,
        "health",
        "--project",
        str(scratch_project),
        "--auto-dir",
        str(auto_memory_dir),
        "--format",
        "json",
    )
    assert after.returncode == 0, after.stdout
    payload = json.loads(after.stdout)
    assert payload["status"] == "ok"
    assert payload["memory_md_present"] is True
    assert payload["topic_files"] == 1


def test_session_start_hook_injects_memory(
    hooks_dir: Path, scratch_project: Path, auto_memory_dir: Path
) -> None:
    """Hook runs as Claude Code would — via subprocess — and returns valid envelope."""
    (auto_memory_dir / "MEMORY.md").write_text("# Project memory\n- [x](x.md)\n")
    (auto_memory_dir / "topic_retry.md").write_text("retry-logic notes\n")

    result = _run_hook(
        hooks_dir / "session_start_hook.py",
        payload={"session_id": "sess-e2e"},
        env_extra={
            "CLAUDE_PROJECT_DIR": str(scratch_project),
            "PLATXA_MEMORY_AUTO_DIR": str(auto_memory_dir),
        },
    )
    assert result.returncode == 0, result.stderr
    envelope = json.loads(result.stdout)
    out = envelope["hookSpecificOutput"]
    assert out["hookEventName"] == "SessionStart"
    ctx = out["additionalContext"]
    assert "[platxa-memory]" in ctx
    assert "Project memory" in ctx  # MEMORY.md body made it in
    assert "topic_retry.md" in ctx  # topic file listed
    assert "stack=python" in ctx


def test_search_finds_seeded_memory(
    cli_path: Path, scratch_project: Path, auto_memory_dir: Path, templates_dir: Path
) -> None:
    # Init the scratch project with the Python rules, then seed a searchable token.
    shutil.copytree(
        templates_dir / "python" / ".claude" / "rules",
        scratch_project / ".claude" / "rules",
    )
    (auto_memory_dir / "feedback_testing.md").write_text(
        "marker: integration tests must hit a real database\n"
    )
    result = _run_cli(
        cli_path,
        "search",
        "integration",
        "--project",
        str(scratch_project),
        "--auto-dir",
        str(auto_memory_dir),
        "--scope",
        "all",
        "--format",
        "json",
    )
    # Exit 0 when at least one hit, even across stdlib fallback path.
    assert result.returncode == 0, (result.stdout, result.stderr)
    payload = json.loads(result.stdout)
    assert payload["count"] >= 1
    assert any("integration" in hit.lower() for hit in payload["hits"])


# --- stage 4: stop-hook loop prevention end-to-end -------------------------


def test_stop_hook_blocks_then_approves(hooks_dir: Path, scratch_project: Path) -> None:
    """Stop hook must emit one block and then approve for the same session."""
    first = _run_hook(
        hooks_dir / "stop_hook.py",
        payload={"session_id": "sid-e2e-1"},
        env_extra={"CLAUDE_PROJECT_DIR": str(scratch_project)},
    )
    assert first.returncode == 0, first.stderr
    assert json.loads(first.stdout)["decision"] == "block"

    second = _run_hook(
        hooks_dir / "stop_hook.py",
        payload={"session_id": "sid-e2e-1"},
        env_extra={"CLAUDE_PROJECT_DIR": str(scratch_project)},
    )
    assert second.returncode == 0
    # After the first block, a marker exists → second call approves.
    second_envelope = json.loads(second.stdout)
    assert "hookSpecificOutput" in second_envelope
    assert second_envelope["hookSpecificOutput"]["hookEventName"] == "Stop"


# --- stage 5: full round-trip sanity --------------------------------------


def test_full_happy_path_round_trip(
    cli_path: Path,
    templates_dir: Path,
    scratch_project: Path,
    auto_memory_dir: Path,
) -> None:
    """Ties the stages together: init, export, re-import, health stays OK."""
    # Init
    shutil.copytree(
        templates_dir / "python" / ".claude" / "rules",
        scratch_project / ".claude" / "rules",
    )
    (auto_memory_dir / "MEMORY.md").write_text("# Memory index\n- [x](x.md)\n")
    (auto_memory_dir / "x.md").write_text("body\n")

    # Export
    archive = scratch_project / "backup.tar.gz"
    exp = _run_cli(cli_path, "export", str(archive), "--auto-dir", str(auto_memory_dir))
    assert exp.returncode == 0, exp.stderr
    assert archive.is_file()

    # Restore into a fresh auto-dir, then verify health reports ok.
    fresh = scratch_project.parent / "restored-memory"
    fresh.mkdir()
    res = _run_cli(cli_path, "restore", str(archive), "--auto-dir", str(fresh))
    assert res.returncode == 0, res.stderr

    health = _run_cli(
        cli_path,
        "health",
        "--project",
        str(scratch_project),
        "--auto-dir",
        str(fresh),
        "--format",
        "json",
    )
    assert health.returncode == 0
    payload = json.loads(health.stdout)
    assert payload["status"] == "ok"
    assert payload["topic_files"] == 1
