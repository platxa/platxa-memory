# AGENTS.md

This repository uses `CLAUDE.md` as the canonical agent-instruction
file. Tools that look for `AGENTS.md` (Cursor, OpenAI codex-cli, and
other harnesses) read this file, which re-exports `CLAUDE.md` via a
single-hop import so the two stay in sync automatically.

@CLAUDE.md

<!--
Why a shim instead of a duplicate?

Keeping two independent files leads to drift: a rule added to CLAUDE.md
is forgotten in AGENTS.md three weeks later. A one-line @import means
every agent harness sees the same instructions without a sync step.

The @import below expands CLAUDE.md inline. That file in turn imports
stack-specific rule files from .claude/rules/ when uncommented. Total
hop depth:

    AGENTS.md -> CLAUDE.md -> .claude/rules/<stack>.md  (depth 3)

Claude Code's 5-hop transitive-import limit is comfortably respected.
-->
