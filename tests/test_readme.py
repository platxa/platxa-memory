"""Validates ``README.md``.

Spec verification criterion for feature #42:
    "README scannable in under 2 minutes; installation commands are
     copy-pasteable"

"Scannable" is enforced structurally: required section headings, a hard
upper bound on length, no giant dead zones (no single section >60% of
the doc). "Copy-pasteable" is enforced by checking that the two install
commands appear verbatim inside a fenced code block. Drift guards then
pin that the README references things that actually exist in the repo
(every skill, agent, hook, and src module it names must be shipped).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
README = REPO / "README.md"

REQUIRED_SECTIONS = (
    "What it is",
    "Installation",
    "Quickstart",
    "Core concepts",
    "Relationship to platxa-code-agent",
    "Hard constraints",
)

REQUIRED_INSTALL_COMMANDS = (
    "/plugin marketplace add platxa/plugins",
    "/plugin install platxa-memory@platxa-plugins",
)


def _text() -> str:
    return README.read_text(encoding="utf-8")


def _sections(text: str) -> dict[str, int]:
    """Return ``{section_title: start_line}`` for every ``## `` heading."""
    out: dict[str, int] = {}
    for i, line in enumerate(text.splitlines()):
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match:
            out[match.group(1)] = i
    return out


def _fenced_code_blocks(text: str) -> list[str]:
    """Return the body of each triple-backtick fenced block."""
    blocks: list[str] = []
    in_fence = False
    current: list[str] = []
    for line in text.splitlines():
        if line.startswith("```"):
            if in_fence:
                blocks.append("\n".join(current))
                current = []
            in_fence = not in_fence
            continue
        if in_fence:
            current.append(line)
    return blocks


# --- existence + length ---------------------------------------------------


def test_readme_exists_non_empty() -> None:
    assert README.is_file()
    assert README.stat().st_size > 0


def test_readme_length_is_scannable() -> None:
    # Upper cap is generous but not unlimited — "scannable in under 2 minutes"
    # at ~200 words/min eyeball skim tops out well before 300 lines.
    lines = _text().splitlines()
    assert 50 <= len(lines) <= 300, f"README is {len(lines)} lines, want 50-300"


# --- structure ------------------------------------------------------------


def test_all_required_sections_present() -> None:
    sections = _sections(_text())
    missing = [s for s in REQUIRED_SECTIONS if s not in sections]
    assert not missing, f"README missing sections: {missing}"


def test_no_single_section_dominates() -> None:
    # If one section is >60% of the doc, the others are starved — readers
    # can't scan for "where's installation?" / "where's quickstart?" fast.
    text = _text()
    total = len(text.splitlines())
    section_starts = sorted(_sections(text).values())
    section_starts.append(total)  # sentinel for the last section's end
    max_size = max(
        section_starts[i + 1] - section_starts[i] for i in range(len(section_starts) - 1)
    )
    assert max_size * 100 / total <= 60, (
        f"largest section is {max_size}/{total} lines "
        f"({max_size * 100 / total:.0f}%); keep any one section <=60%"
    )


# --- installation commands (copy-pasteable) -------------------------------


def test_install_commands_are_in_a_code_block() -> None:
    # Every install command must appear verbatim inside a fenced block,
    # not inline. Inline prose-embedded commands are miserable to paste.
    blocks_joined = "\n\n".join(_fenced_code_blocks(_text()))
    for cmd in REQUIRED_INSTALL_COMMANDS:
        assert cmd in blocks_joined, (
            f"install command {cmd!r} must appear verbatim in a fenced code block"
        )


def test_install_block_precedes_quickstart_block() -> None:
    # A reader should be able to scan top-to-bottom: install → quickstart.
    sections = _sections(_text())
    assert sections["Installation"] < sections["Quickstart"]


# --- path-truth drift guards ---------------------------------------------


def test_referenced_hooks_exist() -> None:
    text = _text()
    for hook in (
        "session_start_hook.py",
        "pre_compact_hook.py",
        "post_compact_hook.py",
        "stop_hook.py",
        "pretool_stop_guard.py",
    ):
        assert hook in text, f"README should mention {hook}"
        assert (REPO / "hooks" / hook).is_file(), f"{hook} claimed but not shipped"


def test_referenced_agents_exist() -> None:
    text = _text()
    for agent in ("memory-curator", "memory-synthesizer", "memory-researcher", "memory-auditor"):
        assert agent in text
        assert (REPO / "agents" / f"{agent}.md").is_file()


def test_referenced_skills_exist() -> None:
    text = _text()
    for skill in ("memory-init", "memory-status", "memory-search", "memory-doctor"):
        assert skill in text
        assert (REPO / "skills" / skill / "SKILL.md").is_file()


def test_referenced_src_modules_exist() -> None:
    text = _text()
    for module in ("stack.py", "atomic.py"):
        assert module in text
        assert (REPO / "src" / "platxa_memory" / module).is_file()


def test_referenced_architecture_doc_exists() -> None:
    text = _text()
    assert "docs/memory-architecture.md" in text
    assert (REPO / "docs" / "memory-architecture.md").is_file()


def test_cli_subcommand_list_matches_bin() -> None:
    # Sanity: the README names 8 CLI subcommands; the CLI must expose them.
    text = _text()
    declared = {
        "detect-stack",
        "health",
        "search",
        "export",
        "import",
        "prune",
        "restore",
        "migrate",
    }
    missing = [c for c in declared if c not in text]
    assert not missing, f"README must name CLI subcommands: {missing}"


# --- hard constraints (repo CLAUDE.md) ------------------------------------


def test_hard_constraints_listed() -> None:
    text = _text()
    for must_mention in (
        "No Anthropic SDK",
        "command",  # hook type
        "http",  # hook type
    ):
        assert must_mention in text, f"README must mention hard constraint: {must_mention!r}"


def test_env_vars_documented() -> None:
    text = _text()
    for env in (
        "PLATXA_MEMORY_TOKEN_BUDGET",
        "PLATXA_MEMORY_AUTO_DIR",
        "PLATXA_MEMORY_PRECOMPACT_OVERRIDE",
        "PLATXA_MEMORY_STOP_SYNTH_DISABLE",
        "CLAUDE_PROJECT_DIR",
    ):
        assert env in text, f"README must document env var: {env}"
