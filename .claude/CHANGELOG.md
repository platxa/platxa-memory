# Spec Workflow Changelog

## #10 [AGENTS] Ship memory-doctor agent (memory: local, haiku): diagnoses memory issues (oversized MEMORY.md, orphaned topic files, conflicting rules, stale instincts); writes fixes to .claude/agent-memory-local/

- **Commit**: `25c2b07`
- **Completed**: 2026-04-16T22:56:00.092608Z
- **Duration**: 8m 57s

## #8 [AGENTS] Ship memory-migrator agent (memory: project, sonnet): handles schema version upgrades for memory files (e.g., v1 plain markdown to v2 frontmatter-indexed)

- **Commit**: `66a9526`
- **Completed**: 2026-04-15T14:36:38.482673Z
- **Duration**: 2h 30m

## #4 [REPO_SETUP] Define plugin.json userConfig fields for opt-in features: observation_capture (bool), memory_token_budget (int, default 25000), telemetry_endpoint (URL, sensitive: false, optional)

- **Commit**: `49a0a2c`
- **Completed**: 2026-04-15T12:05:04.956554Z
- **Duration**: 34m 53s

## #50 [OPERABILITY] Add end-to-end integration tests in tests/e2e/: install platxa-memory in scratch project, run /memory-init, verify generated files, invoke /memory-status

- **Commit**: `332a338`
- **Completed**: 2026-04-15T11:29:14.739928Z
- **Duration**: 5m 55s

## #45 [DISTRIBUTION] Set up GitHub Actions CI: claude plugin validate, python lint/type check, test suite, marketplace schema check on PRs and tags

- **Commit**: `6553c60`
- **Completed**: 2026-04-15T11:22:50.622441Z
- **Duration**: 6m 12s

## #44 [DISTRIBUTION] Add platxa-memory plugin entry to a new platxa-plugins marketplace.json repository (separate from platxa-code-agent but same marketplace)

- **Commit**: `2fc31ea`
- **Completed**: 2026-04-15T11:16:03.283630Z
- **Duration**: 7m 28s

## #42 [DOCUMENTATION] Write README.md with: what platxa-memory is, installation (/plugin marketplace add then /plugin install), quickstart (/memory-init), core concepts, comparison with platxa-code-agent

- **Commit**: `26a6f1f`
- **Completed**: 2026-04-15T11:08:03.971804Z
- **Duration**: 4m 40s

## #41 [DOCUMENTATION] Write docs/memory-architecture.md: layer diagram (CLAUDE.md + rules + auto memory + agent memory + instincts), loading order, /compact survival matrix, per-project routing

- **Commit**: `7ee28a1`
- **Completed**: 2026-04-15T11:02:56.207467Z
- **Duration**: 9m 43s

## #37 [DURABILITY] Implement atomic file write helper in Python: tempfile.NamedTemporaryFile(delete=False, dir=target_parent) -> write -> fsync -> os.replace; parent dir fsync on POSIX

- **Commit**: `d597566`
- **Completed**: 2026-04-15T10:44:24.604668Z
- **Duration**: 9m 35s

## #35 [STACK_DETECTION] Implement stack detector: walk up from CWD, match marker files (pyproject.toml, package.json, go.mod, Cargo.toml, pom.xml, Gemfile, build.gradle, composer.json, mix.exs), return structured {primary, secondary, markers}

- **Commit**: `c8a4571`
- **Completed**: 2026-04-15T10:34:19.741483Z
- **Duration**: 9m 54s

## #32 [TEMPLATES] Ship CLAUDE.md skeleton template with @imports to generated rules files + AGENTS.md compat; under 200 lines

- **Commit**: `2dc6c7e`
- **Completed**: 2026-04-15T10:22:27.670674Z
- **Duration**: 11m 43s

## #31 [TEMPLATES] Ship stack-profile templates for Python, TypeScript, Go, Rust, Java, Ruby, monorepo: each contains .claude/rules/*.md with paths: frontmatter matching language conventions

- **Commit**: `0345f07`
- **Completed**: 2026-04-15T10:09:26.912693Z
- **Duration**: 8m 55s

## #30 [TEMPLATES] Implement platxa-memory CLI at bin/platxa-memory with subcommands: detect-stack, health, search, export, import, prune, restore, migrate

- **Commit**: `b0095e7`
- **Completed**: 2026-04-15T09:57:55.195171Z
- **Duration**: 17m 14s

