# Memory architecture

`platxa-memory` layers five mechanisms into a single coherent memory stack,
using only native Claude Code primitives — no Anthropic SDK calls, no LLM
invocations from plugin code, hook types restricted to `command` and
`http`. This document explains what each layer stores, when it loads, how
the layers compose at session start, and what survives a `/compact`.

## The five layers

```
                        ┌─────────────────────────────────────┐
                        │  5. Instincts                       │   global + project
                        │     confidence-scored patterns      │   ~/.claude/instincts/
                        └─────────────────────────────────────┘   .claude/instincts/
                                        ▲
                        ┌───────────────┴─────────────────────┐
                        │  4. Agent memory                    │   per-agent
                        │     memory: frontmatter on *.md     │   agents/*.md
                        └─────────────────────────────────────┘
                                        ▲
                        ┌───────────────┴─────────────────────┐
                        │  3. Auto memory                     │   per-project (keyed)
                        │     MEMORY.md + topic *.md          │   ~/.claude/projects/
                        └─────────────────────────────────────┘       <key>/memory/
                                        ▲
                        ┌───────────────┴─────────────────────┐
                        │  2. Path-scoped rules               │   repo-local
                        │     YAML frontmatter paths:         │   .claude/rules/*.md
                        └─────────────────────────────────────┘
                                        ▲
                        ┌───────────────┴─────────────────────┐
                        │  1. CLAUDE.md hierarchy             │   repo + user
                        │     project + user + local          │   CLAUDE.md, ~/.claude/
                        └─────────────────────────────────────┘   CLAUDE.md
```

### 1. CLAUDE.md hierarchy

Claude Code reads `CLAUDE.md`, `CLAUDE.local.md`, and `~/.claude/CLAUDE.md`
at session start. Project-level `CLAUDE.md` carries agent instructions that
apply to every session in the repo; `CLAUDE.local.md` is a git-ignored
override for one developer; `~/.claude/CLAUDE.md` is global. Templates for
this layer ship at `templates/CLAUDE.md` (skeleton) and `templates/AGENTS.md`
(compat shim for tools that look for `AGENTS.md` instead).

### 2. Path-scoped rules

Rule files under `.claude/rules/*.md` carry YAML frontmatter with a
`paths:` list of globs. Claude Code injects a rule body only when a file
matching one of its globs is touched, so the per-rule context cost is paid
on demand rather than up front. Seven drop-in stack profiles live at
`templates/<stack>/.claude/rules/` for Python, TypeScript, Go, Rust, Java,
Ruby, and monorepo.

### 3. Auto memory

Claude Code maintains a per-project auto-memory directory at
`~/.claude/projects/<key>/memory/`, containing a `MEMORY.md` index and
any number of topic files (`*.md`). The index is the truth; topic files
hold the long-form content. The repo's `CLAUDE.md` contains the auto-memory
contract: every memory write is either an update to an existing topic file
or a new topic plus a one-line pointer in `MEMORY.md`. No topic file
exceeds 200 lines — `memory-synthesizer` (see layer 4) enforces that cap.

### 4. Agent memory

Subagent definitions under `agents/*.md` carry a `memory:` frontmatter
field with one of three values:

- `memory: project` — dispatch reads `.claude/agent-memory/<agent-name>/`.
- `memory: user` — dispatch reads `~/.claude/agent-memory/<agent-name>/`.
- `memory: local` — in-session scratchpad; cleared between sessions.

The four memory agents shipped by this plugin all declare `memory:
project`:

- `agents/memory-curator.md` — prunes and reconciles topic files.
- `agents/memory-synthesizer.md` — writes session insights at Stop time.
- `agents/memory-researcher.md` — answers questions against the stored
  memory set without mutating it.
- `agents/memory-auditor.md` — looks for drift, duplicate topics, dead
  references.

### 5. Instincts

`.claude/instincts/` (project) and `~/.claude/instincts/` (user) hold
learned behavioural patterns — YAML / JSON blobs with a confidence score
and a pattern description. Unlike the other layers, instinct *bodies* are
never auto-injected. The `SessionStart` hook injects only the file index
so Claude knows they exist; the curator and synthesizer can read a body
on demand when confidence is high.

## Loading order

At session start the `SessionStart` hook (`hooks/session_start_hook.py`)
runs once and emits a single `additionalContext` blob containing:

```
1. [platxa-memory] banner — detected stack, resolved auto-memory dir,
   token budget breakdown
2. MEMORY.md contents (budgeted)
3. Every topic file under the auto-memory dir (budgeted)
4. Instincts file index (no bodies)
```

Layers 1 (CLAUDE.md) and 2 (rules) are handled by Claude Code itself:
`CLAUDE.md` loads unconditionally; rules load lazily when a matching file
path is read. Layer 4 (agent memory) only materialises when that specific
agent is dispatched.

The token budget defaults to **25 000 tokens** and is capped between
**500** (hard minimum) and **200 000** (hard maximum). Override with
`PLATXA_MEMORY_TOKEN_BUDGET`.

## `/compact` survival matrix

The `/compact` command drops the conversation buffer. Claude Code fires
`PreCompact` then `PostCompact` hooks around the drop; this plugin
implements both.

