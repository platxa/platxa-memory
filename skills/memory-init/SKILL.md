---
name: memory-init
description: >-
  Bootstrap the Claude Code memory system in any project. Detects the primary
  stack (Python, TypeScript, Go, Rust), scaffolds CLAUDE.md, .claude/rules/,
  .claude/agent-memory/, and CLAUDE.local.md, and adds the required .gitignore
  entries. Idempotent: re-running on an initialized project produces a
  git-clean diff. Use when the user asks to "init memory", "bootstrap
  memory", "/memory-init", or is setting up a new repo for the platxa-memory
  plugin.
user-invocable: true
disable-model-invocation: true
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
metadata:
  version: "1.0.0"
  author: "DJ Patel"
  tags:
    - memory
    - bootstrap
    - scaffold
    - idempotent
---

# Memory Init — Bootstrap the platxa-memory layer

Create the on-disk memory scaffold for a fresh repo (or top up a partial one).
Runs only on explicit user invocation (`disable-model-invocation: true`); never
auto-fires because mutating the repo without consent is the wrong default.

## Overview

This skill bootstraps every file the platxa-memory plugin expects to find when
it attaches to a project: `CLAUDE.md` at the repo root, a `.claude/rules/`
directory with one stack-specific rule file plus a language-agnostic
`common.md`, a `.claude/agent-memory/` directory seeded with `MEMORY.md`, a
gitignored `CLAUDE.local.md`, and the corresponding `.gitignore` entries. It
detects the project's primary language (Python, TypeScript, Go, or Rust) to
pick the right rule template and falls back to a generic profile when no
marker is found. Every step guards against overwriting existing files so that
running the skill a second time on an already-initialized repo is a strict
no-op.

## Hard guarantees

1. **Idempotent.** Re-running on an initialized repo MUST produce
   `git status --short` output that is empty (no staged, no unstaged, no
   untracked from this skill). Step 6 verifies this.
2. **Non-destructive.** Existing files are never overwritten. Scaffolded
   content appears only in previously absent paths.
3. **Native primitives only.** No LLM calls, no SDK. All work is Bash + Read
   + Write + Edit.

## Process

Copy this checklist and tick each step as you go:

```
Progress:
- [ ] Step 1: Detect primary stack
- [ ] Step 2: Scaffold CLAUDE.md
- [ ] Step 3: Scaffold .claude/rules/
- [ ] Step 4: Scaffold .claude/agent-memory/
- [ ] Step 5: Scaffold CLAUDE.local.md + .gitignore entries
- [ ] Step 6: Verify idempotence
```

### Step 1: Detect primary stack

Probe for marker files in the repo root. Stop at the first match in this order
(a monorepo with multiple markers is treated as the language of the first hit
by convention; the user can override by passing `--stack <name>`).

| Stack | Marker files (any one triggers a hit) |
|-------|---------------------------------------|
| `python` | `pyproject.toml`, `setup.py`, `setup.cfg`, `requirements.txt` |
| `typescript` | `tsconfig.json`, `package.json` with `"typescript"` in deps/devDeps |
| `go` | `go.mod` |
| `rust` | `Cargo.toml` |

If no markers are found, set `STACK=generic` and continue — the generic
profile ships only language-agnostic rules.

Record the detected stack in memory:

```bash
STACK=$(
  if [ -f pyproject.toml ] || [ -f setup.py ] || [ -f setup.cfg ] || [ -f requirements.txt ]; then echo python
  elif [ -f tsconfig.json ] || (grep -q '"typescript"' package.json 2>/dev/null); then echo typescript
  elif [ -f go.mod ]; then echo go
  elif [ -f Cargo.toml ]; then echo rust
  else echo generic
  fi
)
```

Report the detection to the user before any write. If `--dry-run` was passed,
stop here.

### Step 2: Scaffold CLAUDE.md

Only create if the file does not already exist.

```bash
if [ ! -f CLAUDE.md ]; then
  # Write a minimal CLAUDE.md with project name, stack, and a pointer
  # to the agent-memory directory. Do NOT write boilerplate that the
  # user would have to immediately delete.
  Write CLAUDE.md
fi
```

The body should include: one-line project description (use the git remote or
the repo directory name as fallback), the detected `STACK:`, and a
"Memory policy" paragraph explaining that `.claude/agent-memory/` is
authoritative for cross-session facts.

**If CLAUDE.md already exists**, leave it untouched and print
`✓ CLAUDE.md already present — left unchanged`.

### Step 3: Scaffold .claude/rules/

Create the directory and exactly the stack-matching rule file plus a
language-agnostic `common.md`. Never overwrite.

```bash
mkdir -p .claude/rules
# common.md — always
[ -f .claude/rules/common.md ] || Write .claude/rules/common.md
# stack-specific
[ -f .claude/rules/${STACK}.md ] || Write .claude/rules/${STACK}.md
```

Rule file contents come from the templates the platxa-memory plugin ships
alongside this skill (tracked by separate spec features). Each rule file is a
markdown document with a short header stating which file-path globs it
targets.

### Step 4: Scaffold .claude/agent-memory/

Create the directory with a `.gitkeep` (so the directory is tracked even when
empty) and a `MEMORY.md` index seeded with the standard header.

