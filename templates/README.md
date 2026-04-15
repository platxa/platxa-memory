# Stack-profile templates

Drop-in `.claude/rules/` bundles for common project stacks. Each template
ships path-scoped rule files that Claude Code loads when the user edits a
matching file.

## How to use a template

1. Pick the stack that matches your repo (see the list below).
2. Copy the template's `.claude/rules/` directory into your project root:

   ```bash
   cp -r /path/to/platxa-memory/templates/<stack>/.claude/rules .claude/
   ```

3. Commit the files. They are lightweight Markdown with YAML frontmatter;
   no build step is required.
4. Open a file that matches one of the rule's `paths:` globs — Claude Code
   injects the rule body into the context automatically.

The `platxa-memory detect-stack` subcommand reports the stack name for a
given project; it matches the template directory names exactly.

## Available stacks

| Template      | Detect-stack label | Typical marker files                                |
|---------------|--------------------|-----------------------------------------------------|
| `python/`     | `python`           | `pyproject.toml`, `setup.py`, `requirements.txt`    |
| `typescript/` | `typescript`       | `tsconfig.json`                                     |
| `go/`         | `go`               | `go.mod`                                            |
| `rust/`       | `rust`             | `Cargo.toml`                                        |
| `java/`       | `java`             | `pom.xml`, `build.gradle`, `build.gradle.kts`       |
| `ruby/`       | `ruby`             | `Gemfile`                                           |
| `monorepo/`   | _(manual)_         | `pnpm-workspace.yaml`, `package.json` with `workspaces` |

## Frontmatter contract

Every rule file uses the same frontmatter shape:

```yaml
---
name: short-stable-identifier
description: one-line summary shown in rule listings
paths:
  - "glob/pattern/**/*.ext"
---
```

- `name` — kebab-case, stable across renames (hook logs reference it)
- `description` — single line, no trailing period
- `paths` — a non-empty list of glob patterns; relative, no leading `/`

Rules are free Markdown below the frontmatter. Keep each under ~80 lines;
`memory-synthesizer` will not write through a rule body, but readers still
pay a context cost on every trigger.