| Layer                    | Before `/compact`                | Survives compact? | After `/compact`                                                             |
|--------------------------|----------------------------------|-------------------|------------------------------------------------------------------------------|
| 1. CLAUDE.md hierarchy   | In context (inline)              | No                | Re-read natively by Claude Code from `CLAUDE.md` / `CLAUDE.local.md` / `~/.claude/CLAUDE.md` (no platxa-memory action) |
| 2. Path-scoped rules     | In context (if recently matched) | No                | `PostCompact` re-injects every `.claude/rules/*.md` body in full             |
| 3. Auto memory           | In context (from `SessionStart`) | No                | `PostCompact` re-injects `MEMORY.md` and all sibling topic files             |
| 4. Agent memory          | In the agent's own context       | N/A (not in main-agent context) | Re-read from the agent's memory dir the next time the agent is dispatched |
| 5. Instincts             | Index only (from `SessionStart`) | No                | Not re-injected by `PostCompact` (budget pressure; bodies re-hydrate on the next `SessionStart`) |

`PreCompact` (`hooks/pre_compact_hook.py`) **blocks** the compact when the
progress log has unsaved per-feature insights — any feature whose most
recent entry in `.claude/claude-progress.txt` is not `PASSED`, `FAILED`,
or `SKIPPED`. Set `PLATXA_MEMORY_PRECOMPACT_OVERRIDE=1` to bypass. This
makes `/compact` safe by default: you can't lose the only durable record
of work in progress.

`PostCompact` (`hooks/post_compact_hook.py`) splits its budget 60 / 40
between auto-memory and rules (memory is usually larger; rules are
non-negotiable after a compact). Both layers are re-injected in full,
respecting the same `PLATXA_MEMORY_TOKEN_BUDGET`.

### Stop-hook synthesis

`hooks/stop_hook.py` fires when Claude Code is about to stop. On the first
Stop in a session it returns a `block` decision instructing Claude to
dispatch the `memory-synthesizer` agent with a progress-log digest, so
durable insights land in the auto-memory dir before the session ends. A
per-session marker file under `.claude/.memory-synthesized-<session_id>`
and the `stop_hook_active` payload flag together guarantee synthesis runs
exactly once per session. `hooks/pretool_stop_guard.py` writes the same
marker when the main model dispatches `memory-synthesizer` proactively, so
the Stop hook doesn't re-dispatch after the fact.

Opt out with `PLATXA_MEMORY_STOP_SYNTH_DISABLE=1`.

### User-facing skills

Four skills sit on top of the hook + agent layer, each invokable from the
Claude Code chat bar:

- `memory-init` — bootstrap a new project's memory layout.
- `memory-status` — print a five-layer inventory of the current session.
- `memory-search` — ripgrep-backed full-text search across every memory
  file the plugin tracks.
- `memory-doctor` — diagnose common failure modes (missing dirs, stale
  markers, rule drift).

## Per-project routing

The plugin resolves which project a session belongs to from three
signals, in order of precedence:

1. `CLAUDE_PROJECT_DIR` environment variable — if set, treated as
   authoritative.
2. `PLATXA_MEMORY_AUTO_DIR` environment variable — an explicit override
   for the auto-memory directory only (useful for testing and CI).
3. Working-directory fallback. The CLI at `bin/platxa-memory` also
   accepts `--project <dir>` and `--auto-dir <dir>` on every subcommand.

Claude Code derives an opaque directory key from the project path (a
slugified form today, though the exact scheme is treated as an
implementation detail) and stores auto-memory under
`~/.claude/projects/<key>/`. External processes (hooks, CLI, tests)
cannot reconstruct that key reliably, so the plugin falls back to a
**most-recent-mtime** heuristic: of every `~/.claude/projects/*/memory/`
directory, pick the most recently modified. This works reliably for
single-user machines and gracefully degrades to "nearest recent session"
in shared environments. Users who need deterministic routing should
export `PLATXA_MEMORY_AUTO_DIR`.

## Graceful degradation

Every hook in this plugin follows the same rule: **a hook must never
crash the session**. The outer `main()` of every hook (SessionStart,
PreCompact, PostCompact, Stop, PreToolUse guard) wraps its work in a
`try: ... except Exception:` block that emits a benign envelope and
exits 0 on any failure. The `PreCompact` block case is deliberate (it
exits 2 when there are unsaved insights and the override is not set),
but every other hook degrades to "no-op and allow".

## Where each piece lives

| Concern                                | File                                                     |
|----------------------------------------|----------------------------------------------------------|
| Session-start context injection        | `hooks/session_start_hook.py`                            |
| PreCompact save-first guard            | `hooks/pre_compact_hook.py`                              |
| PostCompact re-hydration               | `hooks/post_compact_hook.py`                             |
| Stop-time synthesis trigger            | `hooks/stop_hook.py`                                     |
| PreToolUse loop guard                  | `hooks/pretool_stop_guard.py`                            |
| Memory subagents                       | `agents/memory-{curator,synthesizer,researcher,auditor}.md` |
| User-facing skills                     | `skills/memory-{init,status,search,doctor}/SKILL.md`     |
| Non-interactive CLI                    | `bin/platxa-memory`                                      |
| Stack detector library                 | `src/platxa_memory/stack.py`                             |
| Atomic durable writes                  | `src/platxa_memory/atomic.py`                            |
| Drop-in CLAUDE.md / AGENTS.md skeleton | `templates/CLAUDE.md`, `templates/AGENTS.md`             |
| Stack-specific rule bundles            | `templates/<stack>/.claude/rules/*.md`                   |

## References

- Repo `CLAUDE.md` — hard constraints and architecture boundary with
  `platxa-code-agent`.
- `README.md` — quickstart and plugin install instructions.
- `CHANGELOG.md` — release notes per Keep-a-Changelog.
