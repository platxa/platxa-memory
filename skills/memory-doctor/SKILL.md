---
name: memory-doctor
description: >-
  Use when the user asks to "diagnose memory", "check memory health", "run
  memory doctor", "/memory-doctor", or is investigating context bloat before
  a compaction. Diagnoses the project memory layout by running the
  memory-doctor agent in a forked context, then surfaces only the final
  findings to the main conversation. Reports issues like oversized
  MEMORY.md, orphan topic files, broken index pointers, duplicated facts,
  low-confidence instincts, and gitignore drift. Returns a concise issues
  summary plus concrete fix commands (e.g. /memory-prune, /memory-init
  --stack STACK) — never mutates state directly.
user-invocable: true
disable-model-invocation: true
allowed-tools:
  - Read
  - Bash
  - Task
  - Glob
  - Grep
metadata:
  version: "1.0.0"
  author: "DJ Patel"
  tags:
    - memory
    - diagnostics
    - read-only
    - context-isolation
---

# Memory Doctor — Forked Memory Diagnostics

Run the `memory-doctor` agent in an isolated context so its internal scratch
reasoning never pollutes the main conversation, and surface only the final
issues-and-fixes report to the user. The skill itself proposes fixes but
never runs them — every mutation is explicit, commanded by the user after
they review the report.

## Overview

Memory hygiene degrades slowly. A typical failure mode: MEMORY.md grows past
the 200-line injection cap, topic files become orphaned when refactors rename
files, duplicate facts accumulate across agent directories, and the gitignore
silently falls out of sync with the scaffolding. Each issue is small in
isolation; together they silently inflate the session's context budget and
degrade recall precision.

This skill is the triage tool. It dispatches the `memory-doctor` agent (a
haiku-class, `memory: local` diagnostic specialist — ships as feature #10 of
the platxa-memory plugin) via the Task tool, which gives the agent its own
context window. The agent inspects the project's memory footprint, produces
a structured findings record, and hands control back to this skill. The skill
reformats the record into a compact summary plus a numbered list of fix
commands the user can copy-paste.

## Isolation contract

The central design constraint: **forked-agent reasoning must not leak**.

1. The `memory-doctor` agent is dispatched via the `Task` tool. Task gives
   the sub-agent its own context window by design — this is the native
   Claude Code "context: fork" mechanism. The skill never reads the
   sub-agent's intermediate tool calls.
