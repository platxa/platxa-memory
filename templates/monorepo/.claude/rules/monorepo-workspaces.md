---
name: monorepo-workspaces
description: Conventions for workspace roots in a monorepo
paths:
  - "pnpm-workspace.yaml"
  - "package.json"
  - "turbo.json"
  - "nx.json"
  - "go.work"
  - "Cargo.toml"
  - "rush.json"
---

# Monorepo workspaces

## Workspace definition

- One tool defines workspaces at the repo root: pnpm (`pnpm-workspace.yaml`),
  Yarn (`package.json#workspaces`), npm (`package.json#workspaces`), Turbo
  (`turbo.json`), Nx (`nx.json`), Cargo (`Cargo.toml#workspace`), or Go
  (`go.work`). Do not mix tools at the root.
- Workspace globs live in one source of truth. Do not list packages
  twice (once in `pnpm-workspace.yaml` and once in `turbo.json`).

## Dependency direction

- Apps depend on libs. Libs do not depend on apps. Libs do not depend
  on other libs unless the direction is documented in an ADR.
- No cyclic dependencies between workspace members. `pnpm list -r` or
  the tool's dependency graph command should produce a DAG.

## Versioning

- Internal packages use a workspace protocol (`workspace:*`, `1.0.0` in
  Cargo workspaces). External package versions are pinned in the root
  lockfile; do not override versions in leaf packages.
- Shared devDependencies (TypeScript, ESLint, Vitest) are pinned once
  at the root and inherited by workspaces. Leaf packages only pin
  production dependencies.

## CI

- A change that touches package A must pass tests for A and every
  package that imports A. Use `turbo run --filter=...[HEAD~1]` or the
  equivalent to compute affected workspaces.
