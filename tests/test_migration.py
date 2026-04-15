"""Unit and integration tests for platxa_memory.migration.

Verification criterion (feature #8):
    Agent idempotently migrates a v1 MEMORY.md to v2 format preserving content.

Coverage:
- detect_format_version: none / v1 / v2 / mixed detection
- migrate_v1_to_v2: content preservation, idempotency, type classification,
  slug collision handling, heading preservation
- CLI integration: platxa-memory migrate --format json on v1 dir
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from platxa_memory.migration import (
    _classify_type,
    _make_slug,
    _make_title,
    _unique_path,
    detect_format_version,
    migrate_v1_to_v2,
)

CLI_PATH = Path(__file__).resolve().parent.parent / "bin" / "platxa-memory"


# ---- helpers ----------------------------------------------------------------


def _run(
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    full_env = {**os.environ}
    full_env.pop("CLAUDE_PROJECT_DIR", None)
    full_env.pop("PLATXA_MEMORY_AUTO_DIR", None)
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, str(CLI_PATH), *args],
        capture_output=True,
        text=True,
        env=full_env,
        timeout=30,
    )


def _write_topic(directory: Path, name: str, type_: str, body: str) -> Path:
    """Write a minimal v2 topic file with YAML frontmatter."""
    path = directory / name
    path.write_text(
        f"---\nname: {name}\ndescription: {body[:60]}\ntype: {type_}\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return path


# ---- detect_format_version --------------------------------------------------


def test_detect_none_when_no_memory_md(tmp_path: Path) -> None:
    assert detect_format_version(tmp_path) == "none"


def test_detect_none_when_dir_missing(tmp_path: Path) -> None:
    assert detect_format_version(tmp_path / "nonexistent") == "none"


def test_detect_v2_when_memory_md_empty(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text("", encoding="utf-8")
    assert detect_format_version(tmp_path) == "v2"


def test_detect_v2_when_no_bullets(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text("# Memory index\n\n", encoding="utf-8")
    assert detect_format_version(tmp_path) == "v2"


def test_detect_v1_plain_bullets(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text(
        "# Memory\n- User prefers terse responses.\n- Avoid mocking the DB.\n",
        encoding="utf-8",
    )
    assert detect_format_version(tmp_path) == "v1"


def test_detect_v2_all_backed_links(tmp_path: Path) -> None:
    _write_topic(tmp_path, "feedback_style.md", "feedback", "Prefer terse.")
    (tmp_path / "MEMORY.md").write_text(
        "# Memory index\n- [Style](feedback_style.md) — Prefer terse.\n",
        encoding="utf-8",
    )
    assert detect_format_version(tmp_path) == "v2"


def test_detect_v1_link_without_backing_file(tmp_path: Path) -> None:
    # Link target does not exist → treated as v1 plain bullet.
    (tmp_path / "MEMORY.md").write_text(
        "# Memory index\n- [Ghost](ghost.md) — no file here.\n",
        encoding="utf-8",
    )
    assert detect_format_version(tmp_path) == "v1"


def test_detect_v1_link_without_frontmatter(tmp_path: Path) -> None:
    # File exists but has no ``---`` frontmatter → v1.
    (tmp_path / "nofm.md").write_text("just content, no frontmatter\n", encoding="utf-8")
    (tmp_path / "MEMORY.md").write_text(
        "- [No FM](nofm.md) — missing frontmatter.\n",
        encoding="utf-8",
    )
    assert detect_format_version(tmp_path) == "v1"


def test_detect_v1_mixed_bullets(tmp_path: Path) -> None:
    _write_topic(tmp_path, "feedback_x.md", "feedback", "A fact.")
    (tmp_path / "MEMORY.md").write_text(
        "# Memory\n- [X](feedback_x.md) — A fact.\n- Plain bullet not yet migrated.\n",
        encoding="utf-8",
    )
    # One plain bullet → v1.
    assert detect_format_version(tmp_path) == "v1"


# ---- migrate_v1_to_v2 -------------------------------------------------------


def test_migrate_v1_preserves_content(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text(
        "# Memory\n"
        "- User prefers terse responses with no trailing summaries.\n"
        "- We chose Fernet over raw AES-GCM for key-rotation reasons.\n",
        encoding="utf-8",
    )
    result = migrate_v1_to_v2(tmp_path)

    assert result.status == "migrated"
    assert result.migrations_applied == ["v1->v2"]
    assert result.bullets_migrated == 2
    assert len(result.topic_files_written) == 2

    # Every original fact appears verbatim in exactly one topic file.
    for fact in (
        "User prefers terse responses with no trailing summaries.",
        "We chose Fernet over raw AES-GCM for key-rotation reasons.",
    ):
        hits = [
            f
            for f in result.topic_files_written
            if fact in (tmp_path / f).read_text(encoding="utf-8")
        ]
        assert len(hits) == 1, f"Fact not found in exactly one topic file: {fact!r}"


def test_migrate_v1_idempotent(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text(
        "# Memory\n- Integration tests must hit a real database.\n",
        encoding="utf-8",
    )
    first = migrate_v1_to_v2(tmp_path)
    assert first.status == "migrated"

    # Second call must be a no-op.
    second = migrate_v1_to_v2(tmp_path)
    assert second.status == "up-to-date"
    assert second.migrations_applied == []
    assert second.bullets_migrated == 0

    # No extra topic files created.
    md_files = list(tmp_path.glob("*.md"))
    assert len(md_files) == 1 + len(first.topic_files_written)


def test_migrate_v1_index_is_v2_after_migration(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text(
        "# Memory\n- User prefers terse responses.\n",
        encoding="utf-8",
    )
    migrate_v1_to_v2(tmp_path)
    assert detect_format_version(tmp_path) == "v2"


def test_migrate_v1_preserves_existing_v2_links(tmp_path: Path) -> None:
    _write_topic(tmp_path, "feedback_existing.md", "feedback", "Already migrated fact.")
    (tmp_path / "MEMORY.md").write_text(
        "# Memory index\n"
        "- [Existing](feedback_existing.md) — Already migrated fact.\n"
        "- New plain bullet to be migrated.\n",
        encoding="utf-8",
    )
    result = migrate_v1_to_v2(tmp_path)

    assert result.bullets_migrated == 1
    new_index = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
    # Both the old v2 link and the new link must appear in the index.
    assert "feedback_existing.md" in new_index
    assert result.topic_files_written[0] in new_index


def test_migrate_v1_preserves_heading(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text(
        "# My Custom Heading\n- Some fact.\n",
        encoding="utf-8",
    )
    migrate_v1_to_v2(tmp_path)
    new_index = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
    assert new_index.startswith("# My Custom Heading")


def test_migrate_noop_when_version_is_none(tmp_path: Path) -> None:
    result = migrate_v1_to_v2(tmp_path)
    assert result.status == "up-to-date"
    assert result.migrations_applied == []


def test_migrate_noop_when_version_is_v2(tmp_path: Path) -> None:
    _write_topic(tmp_path, "user_role.md", "user", "I am a data scientist.")
    (tmp_path / "MEMORY.md").write_text(
        "# Memory index\n- [Role](user_role.md) — I am a data scientist.\n",
        encoding="utf-8",
    )
    result = migrate_v1_to_v2(tmp_path)
    assert result.status == "up-to-date"


def test_migrate_writes_valid_frontmatter(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text(
        "# Memory\n- Prefer short responses.\n",
        encoding="utf-8",
    )
    result = migrate_v1_to_v2(tmp_path)
    assert result.topic_files_written

    topic = (tmp_path / result.topic_files_written[0]).read_text(encoding="utf-8")
    assert topic.startswith("---\n")
    assert "name:" in topic
    assert "description:" in topic
    assert "type:" in topic
    assert "---" in topic  # closing delimiter


def test_migrate_collision_handling(tmp_path: Path) -> None:
    # Two bullets that produce the same slug → second gets ``_2`` suffix.
    bullet = "Prefer short responses to user questions."
    (tmp_path / "MEMORY.md").write_text(
        f"# Memory\n- {bullet}\n- {bullet}\n",
        encoding="utf-8",
    )
    result = migrate_v1_to_v2(tmp_path)
    assert result.bullets_migrated == 2
    names = result.topic_files_written
    assert names[0] != names[1], "Collision not handled — two identical filenames"
    for name in names:
        assert (tmp_path / name).is_file()


# ---- type classification heuristics ----------------------------------------


@pytest.mark.parametrize(
    ("bullet", "expected"),
    [
        ("User prefers terse responses with no trailing summaries.", "feedback"),
        ("Don't mock the database — integration tests only.", "feedback"),
        ("We chose Fernet over raw AES-GCM for key-rotation reasons.", "feedback"),
        ("Pipeline bugs tracked in Linear project INGEST.", "reference"),
        ("Grafana board at grafana.internal/d/api-latency is oncall.", "reference"),
        ("Merge freeze begins 2026-03-05 for mobile release cut.", "project"),
        ("Auth middleware rewrite is driven by legal compliance.", "project"),
        ("I am a data scientist focused on observability.", "user"),
        ("Deep Go expertise but first time touching the React side.", "user"),
    ],
)
def test_classify_type(bullet: str, expected: str) -> None:
    assert _classify_type(bullet) == expected


def test_classify_type_default_is_user() -> None:
    assert _classify_type("Something completely ambiguous.") == "user"


# ---- slug / title helpers ---------------------------------------------------


def test_make_slug_basic() -> None:
    assert _make_slug("User prefers terse responses.") == "user_prefers_terse_responses"


def test_make_slug_strips_non_alnum() -> None:
    slug = _make_slug("Don't mock the DB! (incident 2026)")
    assert all(c.isalnum() or c == "_" for c in slug)


def test_make_slug_max_five_words() -> None:
    slug = _make_slug("one two three four five six seven eight")
    assert slug.count("_") <= 4  # ≤5 words = ≤4 underscores


def test_make_slug_empty_fallback() -> None:
    assert _make_slug("!!!") == "entry"


def test_make_title_basic() -> None:
    title = _make_title("User prefers terse responses with no trailing summaries.")
    assert "User" in title or "user" in title.lower()
    assert len(title) <= 80


def test_make_title_strips_trailing_punctuation() -> None:
    title = _make_title("Some fact here,")
    assert not title.endswith(",")


# ---- unique path helper -----------------------------------------------------


def test_unique_path_no_collision(tmp_path: Path) -> None:
    p = _unique_path(tmp_path, "feedback_x")
    assert p == tmp_path / "feedback_x.md"
    assert not p.exists()


def test_unique_path_collision(tmp_path: Path) -> None:
    (tmp_path / "feedback_x.md").write_text("exists", encoding="utf-8")
    p = _unique_path(tmp_path, "feedback_x")
    assert p == tmp_path / "feedback_x_2.md"


def test_unique_path_multiple_collisions(tmp_path: Path) -> None:
    for suffix in ("", "_2", "_3"):
        (tmp_path / f"feedback_x{suffix}.md").write_text("exists", encoding="utf-8")
    p = _unique_path(tmp_path, "feedback_x")
    assert p == tmp_path / "feedback_x_4.md"


# ---- CLI integration --------------------------------------------------------


def test_cli_migrate_v1_via_auto_dir(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text(
        "# Memory\n- User prefers terse responses.\n",
        encoding="utf-8",
    )
    result = _run(
        "migrate",
        "--auto-dir",
        str(tmp_path),
        "--format",
        "json",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "migrated"
    assert "v1->v2" in payload["migrations_applied"]
    assert payload["bullets_migrated"] == 1


def test_cli_migrate_v2_is_noop_via_auto_dir(tmp_path: Path) -> None:
    _write_topic(tmp_path, "feedback_style.md", "feedback", "Prefer terse.")
    (tmp_path / "MEMORY.md").write_text(
        "# Memory index\n- [Style](feedback_style.md) — Prefer terse.\n",
        encoding="utf-8",
    )
    result = _run(
        "migrate",
        "--auto-dir",
        str(tmp_path),
        "--format",
        "json",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "up-to-date"
    assert payload["migrations_applied"] == []


def test_cli_migrate_idempotent_via_auto_dir(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text(
        "# Memory\n- Integration tests must hit a real DB.\n",
        encoding="utf-8",
    )
    # First run: migrates.
    r1 = _run("migrate", "--auto-dir", str(tmp_path), "--format", "json")
    assert json.loads(r1.stdout)["status"] == "migrated"

    # Second run: no-op.
    r2 = _run("migrate", "--auto-dir", str(tmp_path), "--format", "json")
    payload2 = json.loads(r2.stdout)
    assert payload2["status"] == "up-to-date"
    assert payload2["migrations_applied"] == []


def test_cli_migrate_none_version_reports_note(tmp_path: Path) -> None:
    # Empty dir — no MEMORY.md → version 'none' → up-to-date with a note.
    result = _run("migrate", "--auto-dir", str(tmp_path), "--format", "json")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "up-to-date"
    assert "note" in payload
    assert "MEMORY.md" in payload["note"]


# ---- review fixes: YAML quoting, path traversal, unhandled lines ------------


def test_migrate_yaml_quotes_colon_in_value(tmp_path: Path) -> None:
    # Bullet contains a colon — would produce malformed YAML if unquoted.
    (tmp_path / "MEMORY.md").write_text(
        '# Memory\n- User said: "never use mocking".\n',
        encoding="utf-8",
    )
    result = migrate_v1_to_v2(tmp_path)
    assert result.topic_files_written
    topic = (tmp_path / result.topic_files_written[0]).read_text(encoding="utf-8")
    # The name/description lines must be double-quoted strings.
    assert 'name: "' in topic
    assert 'description: "' in topic
    # The original bullet text is preserved in the body (below the ---).
    assert 'User said: "never use mocking"' in topic


def test_migrate_path_traversal_link_treated_as_v1(tmp_path: Path) -> None:
    # A MEMORY.md with a bullet link that traverses outside memory_dir should
    # be treated as a v1 plain bullet (not a backed v2 link), even if the
    # target file happens to exist and has frontmatter.
    outside = tmp_path.parent / "outside.md"
    outside.write_text("---\nname: x\ndescription: y\ntype: user\n---\n\nsome fact\n")

    (tmp_path / "MEMORY.md").write_text(
        "# Memory\n- [Escape](../outside.md) — link escapes memory_dir.\n",
        encoding="utf-8",
    )
    # Because the link target is outside memory_dir, _is_v2_line returns False.
    assert detect_format_version(tmp_path) == "v1"

    # Migration converts the plain bullet — it does NOT follow the escape link.
    result = migrate_v1_to_v2(tmp_path)
    assert result.status == "migrated"
    assert result.bullets_migrated == 1
    # No file should have been written outside tmp_path.
    assert not outside.read_text().startswith("- [")  # original not touched


def test_migrate_collects_unhandled_non_bullet_lines(tmp_path: Path) -> None:
    # Non-bullet, non-heading lines must land in unhandled_lines, not silently dropped.
    (tmp_path / "MEMORY.md").write_text(
        "# Memory\n"
        "- A plain bullet fact.\n"
        "Some raw paragraph text that is not a bullet.\n"
        "Another non-bullet line.\n",
        encoding="utf-8",
    )
    result = migrate_v1_to_v2(tmp_path)
    assert result.bullets_migrated == 1
    assert len(result.unhandled_lines) == 2
    assert "Some raw paragraph text" in result.unhandled_lines[0]
    assert "Another non-bullet" in result.unhandled_lines[1]
