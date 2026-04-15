# CLAUDE.md

> **TODO(platxa-memory): skeleton template** — every `TODO:` placeholder
> below must be replaced before the first agent session reads this file.
> Search for `TODO:` to find them. Delete this blockquote when the last
> placeholder is gone.
>
> Copy into your project root, then uncomment the `@import` line that
> matches your stack. Claude Code expands `@path/file.md` inline when it
> reads this file. `AGENTS.md` ships alongside and re-imports this file,
> so fill in the content here once and both agent entrypoints stay in
> sync.

## Project

TODO: One paragraph — what this project does, for whom, and what problem
it solves. Avoid marketing copy; describe the actual system.

## Stack

TODO: Pick one — `python`, `typescript`, `go`, `rust`, `java`, `ruby`,
or `monorepo`. Language-specific conventions live in the imported rule
files below.

## Rules (path-scoped)

Uncomment the line that matches your stack. Each import pulls in a
separate rule file, so Claude only pays the context cost for the stacks
you use.

<!-- @.claude/rules/python-style.md -->
<!-- @.claude/rules/python-testing.md -->

<!-- @.claude/rules/typescript-style.md -->
<!-- @.claude/rules/typescript-testing.md -->

<!-- @.claude/rules/go-style.md -->
<!-- @.claude/rules/go-testing.md -->

<!-- @.claude/rules/rust-style.md -->
<!-- @.claude/rules/rust-testing.md -->

<!-- @.claude/rules/java-style.md -->
<!-- @.claude/rules/java-testing.md -->

<!-- @.claude/rules/ruby-style.md -->
<!-- @.claude/rules/ruby-testing.md -->

<!-- @.claude/rules/monorepo-workspaces.md -->
<!-- @.claude/rules/monorepo-cross-package.md -->

## Development

### Setup

```bash
# TODO: replace with your install command
# e.g. pnpm install, pip install -e ., go mod download
```

### Run

```bash
# TODO: replace with your run command
# e.g. pnpm dev, python -m app, go run ./cmd/app
```

### Test

```bash
# TODO: replace with your test command
# e.g. pytest, vitest, go test ./...
```

### Lint / format

```bash
# TODO: replace with your lint + format commands
# e.g. ruff check && ruff format, eslint && prettier, golangci-lint run && gofmt -w .
```

## Architecture

TODO: Short map of the codebase (10–20 lines). Name the top-level
directories and what lives in each. Call out any non-obvious module
boundaries, data flows, or ownership splits.

### Key directories

- `src/` — TODO: what goes here
- `tests/` — TODO: what goes here

## Conventions

TODO: Project-specific conventions that aren't covered by the stack rules:

- naming patterns unique to this codebase
- commit message format (e.g. Conventional Commits)
- branching strategy (trunk-based? gitflow?)
- review workflow (who approves what)

## Memory

This project uses the [platxa-memory](https://github.com/platxa/platxa-memory)
plugin for cross-session memory.

- `platxa-memory health` — inspect memory state
- `platxa-memory search <pattern>` — search memory files
- `platxa-memory detect-stack` — confirm the detected stack

Auto-memory lives under `~/.claude/projects/<hashed>/memory/` and is
hydrated at session start by the platxa-memory `SessionStart` hook.

## Common tasks

TODO (optional): repeated workflows worth documenting:

- "How do I add a new `<thing>`?"
- "How do I run the integration tests locally?"
- "Where is the staging env configured?"

## Non-goals

TODO: Things this project deliberately does NOT do. Explicit non-goals
are the cheapest way to stop scope creep in agent-assisted work.

## References

- TODO: link to the architecture doc, ADR index, or design overview
- TODO: link to the deployment runbook
- TODO: link to the on-call rotation or incident history

<!-- Keep this file under 200 lines. Rules go in @.claude/rules/*.md;
     long-form design docs go in docs/ and are linked above. -->
