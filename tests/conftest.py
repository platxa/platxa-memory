"""Shared pytest fixtures for platxa-memory hook tests.

Hooks live under ``hooks/`` rather than a packaged module, so we inject the
repo's ``hooks/`` directory onto ``sys.path`` once per session. Each test
module then imports the hook under test by name.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))
