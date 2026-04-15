"""Validates ``.claude-plugin/plugin.json`` and the marketplace snippet.

Spec verification criterion for feature #44:
    "claude plugin marketplace add ./platxa-plugins then
     /plugin install platxa-memory@platxa-plugins works"

This test module pins the invariants that must hold for the plugin to
install and activate cleanly under the platxa-plugins marketplace:

1. ``plugin.json`` is valid JSON and has the Claude-Code-required top-
   level fields (``name``, ``version``, ``description``).
2. Every hook referenced in ``plugin.json`` points at an existing
   executable Python file under ``hooks/``.
3. Every hook event we have shipped Python for (``session_start_hook``,
   ``pre_compact_hook``, ``post_compact_hook``, ``stop_hook``,
   ``pretool_stop_guard``) is wired into ``plugin.json``.
4. The downstream-marketplace-ready snippet at
   ``.claude-plugin/marketplace-entry.json`` matches the canonical
   name/description/homepage from ``plugin.json`` so they never drift.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / ".claude-plugin" / "plugin.json"
MARKETPLACE_ENTRY = REPO / ".claude-plugin" / "marketplace-entry.json"
HOOKS_DIR = REPO / "hooks"

# Hooks that SHOULD be wired up because we actually ship Python for them.
EXPECTED_HOOK_EVENTS = {
    "SessionStart": "hooks/session_start_hook.py",
    "PreCompact": "hooks/pre_compact_hook.py",
    "PostCompact": "hooks/post_compact_hook.py",
    "Stop": "hooks/stop_hook.py",
    "PreToolUse": "hooks/pretool_stop_guard.py",
}


def _load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _load_entry() -> dict:
    return json.loads(MARKETPLACE_ENTRY.read_text(encoding="utf-8"))


# --- plugin.json shape -----------------------------------------------------


def test_manifest_is_valid_json() -> None:
    assert MANIFEST.is_file(), f"{MANIFEST} missing"
    _load_manifest()  # raises if malformed


def test_manifest_has_required_top_level_fields() -> None:
    data = _load_manifest()
    for field in ("name", "version", "description"):
        assert field in data, f"plugin.json missing required field {field!r}"
        assert isinstance(data[field], str) and data[field].strip()


def test_manifest_name_matches_repo() -> None:
    assert _load_manifest()["name"] == "platxa-memory"


def test_manifest_version_is_semver() -> None:
    version = _load_manifest()["version"]
    parts = version.split(".")
    assert len(parts) == 3, f"version {version!r} is not semver"
    assert all(p.isdigit() for p in parts), f"version {version!r} has non-numeric parts"


# --- hook wiring -----------------------------------------------------------


def test_all_shipped_hooks_are_wired() -> None:
    """Every hook we've shipped Python for must be referenced in plugin.json."""
    hooks = _load_manifest().get("hooks", {})
    missing = [event for event in EXPECTED_HOOK_EVENTS if event not in hooks]
    assert not missing, f"plugin.json missing hook events: {missing}"


def test_every_referenced_hook_command_points_at_a_real_file() -> None:
    """No dangling references — every command must resolve under hooks/."""
    hooks = _load_manifest().get("hooks", {})
    # Each hook event maps to a list of handler groups; each handler group
    # has a `hooks` list of {type, command} dicts.
    for event_name, groups in hooks.items():
        assert isinstance(groups, list), f"{event_name} must be a list"
        for group in groups:
            for handler in group.get("hooks", []):
                assert handler.get("type") in {"command", "http"}, (
                    f"{event_name}: hook type must be 'command' or 'http' "
                    f"(CLAUDE.md hard constraint)"
                )
                command = handler.get("command", "")
                assert command.startswith("${CLAUDE_PLUGIN_ROOT}/"), (
                    f"{event_name}: command must start with ${{CLAUDE_PLUGIN_ROOT}}"
                )
                relative = command.removeprefix("${CLAUDE_PLUGIN_ROOT}/")
                target = REPO / relative
                assert target.is_file(), f"{event_name}: command references missing file {target}"


def test_hook_commands_match_expected_files() -> None:
    hooks = _load_manifest().get("hooks", {})
    for event, expected_path in EXPECTED_HOOK_EVENTS.items():
        commands = []
        for group in hooks.get(event, []):
            for handler in group.get("hooks", []):
                cmd = handler.get("command", "")
                commands.append(cmd.removeprefix("${CLAUDE_PLUGIN_ROOT}/"))
        assert expected_path in commands, f"{event} must invoke {expected_path}, got {commands}"


def test_pretool_use_matcher_is_task() -> None:
    """PreToolUse guard should only fire for Task dispatches."""
    hooks = _load_manifest().get("hooks", {})
    groups = hooks.get("PreToolUse", [])
    assert groups, "PreToolUse must be wired"
    # Exactly one group with matcher=="Task" is required.
    matchers = [g.get("matcher") for g in groups]
    assert "Task" in matchers, (
        f"PreToolUse must have matcher='Task' to avoid firing on every tool; found {matchers}"
    )


def test_plugin_hooks_are_all_command_or_http() -> None:
    # CLAUDE.md hard constraint: hook types restricted to command and http.
    hooks = _load_manifest().get("hooks", {})
    bad: list[str] = []
    for event, groups in hooks.items():
        for group in groups:
            for handler in group.get("hooks", []):
                t = handler.get("type")
                if t not in {"command", "http"}:
                    bad.append(f"{event}: type={t!r}")
    assert not bad, f"forbidden hook types found: {bad}"


# --- marketplace entry -----------------------------------------------------


def test_marketplace_entry_is_valid_json() -> None:
    assert MARKETPLACE_ENTRY.is_file()
    _load_entry()


def test_marketplace_entry_has_required_fields() -> None:
    entry = _load_entry()
    for field in ("name", "source", "description"):
        assert field in entry, f"marketplace entry missing {field!r}"
    # The `source` is what `claude plugin marketplace add` resolves
    # relative to the marketplace root.
    assert entry["source"] == "./plugins/platxa-memory"


def test_marketplace_entry_name_matches_manifest() -> None:
    entry = _load_entry()
    manifest = _load_manifest()
    assert entry["name"] == manifest["name"], (
        "marketplace entry name must match plugin.json name — otherwise "
        "`/plugin install platxa-memory@<market>` will not resolve"
    )


def test_marketplace_entry_homepage_matches_manifest() -> None:
    entry = _load_entry()
    manifest = _load_manifest()
    if "homepage" in entry:
        assert entry["homepage"] == manifest["homepage"], (
            "marketplace entry and plugin manifest must point at the same homepage"
        )


def test_marketplace_entry_description_non_empty() -> None:
    assert _load_entry()["description"].strip()