```bash
mkdir -p .claude/agent-memory
[ -f .claude/agent-memory/.gitkeep ] || Write .claude/agent-memory/.gitkeep
[ -f .claude/agent-memory/MEMORY.md ] || Write .claude/agent-memory/MEMORY.md
```

Seeded `MEMORY.md` should contain a one-line description, an empty topic-file
index, and a reference link back to the `memory-curator` agent.

### Step 5: Scaffold CLAUDE.local.md + .gitignore

Create `CLAUDE.local.md` (a per-developer file that MUST be gitignored) only
if it does not already exist, then ensure the gitignore contains the required
entries.

```bash
[ -f CLAUDE.local.md ] || Write CLAUDE.local.md
# Ensure .gitignore exists
touch .gitignore
# Required ignore entries — append only if missing
for line in 'CLAUDE.local.md' '.claude/agent-memory-local/' '.claude/agent-memory/*/audit_*.md'; do
  grep -qxF "$line" .gitignore || printf '%s\n' "$line" >> .gitignore
done
```

The `grep -qxF` guard is what makes step 5 idempotent. Never use `>>` without
the guard — that is how duplicate gitignore lines sneak in over repeated runs.

### Step 6: Verify idempotence

The canonical post-condition check:

```bash
# After the first run: there will be staged/untracked changes.
# After any subsequent run on the same repo: git must be clean.
git status --porcelain
```

On a re-run, the output of `git status --porcelain` for the paths this skill
touches MUST be empty. If it is not, the skill introduced a non-idempotent
write and must be corrected before continuing.

Automated self-test (run once inside a throwaway git repo):

```bash
git init /tmp/memory-init-test && cd /tmp/memory-init-test
# first invocation — scaffolds files
# second invocation — MUST produce no new changes
# third invocation — same
git add -A && git diff --cached --quiet && echo PASS || (echo FAIL; exit 1)
```

## Options

| Flag | Effect |
|------|--------|
| `--stack <python\|typescript\|go\|rust\|generic>` | Override auto-detection |
| `--dry-run` | Report detection + planned writes, perform no file mutations |
| `--verbose` | Print every path decision (created / skipped-existing) |

## Output

Emit a compact summary once all 6 steps complete:

```
Detected stack: python
Created:  CLAUDE.md, .claude/rules/common.md, .claude/rules/python.md,
          .claude/agent-memory/MEMORY.md, .claude/agent-memory/.gitkeep,
          CLAUDE.local.md
Updated:  .gitignore (3 entries appended)
Skipped (already present): (none)
Idempotent re-run check: git status clean — PASS
```

## Output Checklist

Before marking the skill complete, verify:

- [ ] `CLAUDE.md` exists at repo root (either pre-existing or newly created).
- [ ] `.claude/rules/common.md` exists.
- [ ] `.claude/rules/<stack>.md` exists (for detected or overridden stack).
- [ ] `.claude/agent-memory/MEMORY.md` exists with seeded header.
- [ ] `CLAUDE.local.md` exists at repo root.
- [ ] `.gitignore` contains `CLAUDE.local.md`, `.claude/agent-memory-local/`,
      and `.claude/agent-memory/*/audit_*.md` (each on its own line, no
      duplicates).
- [ ] A subsequent dry-run of this skill reports no planned writes.
- [ ] `git status --porcelain` prints nothing after a re-run.

## Examples

### Example 1: Fresh Python project

```
User: /memory-init
Assistant: Detected stack: python
           Plan: create CLAUDE.md, .claude/rules/{common,python}.md,
                 .claude/agent-memory/MEMORY.md, CLAUDE.local.md;
                 append 3 lines to .gitignore.
           Proceed? (y/n)
User: y
Assistant: Created 6 files. Updated .gitignore (3 new lines).
           Idempotent re-run check: PASS.
```

### Example 2: Re-running on an already-initialized repo

```
User: /memory-init
Assistant: Detected stack: typescript
           All scaffold paths already present. No writes needed.
           Idempotent re-run check: PASS.
```

### Example 3: Dry-run before a team rollout

```
User: /memory-init --dry-run --verbose
Assistant: Detected stack: go
           Would create: CLAUDE.md, .claude/rules/common.md,
                         .claude/rules/go.md, .claude/agent-memory/MEMORY.md,
                         CLAUDE.local.md
           Would append to .gitignore: CLAUDE.local.md,
                                       .claude/agent-memory-local/,
                                       .claude/agent-memory/*/audit_*.md
           Dry run complete — no files modified.
```

## Gotchas

| Problem | Cause | Fix |
|---------|-------|-----|
| Second run creates duplicate `.gitignore` lines | Used `>>` without `grep -qxF` guard | Always guard appends with a fixed-string grep |
| Stack detection picks TypeScript for a Python monorepo | Order of checks puts TS before Python | Pass `--stack python` to override |
| `CLAUDE.md` gets overwritten | Skill used `Write` without existence check | Step 2 MUST check `[ ! -f CLAUDE.md ]` before writing |
| `.claude/agent-memory/` vanishes from git | Empty dirs aren't tracked | Step 4 writes a `.gitkeep` so the dir is committable |
| Idempotence check fails because of timestamp fields | Seeded MEMORY.md or CLAUDE.md included today's date | Seed files must be fully deterministic — no `$(date)` |

<!-- managed by platxa-skill-generator -->
