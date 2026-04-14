---
name: memory-status
description: >-
  Report the current state of every memory layer visible to Claude Code in
  this project. Lists size, last-modified time, estimated token cost, and
  loaded-in-session status for CLAUDE.md hierarchy, .claude/rules/, auto
  memory, agent memory, and instincts. Each layer gets a green/yellow/red
  indicator against a token budget. Read-only — no files are mutated. Use
  when the user asks to "show memory status", "audit what's loaded",
  "/memory-status", or wants to understand why the session context is heavy.
user-invocable: true
allowed-tools:
  - Read
  - Bash
  - Glob
  - Grep
metadata:
  version: "1.0.0"
  author: "DJ Patel"
  tags:
    - memory
    - status
    - analyzer
    - read-only
---

# Memory Status — Five-Layer Inventory

Read-only inspector that surfaces every memory artifact loaded (or loadable)
in the current session, so the user can see at a glance where context budget
is being spent before it becomes a problem.

## Overview

platxa-memory spans five distinct memory layers. Each has its own storage
location, loading trigger, and lifetime. When context gets heavy, the first
question is always "what is loaded, and from which layer?". This skill answers
that question.

The five layers (ordered by loading priority):

| # | Layer | Storage |
|---|-------|---------|
| 1 | CLAUDE.md hierarchy | `CLAUDE.md` + `~/.claude/CLAUDE.md` + `CLAUDE.local.md` + managed policy |
| 2 | `.claude/rules/` | path-scoped rule files with `paths:` frontmatter |
| 3 | Auto memory | `~/.claude/projects/<hash>/memory/MEMORY.md` + topic files |
| 4 | Agent memory | `.claude/agent-memory/<agent>/` (project) + `~/.claude/agent-memory/<agent>/` (user) |
| 5 | Instincts | learned behavioral patterns with confidence scores |

For every file found, this skill reports: size (bytes, lines), last-modified
ISO date, estimated token cost, and whether it is actually loaded into the
current session (vs present on disk but not triggered).

## Token cost model

Token cost is estimated with the canonical 4-chars-per-token heuristic:
`tokens ≈ ceil(byte_count / 4)`. This is deliberately a rough estimate — it
trades accuracy for not spinning up a tokenizer. The indicator thresholds
below assume this model.

## Green / Yellow / Red thresholds

Per-layer totals are categorised by token cost:

| Indicator | Per-layer tokens | Meaning |
|-----------|-----------------|---------|
| 🟢 green | ≤ 5 000 | Comfortable, no action required |
| 🟡 yellow | 5 001 – 25 000 | Watch — consider trimming at next milestone |
| 🔴 red | > 25 000 | Over budget — prune, compact, or compress now |

These are defaults. A user may override by setting
`PLATXA_MEMORY_STATUS_THRESHOLDS=<green>:<yellow>` in env (e.g.
`4000:20000`). When the env var is unset, fall back to the defaults above.

## Process

Copy this checklist and tick each step:

```
Progress:
- [ ] Step 1: Resolve locations (repo root, user home, auto-memory dir)
- [ ] Step 2: Inventory layer 1 — CLAUDE.md hierarchy
- [ ] Step 3: Inventory layer 2 — .claude/rules/
- [ ] Step 4: Inventory layer 3 — auto memory
- [ ] Step 5: Inventory layer 4 — agent memory (project + user)
- [ ] Step 6: Inventory layer 5 — instincts
- [ ] Step 7: Compute per-layer totals and indicator colours
- [ ] Step 8: Emit report
```

### Step 1: Resolve locations

```bash
REPO=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
# Auto-memory dir: Claude Code hashes the repo path. We can't compute the
# hash ourselves; list candidates and let the user confirm in Step 4.
AUTO_MEM_ROOT="$HOME/.claude/projects"
AGENT_MEM_USER="$HOME/.claude/agent-memory"
AGENT_MEM_PROJECT="$REPO/.claude/agent-memory"
```

Record all paths before any read — a missing dir is valuable signal, not an
error.

### Step 2: Inventory layer 1 — CLAUDE.md hierarchy

Probe each possible location. Missing files count as 0 tokens; report them
explicitly so the user sees what *could* load but does not.

```bash
# Ordered as Claude Code loads them:
#  1. Managed policy (Linux: /etc/claude-code/CLAUDE.md)
#  2. User scope       (~/.claude/CLAUDE.md)
#  3. Project parent chain (walk up from REPO to /)
#  4. Project root    ($REPO/CLAUDE.md)
#  5. Project local   ($REPO/CLAUDE.local.md)
```

