---
name: monorepo-cross-package
description: Cross-package conventions for source files inside monorepo workspaces
paths:
  - "packages/**/*"
  - "apps/**/*"
  - "libs/**/*"
  - "services/**/*"
  - "crates/**/*"
---

# Monorepo cross-package conventions

## Imports across workspaces

- Import workspace packages by their public name (`@org/foo`), never by
  relative path. `from "../../foo"` bypasses the public API and breaks
  when the workspace layout changes.
- Each workspace exports a single `index` module (`index.ts`, `lib.rs`,
  `mod.go`). External imports go through that module; internal modules
  are not part of the public contract.

## Build boundaries

- A change inside a package must build and test that package in
  isolation before integration. `turbo run build --filter=@org/foo`
  should succeed without building dependents.
- Generated files (`dist/`, `target/`, `__generated__/`) are ignored in
  git and rebuilt from source. A leaf package never commits build
  output.

## Config inheritance

- Shared config (`tsconfig.base.json`, `.eslintrc.base.cjs`,
  `rustfmt.toml`) lives at the repo root. Leaf packages extend the
  base; they do not fork it.
- Override at the leaf only when the package genuinely differs (e.g.
  a React Native app extends the base but sets `jsx: "react-native"`).
  Every override has a comment explaining why.

## Naming

- Package names use a consistent prefix across the repo (`@org/foo`,
  `myorg-foo`, `com.example.foo`). Mix-and-match hurts discovery.
- Directory name matches package name — `packages/user-service/`
  exposes `@org/user-service`, not `@org/users`.
