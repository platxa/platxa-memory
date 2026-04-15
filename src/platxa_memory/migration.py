"""v1 → v2 memory-format migration helper for platxa-memory.

Schema overview
---------------
**v1 layout** — ``MEMORY.md`` body is a plain bulleted list of durable facts.
No frontmatter, no sibling topic files.

::

    # Memory
    - User prefers terse responses with no trailing summaries.
    - We chose Fernet over raw AES-GCM for key-rotation reasons.

**v2 layout** — ``MEMORY.md`` is an index of links to sibling topic files.
Each topic file carries YAML frontmatter (``name`` / ``description`` / ``type``).

::

    # Memory index
    - [User style preferences](feedback_user_style.md) — User prefers terse responses
    - [Crypto choice](feedback_crypto_choice.md) — Fernet over raw AES-GCM

Public surface
--------------
- :func:`detect_format_version` — non-mutating version detector
- :func:`migrate_v1_to_v2` — idempotent in-place migration
- :class:`MigrationResult` — structured migration outcome

Hard constraint (see CLAUDE.md): stdlib only — no SDK, no API, no LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .atomic import atomic_write_text

# ---- compiled regexes -------------------------------------------------------

# Matches a Markdown bullet link: ``- [title](filename.md)``
_LINK_RE: re.Pattern[str] = re.compile(
    r"^\s*-\s+\[([^\]]+)\]\(([^)]+\.md)\)",
    re.IGNORECASE,
)

# Matches any Markdown bullet: ``- <content>``
_BULLET_RE: re.Pattern[str] = re.compile(r"^\s*-\s+(.+)$")

# ---- type classification keywords -------------------------------------------

_TYPE_KEYWORDS: dict[str, list[str]] = {
    "feedback": [
        "prefer",
        "want",
        "style",
        "terse",
        "don't",
        "avoid",
        "stop",
        "never",
        "always",
        "correct",
        "wrong",
        "approach",
        "feedback",
        "guidance",
        "rule",
        "instead",
        "rather than",
        "not to",
        "should not",
        "do not",
        "burned",
        "incident",
        "chose",
        "chosen",
        "over raw",
        "reason",
    ],
    "reference": [
        "linear",
        "grafana",
        "slack",
        "jira",
        "notion",
        "asana",
        "dashboard",
        "board",
        "external",
        "tracker",
        "monitoring",
        "github.com",
        "gitlab.com",
        "http",
        "url",
        "link",
    ],
    "project": [
        "project",
        "deadline",
        "milestone",
        "sprint",
        "freeze",
        "release",
        "branch",
        "decision",
        "we're",
        "we are",
        "the team",
        "module",
        "feature",
        "initiative",
        "blocked",
        "ongoing",
        "in progress",
        "rewrite",
        "compliance",
        "legal",
        "driven by",
        "migration",
    ],
    "user": [
        "i am",
        "i'm",
        "my role",
        "years experience",
        "expertise",
        "background",
        "engineer",
        "developer",
        "data scientist",
        "architect",
        "first time",
        "new to",
    ],
}

# Evaluation order matters: feedback and reference are checked before the more
# generic project / user buckets so that e.g. "avoid mocking the database (incident)"
# lands in "feedback" rather than "user".
_TYPE_ORDER: tuple[str, ...] = ("feedback", "reference", "project", "user")


# ---- internal helpers -------------------------------------------------------


def _yaml_quote(s: str) -> str:
    """Return *s* safely double-quoted for a YAML scalar value.

    Escapes backslashes, double-quotes, and newlines so that values
    containing colons, quotes, or other YAML-significant characters do not
    produce malformed frontmatter.
    """
    escaped = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _classify_type(text: str) -> str:
    """Heuristically classify a memory bullet into one of the four memory types.

    Returns ``'feedback'``, ``'reference'``, ``'project'``, or ``'user'``
    (the default when no keyword matches).
    """
    low = text.lower()
    for type_name in _TYPE_ORDER:
        for kw in _TYPE_KEYWORDS[type_name]:
            if kw in low:
                return type_name
    return "user"


def _make_slug(text: str) -> str:
    """Derive a filesystem-safe slug from the first words of *text*.

    Retains only ASCII letters, digits, and spaces; takes at most the first
    five tokens; joins with underscores.  Falls back to ``'entry'`` when the
    cleaned text is empty.
    """
    cleaned = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    words = [w for w in cleaned.split() if w][:5]
    return "_".join(words) or "entry"


def _make_title(text: str) -> str:
    """Derive a display title from the first few words of *text*.

    Returns a capitalised, punctuation-stripped string of at most 80 chars.
    """
    words = text.strip().split()[:7]
    title = " ".join(words).rstrip(".,;:")
    return (title[:80] if len(title) > 80 else title) or "Memory entry"


def _unique_path(memory_dir: Path, stem: str) -> Path:
    """Return a :class:`Path` for a new topic file that does not yet exist.

    When ``{stem}.md`` is already present, appends ``_2``, ``_3``, … until a
    free name is found.
    """
    candidate = memory_dir / f"{stem}.md"
    if not candidate.exists():
        return candidate
    i = 2
    while True:
        candidate = memory_dir / f"{stem}_{i}.md"
        if not candidate.exists():
            return candidate
        i += 1


def _is_v2_line(line: str, memory_dir: Path) -> bool:
    """Return ``True`` when *line* is a bullet link to a frontmatter topic file.

    A v2 bullet matches ``- [title](target.md)`` where:
    - *target.md* resolves to an existing file inside *memory_dir*
    - that file begins with ``---`` (YAML frontmatter)
    """
    m = _LINK_RE.match(line)
    if not m:
        return False
    # Resolve against memory_dir and guard against path traversal: the target
    # must remain inside the memory directory (``../../etc/passwd.md`` is not
    # a valid topic file).
    try:
        target = (memory_dir / m.group(2)).resolve()
        mem_root = memory_dir.resolve()
        if not target.is_relative_to(mem_root):
            return False
    except (OSError, ValueError):
        return False
    if not target.is_file():
        return False
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        return content.startswith("---")
    except OSError:
        return False


# ---- public API -------------------------------------------------------------


def detect_format_version(memory_dir: Path) -> str:
    """Detect the memory schema version of *memory_dir*.

    Parameters
    ----------
    memory_dir:
        Path to the auto-memory directory (the directory that contains
        ``MEMORY.md`` and optional topic files).

    Returns
    -------
    ``'v2'``
        All bullet lines in ``MEMORY.md`` are frontmatter-backed
        ``[title](file.md)`` links, or ``MEMORY.md`` exists but has no
        bullet lines at all (already current or freshly initialised).
    ``'v1'``
        ``MEMORY.md`` exists and at least one bullet is NOT a backed link
        (plain text fact — must be migrated).
    ``'none'``
        ``MEMORY.md`` is absent or unreadable.
    """
    memory_md = memory_dir / "MEMORY.md"
    if not memory_md.is_file():
        return "none"
    try:
        text = memory_md.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "none"

    bullet_lines = [line for line in text.splitlines() if _BULLET_RE.match(line)]
    if not bullet_lines:
        # No bullets → treat as v2 (blank index or heading-only MEMORY.md).
        return "v2"

    for line in bullet_lines:
        if not _is_v2_line(line, memory_dir):
            return "v1"
    return "v2"


@dataclass
class MigrationResult:
    """Structured outcome of a :func:`migrate_v1_to_v2` call.

    Attributes
    ----------
    status:
        ``'migrated'`` — at least one bullet was converted.
        ``'up-to-date'`` — no migration was necessary (idempotent call).
    migrations_applied:
        Names of migration edges applied (e.g. ``['v1->v2']``).
        Empty when ``status == 'up-to-date'``.
    topic_files_written:
        Filenames (not full paths) of newly created topic files.
    bullets_migrated:
        Count of v1 bullets converted.
    unhandled_lines:
        Non-heading, non-bullet lines from the original MEMORY.md that
        were not automatically migrated (e.g. sub-headings, paragraph text).
        The caller or agent should inspect these and handle them manually.
        Empty for standard v1 layouts that contain only a heading + bullets.
    """

    status: str
    migrations_applied: list[str] = field(default_factory=list)
    topic_files_written: list[str] = field(default_factory=list)
    bullets_migrated: int = 0
    unhandled_lines: list[str] = field(default_factory=list)


def migrate_v1_to_v2(memory_dir: Path) -> MigrationResult:
    """Migrate *memory_dir* from v1 to v2 layout in-place.

    The function:

    1. Detects the format version via :func:`detect_format_version`.
    2. Returns ``MigrationResult(status='up-to-date')`` immediately when the
       directory is not v1 (idempotent).
    3. Parses ``MEMORY.md`` and partitions bullet lines into:
       - already-v2 lines (``[title](backed-file.md)`` links) — preserved as-is
       - plain-text v1 bullets — converted to topic files + index links
    4. For each plain bullet:
       - classifies it into ``user | feedback | project | reference``
       - derives a filename slug and a display title
       - writes ``{type}_{slug}.md`` with YAML frontmatter + original text
    5. Rewrites ``MEMORY.md`` as a v2 index (original heading preserved,
       existing v2 links kept, new links appended).

    All writes go through :func:`~platxa_memory.atomic.atomic_write_text` so
    a crash mid-migration never leaves a half-written file.

    Parameters
    ----------
    memory_dir:
        The auto-memory directory (must contain ``MEMORY.md`` for v1 to be
        detected; otherwise returns ``up-to-date``).

    Returns
    -------
    :class:`MigrationResult`
        Full description of what was done.
    """
    version = detect_format_version(memory_dir)
    if version != "v1":
        return MigrationResult(status="up-to-date")

    memory_md = memory_dir / "MEMORY.md"
    text = memory_md.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    # Preserve the first heading line; fall back to a sensible default.
    heading = next((ln for ln in lines if ln.startswith("#")), "# Memory index")

    # Partition lines into bullets (v2 or plain) and everything else.
    existing_v2_lines: list[str] = []
    plain_bullets: list[str] = []
    unhandled: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or line.startswith("#"):
            # Blank lines and headings are structural — not unhandled content.
            continue
        if _BULLET_RE.match(line):
            if _is_v2_line(line, memory_dir):
                existing_v2_lines.append(line.rstrip())
            else:
                m = _BULLET_RE.match(line)
                if m:
                    plain_bullets.append(m.group(1).strip())
        else:
            # Non-bullet, non-heading content (paragraph text, sub-headings
            # that don't start with "#", raw facts).  Collect for the caller.
            unhandled.append(line.rstrip())

    # Write a topic file for each plain bullet.
    new_v2_lines: list[str] = []
    topic_files: list[str] = []

    for bullet in plain_bullets:
        type_name = _classify_type(bullet)
        slug = _make_slug(bullet)
        stem = f"{type_name}_{slug}"
        topic_path = _unique_path(memory_dir, stem)
        title = _make_title(bullet)
        # Truncate description at 80 chars to keep the index line readable.
        desc = bullet[:80]

        # YAML-quote name and description to prevent injection from colons,
        # quotes, or other YAML-significant characters in bullet text.
        frontmatter = (
            f"---\n"
            f"name: {_yaml_quote(title)}\n"
            f"description: {_yaml_quote(desc)}\n"
            f"type: {type_name}\n"
            f"---\n"
            f"\n"
            f"{bullet}\n"
        )
        atomic_write_text(topic_path, frontmatter)
        topic_files.append(topic_path.name)
        new_v2_lines.append(f"- [{title}]({topic_path.name}) — {desc}")

    # Rewrite MEMORY.md as v2 index (heading + blank line + all link bullets).
    all_links = existing_v2_lines + new_v2_lines
    new_index = heading + "\n\n" + "\n".join(all_links) + "\n"
    atomic_write_text(memory_md, new_index)

    return MigrationResult(
        status="migrated",
        migrations_applied=["v1->v2"],
        topic_files_written=topic_files,
        bullets_migrated=len(plain_bullets),
        unhandled_lines=unhandled,
    )


__all__ = (
    "MigrationResult",
    "detect_format_version",
    "migrate_v1_to_v2",
)
