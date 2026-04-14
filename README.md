# platxa-memory

Production-grade Claude Code memory plugin. Native Claude Code primitives only — no SDK, no API, no LLM calls in plugin code.

## What it is

`platxa-memory` is a focused Claude Code plugin that ships the memory layer for any project:

- Memory-enabled subagents (curator, synthesizer, auditor, researcher, migrator, doctor)
- Bootstrap skills (`/memory-init`, `/memory-status`, `/memory-doctor`, `/memory-health`, `/memory-search`, `/memory-export`, `/memory-import`, `/memory-prune`, `/memory-restore`, `/memory-architecture`)
- Lifecycle hooks (SessionStart, PreCompact, PostCompact, InstructionsLoaded, CwdChanged, Stop, SubagentStop, PreToolUse, FileChanged)
- Language-profile templates (Python, TypeScript, Go, Rust, Java, Ruby, monorepo)
- CLI at `bin/platxa-memory` for non-interactive access

## Installation

```bash
# Add the platxa marketplace
/plugin marketplace add platxa/plugins

# Install platxa-memory
/plugin install platxa-memory@platxa-plugins
```

## Quickstart

In any project, run:

```
/memory-init
```

The skill detects the project stack, instantiates path-scoped rules under `.claude/rules/`, scaffolds a project `CLAUDE.md`, creates seeded `MEMORY.md` templates under `.claude/agent-memory/`, and adds `CLAUDE.local.md` to `.gitignore`.

## Architecture

See [docs/memory-architecture.md](docs/memory-architecture.md) for the layered memory model, loading order, `/compact` survival matrix, and per-project routing via `CLAUDE_PROJECT_DIR`.

Five memory layers, all native Claude Code:

1. **CLAUDE.md hierarchy** — project + user + local instructions
2. **`.claude/rules/`** — path-scoped rules with `paths:` frontmatter
3. **Auto memory** — `~/.claude/projects/<hash>/memory/MEMORY.md` + topic files
4. **Agent memory** — `memory: project|user|local` frontmatter on agent definitions
5. **Instincts** — learned behavioral patterns with confidence scores

## Relationship to platxa-code-agent

| Plugin | Responsibility |
|--------|----------------|
| **platxa-code-agent** | Spec-driven development loop, code agents, review pipeline |
| **platxa-memory** | Cross-session memory, context injection, compaction survival |

Both ship in the same `platxa-plugins` marketplace and can be installed independently.

## Constraints

This plugin uses only native Claude Code primitives:

- No Anthropic SDK
- No Anthropic API calls
- No third-party LLM calls
- Hook types limited to `command` and `http` (never `prompt` or `agent`)

All dynamic context is produced by shell substitution (`` !`command` ``) or deterministic Python scripts.

## License

[MIT](LICENSE)