2. The sub-agent MUST return a single structured payload (see "Expected
   agent payload" below). Free-form reasoning from inside the sub-agent is
   discarded.
3. The main conversation sees only the final report this skill produces.
   No raw agent transcript, no intermediate file reads, no scratch notes.
4. The skill is itself read-only: `allowed-tools` is `Read, Bash, Task,
   Glob, Grep`. Write, Edit, WebFetch are absent — structural enforcement
   of "propose fixes, never apply them."

If a reader changes `allowed-tools` to include Write or Edit, they are
breaking the isolation contract and should revisit this decision.

## Process

Copy this checklist and tick each step:

```
Progress:
- [ ] Step 1: Preflight — verify memory-doctor agent is installed
- [ ] Step 2: Dispatch the forked memory-doctor agent
- [ ] Step 3: Parse the structured payload
- [ ] Step 4: Render issues summary
- [ ] Step 5: Render fix commands
- [ ] Step 6: Emit the final report
```

### Step 1: Preflight — agent availability

The `memory-doctor` agent is defined in `agents/memory-doctor.md` (shipped
as feature #10 of platxa-memory). Before dispatching, verify it exists. If
missing, emit the graceful-degradation message and exit with code 0 — a
user who has partially installed the plugin should see a clear "ship
feature #10 first" rather than an opaque Task failure.

```bash
# Check for the agent definition in any agents/ directory on the load path
if ! find agents ~/.claude/agents -type f -name 'memory-doctor.md' 2>/dev/null | grep -q .; then
  cat <<'MSG'
memory-doctor agent not yet installed.

This skill dispatches the memory-doctor agent (platxa-memory feature #10)
to produce its diagnostics. The agent definition is missing from:
  - ./agents/memory-doctor.md
  - ~/.claude/agents/memory-doctor.md

Ship feature #10 first (agents/memory-doctor.md), then re-run /memory-doctor.
MSG
  exit 0
fi
```

### Step 2: Dispatch the forked memory-doctor agent

Use the Task tool with `subagent_type: memory-doctor` (or the fully-qualified
`platxa-memory:memory-doctor` when the plugin is namespaced). The prompt
must ask for a structured JSON payload so parsing in Step 3 is deterministic.

Dispatch prompt template:

```text
Diagnose the memory layout for the project at {{CWD}}. Scan:
  - CLAUDE.md hierarchy (project + user + local + managed policy)
  - .claude/rules/**/*.md
  - auto memory at ~/.claude/projects/**/memory/
  - agent memory at .claude/agent-memory/** and ~/.claude/agent-memory/**
  - instincts at .claude/instincts/** and ~/.claude/instincts/**
  - .gitignore entries required by /memory-init

Return ONLY a fenced JSON block with this schema (no prose preamble,
no closing summary):

```json
{
  "scanned": {
    "claude_md": 0,
    "rules": 0,
    "auto_memory_files": 0,
    "agent_memory_dirs": 0,
    "instincts": 0,
    "gitignore_entries": 0
  },
  "issues": [
    {"severity": "high",
     "layer": "claude_md",
     "path": "relative path or dir",
     "problem": "one-line description",
     "evidence": "file:line or short quote"}
  ],
  "fix_commands": [
    {"order": 1, "command": "/memory-prune", "reason": "why this helps"}
  ]
}
```

Required fields:
- `scanned`: all six integer counters must be present (emit 0 when absent).
- `issues[].severity`: lowercase, one of exactly `high`, `medium`, `low`.
  Any other value is a schema violation — the skill will reject the payload.
- `issues[].layer`: lowercase, one of exactly `claude_md`, `rules`,
  `auto_memory`, `agent_memory`, `instincts`, `gitignore`.

Do NOT write any files. Do NOT attempt fixes yourself — the orchestrator
expects you to propose, not mutate.
```

Rationale: the agent is `memory: local` (machine-local, gitignored) so its
running notes never reach the repo. The fenced-JSON response is a strict
contract that survives the context boundary — free-form prose is dropped.

### Step 3: Parse the structured payload

Extract the JSON block from the agent response. If the agent misbehaves and
returns malformed JSON, report a clear parse failure with the offending
snippet and exit — do not silently fall back to free-form output.

```bash
# Conceptual — the skill's executor implements this via Read/Bash:
# 1. Locate the first ```json ... ``` fence in the agent reply.
# 2. Parse with `python3 -c 'import json,sys; json.load(sys.stdin)'`.
# 3. On parse failure: print the bad snippet and exit 1.
```

Validate the schema shape: `scanned` (object with 6 integer counters),
`issues` (array), and `fix_commands` (array) are all required. Missing any
of them → report-and-exit. Empty `issues`/`fix_commands` arrays are legal
and mean "memory looks healthy."

Additionally, reject any `issues[].severity` outside the exact enum
`{"high","medium","low"}` and any `issues[].layer` outside
`{"claude_md","rules","auto_memory","agent_memory","instincts","gitignore"}`.
Silently bucketing unknown enum values would lose data — fail loudly instead.

### Step 4: Render issues summary

Group issues by severity. Within each severity, group by layer. Render as:

```
## Issues

### HIGH (N)
- [<layer>] <path>: <problem>
  Evidence: <file:line or short quote>

### MEDIUM (N)
- ...

### LOW (N)
- ...
```

If an array is empty, render `(none)` for that severity rather than omitting
the heading — a stable report schema helps downstream parsers.

### Step 5: Render fix commands

Render `fix_commands` as a numbered list. Each entry shows the exact
command and the reason. This list is the action surface; users pick which
to run.

```
## Suggested fixes
1. `/memory-prune`
   Reason: <agent's reason>
2. `Edit .gitignore` — append `CLAUDE.local.md`
   Reason: required by /memory-init, currently missing
```

Rule: never execute any command from this list automatically. This skill
proposes, user disposes.

### Step 6: Emit the final report

The report structure is a stable schema — downstream parsers depend on
every section appearing in the same order every run. Do NOT collapse empty
sections; use `(none)` / `(no action required)` placeholders so the schema
never changes shape.

Populate `Scanned:` directly from the `scanned` object in the agent
payload. Render all six counters even when zero.

```
# Memory Doctor Report — 2026-04-15 14:02 UTC

Forked agent: memory-doctor  (memory: local, isolated context)
Scanned: 3 CLAUDE.md files, 2 rules, 4 auto-memory files,
         6 agent-memory dirs, 0 instincts, 3 gitignore entries

## Issues
(rendered from Step 4 — always renders all three severity subheadings)

## Suggested fixes
(rendered from Step 5 — render `(no action required)` if fix_commands
is empty; do not omit the section)

---
Read-only: no files were modified. Run fixes individually after review.
```

When the report has zero findings across all severities, render a one-line
banner `_All clear — memory layout is healthy._` immediately below the
`## Issues` heading, then continue with the three severity subheadings
(each reading `(none)`). The banner is additive — it complements the
stable schema, never replaces it.

## Options

| Flag | Effect |
|------|--------|
| `--json` | Emit the agent's structured payload verbatim (useful for scripting) |
| `--severity <high\|medium\|low>` | Filter the issues list to a minimum severity |
| `--no-fixes` | Report issues only; omit the Suggested fixes section |

## Examples

### Example 1: Healthy project

```
User: /memory-doctor
Assistant: # Memory Doctor Report — 2026-04-15 14:02 UTC
           Forked agent: memory-doctor  (memory: local, isolated context)
           Scanned: 2 CLAUDE.md files, 2 rules, 0 auto-memory files,
                    0 agent-memory dirs, 0 instincts, 3 gitignore entries

           ## Issues
           _All clear — memory layout is healthy._

           ### HIGH (0)
           (none)

           ### MEDIUM (0)
           (none)

           ### LOW (0)
           (none)

           ## Suggested fixes
           (no action required)

           Read-only: no files were modified.
```

### Example 2: Drifted project

```
User: /memory-doctor
Assistant: # Memory Doctor Report — 2026-04-20 09:15 UTC
           Forked agent: memory-doctor  (memory: local, isolated context)
           Scanned: 4 CLAUDE.md files, 3 rules, 12 auto-memory files,
                    6 agent-memory dirs, 2 instincts, 3 gitignore entries

           ## Issues
           ### HIGH (2)
           - [claude_md] CLAUDE.md: exceeds 200-line injection cap (412 lines)
             Evidence: CLAUDE.md:412
           - [gitignore] .gitignore: missing 'CLAUDE.local.md' entry
             Evidence: /memory-init expects this line

           ### MEDIUM (1)
           - [agent_memory] memory-curator/: 2 orphan topic files
             Evidence: feedback_old_api.md not indexed in MEMORY.md

           ### LOW (0)
           (none)

           ## Suggested fixes
           1. `Edit CLAUDE.md` — split into topic files; target ≤ 200 lines
              Reason: auto-injection cap triggers silent truncation above 200 lines
           2. `/memory-init`  — re-run to append required .gitignore entries
              Reason: idempotent; only adds missing lines
           3. `Invoke memory-curator agent`  — index or remove orphans
              Reason: orphan topic files waste retrieval budget
```

### Example 3: Agent not installed

```
User: /memory-doctor
Assistant: memory-doctor agent not yet installed.

           This skill dispatches the memory-doctor agent (platxa-memory
           feature #10) to produce its diagnostics. The agent definition
           is missing from:
             - ./agents/memory-doctor.md
             - ~/.claude/agents/memory-doctor.md

           Ship feature #10 first (agents/memory-doctor.md), then re-run
           /memory-doctor.
```

## Output Checklist

Before returning to the user, verify:

- [ ] Preflight succeeded OR emitted the graceful-degradation message.
- [ ] If dispatched: the Task tool was used exactly once with
      `subagent_type: memory-doctor`.
- [ ] The agent's response was parsed as JSON; malformed JSON produced a
      parse-failure report rather than silent fallback.
- [ ] The `Issues` section has all three severity subheadings (HIGH,
      MEDIUM, LOW), even if some are `(none)`.
- [ ] The `Suggested fixes` section lists commands verbatim; no shell was
      executed.
- [ ] No files were written or modified by this skill (read-only contract).
- [ ] The main conversation received only the final report — no raw agent
      transcript leaked.

## Gotchas

| Problem | Cause | Mitigation |
|---------|-------|------------|
| Skill silently hangs | `memory-doctor` agent has `maxTurns` set too low and times out without returning JSON | Set a reasonable `maxTurns` (>= 10) in the agent definition; the skill should surface "agent timed out" rather than hanging |
| Fixes applied to main context | Someone added Write/Edit to `allowed-tools` | Revert. The isolation contract (Section "Isolation contract") is what distinguishes this skill from `/memory-prune` |
| JSON parse fails | Agent emitted prose before the fenced block | The dispatch prompt forbids preambles; if it still happens, tighten the agent's system prompt (fix lives in feature #10, not here) |
| Sub-agent leaks scratch reasoning | Skill reads the raw Task output instead of parsing the JSON | Always parse the JSON payload; never dump the raw agent response to the main conversation |
| Report omits a severity heading | Skill used `if len(issues) > 0` before rendering a subheading | Always render all three severity subheadings; use `(none)` for empty |
| User runs `/memory-doctor` expecting it to fix things | Misread the skill as `/memory-prune` | The opening paragraph explicitly states "never mutates state." If users still confuse them, add a one-line banner "(read-only — proposes fixes)" at report top |

<!-- managed by platxa-skill-generator -->