For each file found: `wc -c`, `wc -l`, `stat -c%y` for modified time, and
`tokens = bytes / 4`.

### Step 3: Inventory layer 2 — .claude/rules/

```bash
find "$REPO/.claude/rules" -type f -name '*.md' 2>/dev/null
```

For each rule file, read the YAML frontmatter and report the `paths:` field
so the user sees which file globs will trigger the rule. A rule without
`paths:` loads unconditionally — flag these with a `(always-on)` tag.

### Step 4: Inventory layer 3 — auto memory

```bash
# Auto memory lives under ~/.claude/projects/<hash>/memory/
# The hash is deterministic but Claude Code-internal. Enumerate all
# candidates; the active one is the largest-mtime directory whose presence
# correlates with the current session.
find "$AUTO_MEM_ROOT" -maxdepth 3 -name MEMORY.md -printf '%T@ %p\n' 2>/dev/null \
  | sort -nr | head -10
```

Report: the most recently modified `MEMORY.md` under this root is the
probable active auto-memory for this session. Also list every topic file
in the same directory (`*.md` siblings of `MEMORY.md`).

Do NOT guess at the hash-to-path mapping — print candidates and let the
user confirm with `/memory` if needed.

### Step 5: Inventory layer 4 — agent memory

Two roots to cover:

```bash
# Project scope — committed to the repo
find "$AGENT_MEM_PROJECT" -type f -name '*.md' 2>/dev/null

# User scope — cross-project
find "$AGENT_MEM_USER" -type f -name '*.md' 2>/dev/null
```

Group results by agent directory name (e.g., `memory-curator/`,
`memory-auditor/`) and report a sub-total per agent. A sprawling agent dir
(>30 files or >15k tokens) is a yellow flag by itself even if the absolute
total is green.

### Step 6: Inventory layer 5 — instincts

Instinct files usually live under `.claude/instincts/` (project) or
`~/.claude/instincts/` (user) as YAML or JSON with a `confidence:` field.
Enumerate:

```bash
find "$REPO/.claude/instincts" "$HOME/.claude/instincts" \
  -type f \( -name '*.yaml' -o -name '*.yml' -o -name '*.json' \) 2>/dev/null
```

For each instinct file, extract the `confidence:` value and show it
alongside the size. Instincts with `confidence < 0.5` should be flagged
(🟡) even if small — low-confidence patterns consume context without
earning it.

### Step 7: Compute per-layer totals and indicator colours

For each of the 5 layers, sum the token estimates. Apply thresholds from the
"Green / Yellow / Red thresholds" section. Respect the
`PLATXA_MEMORY_STATUS_THRESHOLDS` override when set.

### Step 8: Emit report

## Output format

Emit a structured markdown report. The format is stable so downstream tooling
can parse it. Tables use fixed columns. Indicators are emoji + color name so
plain-text consumers are not broken.

```
# Memory Status — <YYYY-MM-DD HH:MM UTC>

## Summary
| Layer | Files | Tokens | Indicator |
|-------|-------|--------|-----------|
| 1. CLAUDE.md hierarchy | N | 1 234   | 🟢 green  |
| 2. .claude/rules/      | N | 3 410   | 🟢 green  |
| 3. Auto memory         | N | 7 900   | 🟡 yellow |
| 4. Agent memory        | N | 26 400  | 🔴 red    |
| 5. Instincts           | N |   620   | 🟢 green  |
| **TOTAL**              | N | 39 564  | —        |

## Layer 1 — CLAUDE.md hierarchy
- /etc/claude-code/CLAUDE.md                        : (not present)
- ~/.claude/CLAUDE.md                               : 322 L · 8 KB · 2 048 tok · 2026-03-11
- /home/.../parent/CLAUDE.md                        : 135 L · 3 KB ·   768 tok · 2026-04-01
- <repo>/CLAUDE.md                                  :  40 L · 1 KB ·   256 tok · 2026-04-15
- <repo>/CLAUDE.local.md                            : (not present)

## Layer 2 — .claude/rules/
- common.md        (paths: **)                      : 40 L · 1 KB · 256 tok · 2026-04-10
- python.md        (paths: **/*.py)                 : 60 L · 2 KB · 512 tok · 2026-04-10

## Layer 3 — Auto memory
Active candidate: ~/.claude/projects/<hash>/memory/
- MEMORY.md                                         : 12 L · 0 KB ·  62 tok · 2026-04-15
- feedback_phase4_lean_review.md                    : 14 L · 1 KB ·  128 tok · 2026-04-15
- feedback_skill_generation.md                      : 17 L · 1 KB ·  156 tok · 2026-04-15

## Layer 4 — Agent memory
memory-curator/        : 0 files · 0 tok · (empty)
memory-synthesizer/    : 0 files · 0 tok · (empty)
memory-auditor/        : 0 files · 0 tok · (empty)
memory-researcher/     : 0 files · 0 tok · (empty)

## Layer 5 — Instincts
(none found at .claude/instincts/ or ~/.claude/instincts/)

## Recommendations
- 🔴 Layer 4 is over the 25 000-token threshold. Run /memory-prune or invoke
  the memory-curator to consolidate.
- 🟡 Layer 3 (auto memory) is approaching the threshold; a synthesizer pass
  at session end would help.
```

