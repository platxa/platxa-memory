"""platxa-memory — cross-session memory plugin for Claude Code.

This package bundles the shared Python library used by the plugin's hooks,
the ``bin/platxa-memory`` CLI, and the test suite. Hooks and the CLI live
as standalone scripts on disk; importing from ``platxa_memory`` lets them
share detection logic without duplicating constants.

Hard constraint (see CLAUDE.md): stdlib only — no SDK, no API, no LLM.
"""

from .atomic import atomic_write, atomic_write_bytes, atomic_write_text
from .stack import StackInfo, detect_stack

__all__ = (
    "StackInfo",
    "atomic_write",
    "atomic_write_bytes",
    "atomic_write_text",
    "detect_stack",
)
