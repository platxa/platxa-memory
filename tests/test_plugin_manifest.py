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


def _script_path_from_command(command: str) -> str:
    """Extract the `${CLAUDE_PLUGIN_ROOT}/<relative>` target out of a command.

    Commands may be bare (``${CLAUDE_PLUGIN_ROOT}/hooks/foo.py``) or may be
    prefixed by an ``env KEY=VAL ...`` block used to thread user-config
    values into the hook's environment (feature #4). Parse either shape.
    """
    marker = "${CLAUDE_PLUGIN_ROOT}/"
    idx = command.find(marker)
    if idx < 0:
        raise AssertionError(f"command does not reference CLAUDE_PLUGIN_ROOT: {command!r}")
    tail = command[idx + len(marker) :]
    # The script path is the first whitespace-delimited token after the marker.
    return tail.split()[0]


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
                relative = _script_path_from_command(command)
                target = REPO / relative
                assert target.is_file(), f"{event_name}: command references missing file {target}"


def test_hook_commands_match_expected_files() -> None:
    hooks = _load_manifest().get("hooks", {})
    for event, expected_path in EXPECTED_HOOK_EVENTS.items():
        commands = []
        for group in hooks.get(event, []):
            for handler in group.get("hooks", []):
                cmd = handler.get("command", "")
                commands.append(_script_path_from_command(cmd))
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


# --- userConfig schema (feature #4) ---------------------------------------


def test_user_config_declares_required_fields() -> None:
    user_config = _load_manifest().get("userConfig", {})
    # Three fields per the feature spec: observation_capture (bool),
    # memory_token_budget (int, default 25 000), telemetry_endpoint
    # (optional URL, sensitive: false).
    assert set(user_config.keys()) >= {
        "observation_capture",
        "memory_token_budget",
        "telemetry_endpoint",
    }, f"userConfig missing required fields: {list(user_config.keys())}"


def test_user_config_observation_capture_is_boolean() -> None:
    field = _load_manifest()["userConfig"]["observation_capture"]
    assert field["type"] == "boolean"
    assert field.get("default") is False, (
        "observation_capture must default off so installing the plugin is "
        "invisible until the user opts in"
    )


def test_user_config_memory_token_budget_is_int_with_safe_defaults() -> None:
    field = _load_manifest()["userConfig"]["memory_token_budget"]
    assert field["type"] == "integer"
    assert field["default"] == 25000, "default must match the hook's documented default budget"
    # The hooks clamp regardless, but the declared bounds should match.
    assert field.get("minimum") == 500
    assert field.get("maximum") == 200000


def test_user_config_telemetry_endpoint_is_optional_url() -> None:
    field = _load_manifest()["userConfig"]["telemetry_endpoint"]
    assert field["type"] == "string"
    assert field.get("format") == "uri"
    # Per spec: optional, non-sensitive (the endpoint URL itself is not
    # a secret — what you send to it is, but the plugin doesn't send
    # anything until opted in).
    assert field.get("optional") is True
    assert field.get("sensitive") is False


def test_hooks_thread_memory_token_budget_from_user_config() -> None:
    """The two budget-aware hooks must receive ``user_config.memory_token_budget``
    as ``PLATXA_MEMORY_TOKEN_BUDGET`` via the ``env KEY=VAL`` command prefix.
    """
    hooks = _load_manifest()["hooks"]
    for event in ("SessionStart", "PostCompact"):
        commands = [h["command"] for group in hooks.get(event, []) for h in group.get("hooks", [])]
        assert commands, f"{event} has no hook commands"
        assert any(
            'PLATXA_MEMORY_TOKEN_BUDGET="${user_config.memory_token_budget}"' in cmd
            for cmd in commands
        ), (
            f"{event} must thread user_config.memory_token_budget into "
            f"PLATXA_MEMORY_TOKEN_BUDGET via the env prefix; got {commands}"
        )


def test_session_start_threads_all_opt_in_user_config() -> None:
    """SessionStart is the entry point that needs every opt-in flag visible,
    so all three userConfig fields must be threaded into its env.
    """
    hooks = _load_manifest()["hooks"]
    commands = [
        h["command"] for group in hooks.get("SessionStart", []) for h in group.get("hooks", [])
    ]
    joined = "\n".join(commands)
    for mapping in (
        'PLATXA_MEMORY_TOKEN_BUDGET="${user_config.memory_token_budget}"',
        'PLATXA_MEMORY_OBSERVATION_CAPTURE="${user_config.observation_capture}"',
        'PLATXA_MEMORY_TELEMETRY_ENDPOINT="${user_config.telemetry_endpoint}"',
    ):
        assert mapping in joined, f"SessionStart command missing user-config threading: {mapping!r}"


def test_user_config_substitutions_are_shell_quoted() -> None:
    """Every ``${user_config.X}`` substitution inside a hook command must sit
    inside double quotes. User-configured values include a URL
    (``telemetry_endpoint``) that may legitimately contain ``&``, ``;``, or
    whitespace — characters the shell would otherwise interpret. Unquoted
    substitution is a command-injection vector once the user opts in, so
    pin the quoting on the JSON-decoded command string (the actual shell
    command Claude Code will execute), not on the escaped JSON source.
    """
    import re

    manifest = _load_manifest()
    offenders: list[str] = []
    for event, groups in manifest.get("hooks", {}).items():
        for group in groups:
            for handler in group.get("hooks", []):
                cmd = handler.get("command", "")
                for match in re.finditer(r"(.?)\$\{user_config\.[A-Za-z0-9_]+\}(.?)", cmd):
                    before, after = match.group(1), match.group(2)
                    if before == '"' and after == '"':
                        continue
                    offenders.append(f"{event}: {match.group(0)!r}")
    assert not offenders, (
        'user_config substitutions must be shell-quoted ("${user_config.X}") '
        "to avoid injection via URLs containing & ; or whitespace; "
        f"unquoted: {offenders}"
    )


def test_every_declared_user_config_field_is_threaded_somewhere() -> None:
    """Reverse drift guard: every declared userConfig field must be referenced
    at least once inside a hook command, so a declaration without a consumer
    fails CI rather than quietly going dead.
    """
    import re

    manifest = _load_manifest()
    declared = set(manifest.get("userConfig", {}).keys())
    manifest_text = MANIFEST.read_text(encoding="utf-8")
    referenced = set(re.findall(r"\$\{user_config\.([A-Za-z0-9_]+)\}", manifest_text))
    unused = declared - referenced
    assert not unused, f"userConfig fields declared but never referenced in a hook: {unused}"


def test_every_user_config_reference_names_a_declared_field() -> None:
    """Guard against typos: ``${user_config.foo}`` must refer to a field
    that actually exists in the userConfig declaration.
    """
    import re

    manifest = _load_manifest()
    declared = set(manifest.get("userConfig", {}).keys())
    manifest_text = MANIFEST.read_text(encoding="utf-8")
    referenced = set(re.findall(r"\$\{user_config\.([A-Za-z0-9_]+)\}", manifest_text))
    unknown = referenced - declared
    assert not unknown, f"plugin.json references undeclared userConfig fields: {unknown}"