When a layer has no files, render `(empty)` for that layer and colour it
green. When a recommendation block has nothing to report, write
`(no action required)` rather than omitting the section — a stable report
schema matters for downstream parsing.

## Options

| Flag | Effect |
|------|--------|
| `--json` | Emit JSON instead of the markdown report above |
| `--layer <1-5>` | Inspect a single layer in detail |
| `--min-tokens <N>` | Hide files below N tokens in per-layer listings |
| `--no-color` | Drop the emoji indicators (use `[G]`/`[Y]`/`[R]` text) |

Env: `PLATXA_MEMORY_STATUS_THRESHOLDS=<green>:<yellow>` overrides the
default 5 000 / 25 000 thresholds.

## Output Checklist

Before returning to the user, verify:

- [ ] All 5 layers appear in the Summary table (even if empty).
- [ ] Each layer has a single 🟢/🟡/🔴 indicator.
- [ ] Every listed file has a size, line count, token estimate, and ISO mtime.
- [ ] No files were written or modified (this skill is strictly read-only).
- [ ] The report's section order matches the schema in "Output format".

## Examples

### Example 1: Healthy project

```
User: /memory-status
Assistant: # Memory Status — 2026-04-15 09:12 UTC

           ## Summary
           | Layer | Files | Tokens | Indicator |
           |---|---|---|---|
           | 1. CLAUDE.md hierarchy | 3 |  3 072 | 🟢 green  |
           | 2. .claude/rules/      | 2 |    768 | 🟢 green  |
           | 3. Auto memory         | 3 |    346 | 🟢 green  |
           | 4. Agent memory        | 4 |      0 | 🟢 green  |
           | 5. Instincts           | 0 |      0 | 🟢 green  |

           (no action required)
```

### Example 2: Heavy context — agent memory over budget

```
User: /memory-status
Assistant: # Memory Status — 2026-04-20 14:02 UTC
           ...
           ## Summary
           | Layer | Files | Tokens | Indicator |
           |---|---|---|---|
           | 4. Agent memory        | 42 | 34 000 | 🔴 red    |
           ...
           ## Recommendations
           - 🔴 Layer 4 is over the 25 000-token threshold. Top agents:
             memory-curator/ 22 000, memory-synthesizer/ 9 500.
             Consider /memory-prune or a memory-curator consolidation pass.
```

### Example 3: Single-layer deep dive with JSON

```
User: /memory-status --layer 2 --json
Assistant: {"layer":2,"name":".claude/rules/","indicator":"green",
           "tokens":768,"files":[
             {"path":".claude/rules/common.md","tokens":256,"lines":40,
              "modified":"2026-04-10","paths":"**"},
             {"path":".claude/rules/python.md","tokens":512,"lines":60,
              "modified":"2026-04-10","paths":"**/*.py"}]}
```

## Gotchas

| Problem | Cause | Mitigation |
|---------|-------|------------|
| Auto-memory dir reports "unknown" | Path contains a Claude-Code-internal hash | Enumerate candidates and surface them — do not fabricate a mapping |
| Token estimate feels low for XML-heavy files | 4-chars-per-token model over-counts for ASCII prose | Treat estimates as ±25% accurate; use for indicators, not for exact billing |
| `find` errors on user-scope dir on fresh install | `~/.claude/` does not exist yet | Redirect stderr to `/dev/null`; missing dirs count as 0 files / 0 tokens |
| Indicator flips between runs with no file change | Threshold env var is set in one shell and not another | Always print the active thresholds at the top of the report |
| "Loaded in session" column is always unknown | Claude Code does not expose which files it actually injected | Report "on disk" accurately and note the limitation rather than guessing |

<!-- managed by platxa-skill-generator -->
