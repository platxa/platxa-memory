"""Stack detector for platxa-memory.

Walks up the directory tree from a starting path, matches marker files
(``pyproject.toml``, ``package.json``, ``go.mod``, ``Cargo.toml``,
``pom.xml``, ``Gemfile``, ``build.gradle`` / ``build.gradle.kts``,
``composer.json``, ``mix.exs``, ``tsconfig.json``, …) and returns a
structured :class:`StackInfo` describing the primary stack, any
secondary stacks co-located at the same level (multi-stack repos), and
the absolute paths of every marker that contributed to the decision.

Design notes:

- **Tree walk** from ``start`` upward — the caller typically passes the
  current working directory or ``$CLAUDE_PROJECT_DIR``. The walk stops at
  filesystem root or when ``max_depth`` levels have been inspected,
  whichever comes first, to guard against pathological symlink loops.
- **First-hit wins**: the nearest ancestor with any marker defines the
  stack. Stacks found at that level are classified; higher ancestors are
  ignored, which prevents a vendored repo under ``/src/vendor/foo`` from
  being overridden by a parent's marker file.
- **Priority ordering**: when multiple markers coexist at the same level
  (a Python/TS monorepo root, for instance), the stack listed earliest in
  :data:`STACK_PRIORITY` becomes ``primary``; the rest become
  ``secondary``. Ties are broken by the marker-family order, not by file
  name, so a ``pyproject.toml`` beats a ``package.json`` at the same
  level deterministically.
- **Graceful fallback**: when no markers are found anywhere between
  ``start`` and the root (e.g. a directory containing only ``.git``), the
  detector returns ``StackInfo(primary="generic", secondary=(),
  markers=())`` rather than raising. Callers can treat the ``generic``
  label as "unknown".

Hard constraint (see CLAUDE.md): stdlib only — no SDK, no API, no LLM.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

# Priority order: the first stack with any marker at the chosen level is the
# primary. Order is intentional — Python and TypeScript sit above JavaScript
# so a `tsconfig.json` + `package.json` pair is classified as TypeScript, and
# a `pyproject.toml` + `package.json` pair (common in hybrid repos) becomes
# Python-primary with JavaScript as a secondary stack.
STACK_PRIORITY: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("python", ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")),
    ("typescript", ("tsconfig.json",)),
    ("javascript", ("package.json",)),
    ("go", ("go.mod",)),
    ("rust", ("Cargo.toml",)),
    ("java", ("pom.xml", "build.gradle", "build.gradle.kts")),
    ("ruby", ("Gemfile",)),
    ("php", ("composer.json",)),
    ("elixir", ("mix.exs",)),
)

DEFAULT_MAX_DEPTH = 25


@dataclass(frozen=True)
class StackInfo:
    """Structured result of a stack-detection walk.

    Attributes
    ----------
    primary:
        The highest-priority stack detected at the nearest ancestor with
        marker files. ``"generic"`` when no markers were found.
    secondary:
        Other stacks that share the same ancestor directory. Empty tuple
        when the directory is single-stack or when nothing was detected.
    markers:
        ``(stack, absolute_path)`` pairs for every marker file that
        contributed to the classification, in priority order.
    """

    primary: str
    secondary: tuple[str, ...]
    markers: tuple[tuple[str, Path], ...]

    @property
    def is_multi_stack(self) -> bool:
        """True when the detector found more than one stack at the same level."""
        return bool(self.secondary)

    @property
    def stacks(self) -> tuple[str, ...]:
        """All stacks detected at the chosen level, primary first."""
        if self.primary == "generic":
            return ()
        return (self.primary, *self.secondary)


def _walk_up(start: Path) -> Iterator[Path]:
    """Yield ``start`` and every ancestor up to the filesystem root."""
    current = start
    while True:
        yield current
        parent = current.parent
        if parent == current:
            return
        current = parent


def _markers_at(directory: Path) -> list[tuple[str, Path]]:
    """Return ``(stack, marker_path)`` pairs found directly in ``directory``.

    The result preserves :data:`STACK_PRIORITY` order, which is what makes
    the ``primary`` / ``secondary`` split deterministic for multi-stack
    roots.
    """
    hits: list[tuple[str, Path]] = []
    try:
        for stack, filenames in STACK_PRIORITY:
            for filename in filenames:
                candidate = directory / filename
                if candidate.is_file():
                    hits.append((stack, candidate.resolve()))
    except OSError:
        # Permission denied or broken filesystem — treat as no marker.
        return []
    return hits


def _build_stack_info(markers: list[tuple[str, Path]]) -> StackInfo:
    seen: list[str] = []
    for stack, _ in markers:
        if stack not in seen:
            seen.append(stack)
    primary = seen[0]
    secondary = tuple(seen[1:])
    return StackInfo(primary=primary, secondary=secondary, markers=tuple(markers))


def detect_stack(
    start: Path | str | None = None,
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> StackInfo:
    """Walk up from ``start`` and classify the project stack.

    Parameters
    ----------
    start:
        Starting directory (or a file path whose parent is used). Defaults
        to the current working directory when ``None``.
    max_depth:
        Maximum number of ancestor directories to inspect before giving
        up. The default is deliberately generous; lower it for tests or
        tight sandboxes.

    Returns
    -------
    :class:`StackInfo`
        Structured result. ``primary == "generic"`` when no markers are
        found — this is the documented graceful-fallback path (the spec's
        ".git-only directory" case).
    """
    try:
        base = Path(start).expanduser().resolve() if start is not None else Path.cwd()
    except OSError:
        return StackInfo(primary="generic", secondary=(), markers=())

    directory = base if base.is_dir() else base.parent
    for depth, candidate in enumerate(_walk_up(directory)):
        if depth >= max_depth:
            break
        markers = _markers_at(candidate)
        if markers:
            return _build_stack_info(markers)

    return StackInfo(primary="generic", secondary=(), markers=())
