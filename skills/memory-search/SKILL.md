---
name: memory-search
description: >-
  Use when the user asks to "search memory", "find in memory",
  "/memory-search PATTERN", "look up a memory entry", or wants to locate a
  specific fact across the platxa-memory directories. Runs a ripgrep-backed
  full-text search across every memory file visible to the plugin — both
  project scope (repo-local rules, agent memory, instincts, CLAUDE.md,
  CLAUDE.local.md) and user scope (~/.claude/ agent memory, instincts,
  global CLAUDE.md, auto-memory). Case-insensitive regex by default, falls
  back to grep -rEn if rg is unavailable. Read-only — no mutations.
user-invocable: true
argument-hint: PATTERN [--scope project|user|all] [--limit N] [--format text|json]
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
    - search
    - ripgrep
    - read-only
---

# Memory Search — Ripgrep-Backed Full-Text Search

Fast, structured full-text search over every memory file the platxa-memory
plugin tracks. Read-only: the skill never mutates a byte of memory, it only
reports what it finds.

## Overview

Memory accumulates across many small files: per-agent memory dirs, rule
files, instinct YAMLs, CLAUDE.md hierarchy, and the machine-local auto-memory
store. When a user (or another agent) needs to confirm "did we decide this
already" or "where is the retry-logic note", dumping every file is wasteful.
Targeted search is the right tool.

This skill wraps `rg` (ripgrep) — the fastest pragmatic grep — with a
scope-aware root set, sane defaults, and structured output. When `rg` is
missing (fresh container, restricted CI), it falls back to
`grep -rEn --include='*.md'` so the skill always works.

## Search scope

The full set of searchable roots, grouped by scope:

**Project scope (repo-local):**
- `CLAUDE.md`
- `CLAUDE.local.md`
- `.claude/rules/`
- `.claude/agent-memory/`
- `.claude/instincts/`

**User scope (cross-project, under `$HOME`):**
- `~/.claude/CLAUDE.md`
- `~/.claude/agent-memory/`
- `~/.claude/instincts/`
- `~/.claude/projects/HASH/memory/` (auto-memory, one hash per project)

The `--scope` flag picks which roots are searched:

| `--scope` | Roots |
|-----------|-------|
| `project` | project-scope roots only |
| `user` | user-scope roots only |
| `all` (default) | every root above |

## Options

| Flag | Default | Meaning |
|------|---------|---------|
| `--scope project\|user\|all` | `all` | which root set to search |
| `--limit N` | `25` | cap on total matches returned |
| `--format text\|json` | `text` | output shape (see "Output format") |
| `--case-sensitive` | off | disable the default case-insensitive match |
| `--fixed-strings` | off | pass `-F` to rg/grep — treat PATTERN as literal text |

The first positional argument is `PATTERN`. It is interpreted as the
default rg/grep regex flavour (ERE-style). If your environment has rg
built with PCRE2 and you need lookarounds or backrefs, invoke the skill
as a shell escape (`!rg -P ...`) rather than adding runtime-environment
detection to this skill.

## Process

Copy this checklist and tick each step:

```
Progress:
- [ ] Step 1: Parse arguments and validate PATTERN
- [ ] Step 2: Assemble the root set for the chosen --scope
- [ ] Step 3: Choose search engine (rg preferred, grep fallback)
- [ ] Step 4: Execute search with --limit honoured
- [ ] Step 5: Tag each hit with its memory layer
- [ ] Step 6: Emit results in the chosen --format
```

### Step 1: Parse arguments

```bash
PATTERN="$1"
[ -z "$PATTERN" ] && {
  echo "Usage: /memory-search PATTERN [--scope ...] [--limit N] [--format ...]" >&2
  exit 2
}
SCOPE="all"
LIMIT=25
FORMAT="text"
CASE_FLAG="-i"
FIXED_FLAG=""
# shift and parse remaining flags
```

Reject empty PATTERN with exit 2 (usage error). Do NOT silently default to
match-everything — that ruins the token budget.

### Step 2: Assemble the root set

```bash
PROJECT_ROOTS=(
  "CLAUDE.md"
  "CLAUDE.local.md"
  ".claude/rules"
  ".claude/agent-memory"
  ".claude/instincts"
)
USER_ROOTS=(
  "$HOME/.claude/CLAUDE.md"
  "$HOME/.claude/agent-memory"
  "$HOME/.claude/instincts"
  "$HOME/.claude/projects"
)
case "$SCOPE" in
  project) ROOTS=("${PROJECT_ROOTS[@]}") ;;
  user)    ROOTS=("${USER_ROOTS[@]}") ;;
  all)     ROOTS=("${PROJECT_ROOTS[@]}" "${USER_ROOTS[@]}") ;;
  *)       echo "bad --scope: $SCOPE" >&2; exit 2 ;;
esac
# Prune non-existent roots so rg does not error on them
EXISTING=()
for r in "${ROOTS[@]}"; do [ -e "$r" ] && EXISTING+=("$r"); done
```

A missing root is not an error — it is an empty scope contribution. Fresh
repos have no `.claude/agent-memory/`; that is normal.

### Step 3: Choose search engine

```bash
if command -v rg >/dev/null 2>&1; then
  ENGINE=rg
else
  ENGINE=grep
fi
```

Record the engine choice — include it in the JSON output so downstream
tooling can audit which engine ran.

### Step 4: Execute search

With `rg`:

```bash
rg $CASE_FLAG $FIXED_FLAG \
   --type-add 'mem:*.{md,yaml,yml,json}' --type mem \
   --no-messages --line-number --with-filename \
   -m "$LIMIT" "$PATTERN" "${EXISTING[@]}"
```

