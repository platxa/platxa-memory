# platxa-memory

Production-grade cross-session memory for Claude Code. Stdlib-only, no
Anthropic SDK, no LLM calls from plugin code.

## What it is

`platxa-memory` is a Claude Code plugin that adds durable memory to any
project. A session ends, the context window compacts, the machine
reboots — when the next session starts, the plugin has already
re-hydrated the facts, rules, and decisions that matter.

It ships:

- **Lifecycle hooks** — `SessionStart` (inject memory + rules),
  `PreCompact` (block `/compact` with unsaved insights), `PostCompact`
  (re-inject after compact), `Stop` + `PreToolUse` guard (dispatch a
  synthesizer agent exactly once per session).
- **Memory subagents** — `memory-curator`, `memory-synthesizer`,
  `memory-researcher`, `memory-auditor`.
- **User-facing skills** — `/memory-init`, `/memory-status`,
  `/memory-search`, `/memory-doctor`.
- **Non-interactive CLI** at `bin/platxa-memory` with 8 subcommands
  (`detect-stack`, `health`, `search`, `export`, `import`, `prune`,
  `restore`, `migrate`).
- **Stack-profile templates** for Python, TypeScript, Go, Rust, Java,
  Ruby, and monorepo — drop-in `.claude/rules/*.md` bundles plus a
  `CLAUDE.md` / `AGENTS.md` skeleton pair.

## Installation

```bash
# 1. Add the platxa marketplace
/plugin marketplace add platxa/plugins

# 2. Install platxa-memory
/plugin install platxa-memory@platxa-plugins
```

When the plugin is enabled, Claude Code prepends `bin/` to your `PATH`,
so `platxa-memory --help` works from any shell.

## Quickstart

In any project, run:

```
/memory-init
```

The skill detects the project stack, copies the matching stack-profile
bundle into `.claude/rules/`, scaffolds `CLAUDE.md` + `AGENTS.md` from
the templates, and wires everything up so the next session picks it up
automatically.

After that, the memory system runs in the background:

```
/memory-status     # five-layer inventory of current state
/memory-search X   # ripgrep across every memory file
/memory-doctor     # diagnose missing dirs, stale markers, rule drift
```

## Core concepts

Five memory layers, all native Claude Code primitives:

1. **CLAUDE.md hierarchy** — project + user + local instructions.
2. **`.claude/rules/`** — path-scoped rules with a `paths:` frontmatter
   glob list; rule bodies load only when a matching file is touched.
3. **Auto memory** — Claude Code's per-project
   `~/.claude/projects/<key>/memory/` with a `MEMORY.md` index plus
   topic files, written by the synthesizer agent.
4. **Agent memory** — per-subagent memory via
   `memory: project|user|local` frontmatter on agent definitions.
5. **Instincts** — confidence-scored behavioural patterns under
   `.claude/instincts/` (index auto-injected; bodies on demand).

Full architecture — loading order, `/compact` survival matrix,
per-project routing via `CLAUDE_PROJECT_DIR`, and the 4-layer loop
prevention that makes the Stop hook fire-exactly-once per session — is
in [`docs/memory-architecture.md`](docs/memory-architecture.md).

## Configuration

| Env var                              | Effect                                                              |
|--------------------------------------|---------------------------------------------------------------------|
| `PLATXA_MEMORY_TOKEN_BUDGET`         | Context budget for SessionStart / PostCompact re-injection (default 25 000; range 500–200 000) |
| `PLATXA_MEMORY_AUTO_DIR`             | Explicit auto-memory directory override                             |
| `PLATXA_MEMORY_PRECOMPACT_OVERRIDE=1`| Allow `/compact` even with unsaved per-feature insights             |
| `PLATXA_MEMORY_STOP_SYNTH_DISABLE=1` | Skip the Stop-hook synthesizer dispatch                             |
| `CLAUDE_PROJECT_DIR`                 | Authoritative project root (precedence: this > AUTO_DIR > cwd)      |

## Relationship to platxa-code-agent

| Plugin                | Responsibility                                            |
|-----------------------|-----------------------------------------------------------|
| **platxa-code-agent** | Spec-driven development loop, code agents, review pipeline |
| **platxa-memory**     | Cross-session memory, context injection, compaction survival |

Both ship in the same `platxa-plugins` marketplace and install
independently. `platxa-code-agent` provides the spec workflow you use
to build features; `platxa-memory` preserves what each of those sessions
learned so the next one starts ahead. Neither depends on the other.

## Hard constraints

This plugin uses only native Claude Code primitives and Python stdlib:

- **No Anthropic SDK** in plugin code.
- **No Anthropic API calls** from hooks, skills, or subagents.
- **No third-party LLM calls.**
- **Hook types restricted to `command` and `http`** — never `prompt`
  or `agent`.
- **Dynamic context** comes from shell substitution (`` !`command` ``)
  or deterministic Python scripts.

These are documented in [`CLAUDE.md`](CLAUDE.md) and enforced by code
review.

## Repo layout

```
platxa-memory/
├── agents/              memory-{curator,synthesizer,researcher,auditor}.md
├── bin/                 platxa-memory         ← executable CLI
├── docs/                memory-architecture.md
├── hooks/               session_start_hook.py, pre_compact_hook.py,
│                        post_compact_hook.py, stop_hook.py,
│                        pretool_stop_guard.py
├── skills/              memory-{init,status,search,doctor}/SKILL.md
├── src/platxa_memory/   stack.py (detector), atomic.py (durable writes)
├── templates/           CLAUDE.md, AGENTS.md, {python,typescript,go,
│                        rust,java,ruby,monorepo}/.claude/rules/*.md
└── tests/               pytest suite covering every hook, skill,
                         template, and library module
```

## Status

Pre-`0.1.0`. Hooks, agents, skills, CLI, stack detector, atomic write
helper, and stack templates are shipped; see
[`CHANGELOG.md`](CHANGELOG.md) for the incremental history.

## License

[MIT](LICENSE)