## #26 [HOOKS] Stop hook (command type): dispatches memory-synthesizer agent to write session insights to MEMORY.md + topic files; uses PreToolUse to prevent infinite loops

- **Commit**: `c0bfc60`
- **Completed**: 2026-04-15T09:39:13.771201Z
- **Duration**: 7m 14s

## #23 [HOOKS] PostCompact hook (command type): re-injects auto memory MEMORY.md + critical rules that were loaded before compact via InstructionsLoaded event replay

- **Commit**: `642c4d3`
- **Completed**: 2026-04-14T21:27:36.858122Z
- **Duration**: 4m 23s

## #22 [HOOKS] PreCompact hook (command type): detects unsaved session insights (conversation mentions not yet in memory); offers to save first; exits 2 to block if critical context pending

- **Commit**: `c2adf26`
- **Completed**: 2026-04-14T21:20:34.230617Z
- **Duration**: 6m 7s

## #21 [HOOKS] SessionStart hook (command type): reads user project auto memory ~/.claude/projects/<hash>/memory/MEMORY.md + instincts + stack detection, emits additionalContext JSON; honors memory_token_budget user config

- **Commit**: `b741404`
- **Completed**: 2026-04-14T21:13:17.772205Z
- **Duration**: 6m 7s

## #15 [SKILLS] Implement /memory-search skill: grep-based full-text search across all memory files for current project + user scope; supports --scope, --limit, --format options via argument-hint

- **Commit**: `10259cd`
- **Completed**: 2026-04-14T21:03:59.233158Z
- **Duration**: 3m 53s

## #13 [SKILLS] Implement /memory-doctor skill (disable-model-invocation: true): runs memory-doctor agent via context: fork + agent: memory-doctor; output summarizes issues and offers fix commands

- **Commit**: `2e77807`
- **Completed**: 2026-04-14T20:58:30.950215Z
- **Duration**: 6m 53s

## #12 [SKILLS] Implement /memory-status skill: lists all loaded CLAUDE.md + rules + auto memory + agent memory files; shows sizes, last modified, token cost, loaded-in-session state

- **Commit**: `8136ef7`
- **Completed**: 2026-04-14T20:50:23.414698Z
- **Duration**: 3m 30s

## #11 [SKILLS] Implement /memory-init skill (disable-model-invocation: true): bootstraps memory systems — detects stack, instantiates CLAUDE.md + .claude/rules/ templates + agent-memory/ + CLAUDE.local.md + .gitignore entries

- **Commit**: `c33ae53`
- **Completed**: 2026-04-14T20:45:37.443010Z
- **Duration**: 5m 1s

## #9 [AGENTS] Ship memory-researcher agent (memory: project, haiku): searches memory on-demand using Grep/Read; returns concise citations instead of dumping content

- **Commit**: `bd21120`
- **Completed**: 2026-04-14T20:39:23.093044Z
- **Duration**: 2m 58s

## #7 [AGENTS] Ship memory-auditor agent (memory: user, haiku): cross-project audit of memory staleness, confidence drift, duplication; user-scope so patterns generalize across projects

- **Commit**: `56f1cdc`
- **Completed**: 2026-04-14T20:34:16.456539Z
- **Duration**: 3m 20s

## #6 [AGENTS] Ship memory-synthesizer agent (memory: project, sonnet): extracts session insights and writes concise topic files; called from Stop hook at session end

- **Commit**: `a119fc7`
- **Completed**: 2026-04-14T20:29:10.851646Z
- **Duration**: 3m 2s

## #5 [AGENTS] Ship memory-curator agent (memory: project, sonnet): reads, updates, prunes memory files for the current project; consults MEMORY.md first then topic files

- **Commit**: `be14eef`
- **Completed**: 2026-04-14T20:24:40.443571Z
- **Duration**: 5m 2s

## #3 [REPO_SETUP] Set up pyproject.toml + ruff + pyright for Python code (hook scripts and CLI). Match platxa-code-agent toolchain.

- **Commit**: `46ce5f9`
- **Completed**: 2026-04-14T20:15:28.162888Z
- **Duration**: 11m 17s

## #2 [REPO_SETUP] Create .claude-plugin/plugin.json with name=platxa-memory, semver version, description, author, keywords=[memory,context,claude-code], repository URL, homepage, license=MIT

- **Commit**: `23e3e04`
- **Completed**: 2026-04-14T20:02:53.619162Z
- **Duration**: 5m 0s