With `grep` fallback:

```bash
grep -rEn --include='*.md' --include='*.yaml' --include='*.yml' \
     --include='*.json' --color=never \
     $CASE_FLAG $FIXED_FLAG "$PATTERN" "${EXISTING[@]}" \
     | head -n "$LIMIT"
```

`rg -m N` caps matches per-file. For a global cap, post-filter with
`head -n $LIMIT` after combining file-level caps — document whichever
semantic the implementation ships with so downstream callers are not
surprised.

### Step 5: Tag each hit with its memory layer

For every hit line `<path>:<line>:<excerpt>`, classify by path prefix:

| Path contains | Layer tag |
|---------------|-----------|
| `CLAUDE.md` or `CLAUDE.local.md` | `claude_md` |
| `.claude/rules/` | `rules` |
| `.claude/agent-memory/` | `agent_memory_project` |
| `.claude/instincts/` or `~/.claude/instincts/` | `instincts` |
| `~/.claude/agent-memory/` | `agent_memory_user` |
| `~/.claude/projects/.../memory/` | `auto_memory` |
| anything else (should not happen if roots are correct) | `other` |

The layer tag is included in every output row — it is the fastest way for a
caller to filter results without re-parsing the path.

### Step 6: Emit results

`--format text` (default, human-readable):

```
rg (engine) — pattern: 'retry backoff' — scope: all — 4 matches

[rules]                .claude/rules/common.md:14
    retry-backoff policy: exponential with jitter, cap 30s

[agent_memory_project] .claude/agent-memory/memory-curator/feedback_retries.md:3
    we prefer retry backoff over fixed delay to avoid thundering herds

[auto_memory]          ~/.claude/projects/abc123/memory/MEMORY.md:22
    - [retry-policy](project_retries.md) — retry backoff decisions

[claude_md]            CLAUDE.md:47
    See .claude/rules/retries.md for retry-backoff conventions.
```

`--format json` (machine-readable, suitable for piping into other skills):

```json
{
  "engine": "rg",
  "pattern": "retry backoff",
  "scope": "all",
  "limit": 25,
  "count": 4,
  "results": [
    {"layer": "rules", "path": ".claude/rules/common.md", "line": 14,
     "excerpt": "retry-backoff policy: exponential with jitter, cap 30s"}
  ]
}
```

If there are zero matches, the text output is `(no matches)` and the JSON
output is `{"engine":"...","pattern":"...","scope":"...","count":0,
"results":[]}`. Never emit an empty response — a downstream parser needs a
deterministic shape.

## Output Checklist

Before returning to the user, verify:

- [ ] PATTERN was non-empty; usage error was printed otherwise.
- [ ] At least one root existed (even if zero matches).
- [ ] The engine choice (`rg` or `grep`) appears in the header or JSON.
- [ ] Every result has a `layer` tag from the Step-5 table.
- [ ] The number of results is `<= --limit`.
- [ ] No files were modified — this skill is read-only.

## Examples

### Example 1: Project-scope search for a term

```
User: /memory-search "retry backoff" --scope project
Assistant: rg (engine) — pattern: 'retry backoff' — scope: project — 2 matches

           [rules]                .claude/rules/common.md:14
               retry-backoff policy: exponential with jitter, cap 30s

           [agent_memory_project] .claude/agent-memory/memory-curator/feedback_retries.md:3
               we prefer retry backoff over fixed delay to avoid thundering herds
```

### Example 2: JSON output for tooling

```
User: /memory-search "OAuth" --format json --limit 5
Assistant: {"engine":"rg","pattern":"OAuth","scope":"all","limit":5,"count":1,
           "results":[{"layer":"auto_memory",
                       "path":"/home/michael/.claude/projects/abc/memory/MEMORY.md",
                       "line":8,
                       "excerpt":"- [oauth-decisions](project_auth.md) — OAuth token flow"}]}
```

### Example 3: Fallback to grep

```
User: /memory-search "TODO" --scope user
Assistant: grep (engine, rg not installed) — pattern: 'TODO' — scope: user — 3 matches
           ...
```

### Example 4: No matches

```
User: /memory-search "nonexistent phrase"
Assistant: rg (engine) — pattern: 'nonexistent phrase' — scope: all — 0 matches
           (no matches)
```

## Gotchas

| Problem | Cause | Mitigation |
|---------|-------|------------|
| Search silently returns zero results on a fresh repo | `.claude/agent-memory/` does not exist yet | Step 2 prunes missing roots — this is correct, but the header should still print `engine` / `pattern` / `scope` so the caller sees what ran |
| Regex metacharacters break PATTERN | User meant a literal string | Pass `--fixed-strings` (becomes `rg -F` / `grep -F`) |
| Auto-memory path contains the Claude-Code-internal hash | Cannot predict the hash | Search `~/.claude/projects/` recursively and tag hits as `auto_memory` by their path segment, not by hash |
| `--limit` appears to apply per-file only | `rg -m N` is per-file | Document the semantic explicitly and post-filter with `head -n N` if a global cap is desired |
| Results include secrets from CLAUDE.local.md | `CLAUDE.local.md` is gitignored but still on disk | Scoping is honest — CLAUDE.local.md is a project-scope root. Users who want a sanitised search should pass `--scope user` or add an exclusion flag in a future version |
| Case-sensitive match fails with ASCII curly quotes | PATTERN contained a smart quote from a doc paste | Normalize PATTERN or document this limitation — do not silently strip characters |

<!-- managed by platxa-skill-generator -->
