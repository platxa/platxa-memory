---
name: typescript-style
description: TypeScript source-style rules — strict typing, imports, modules
paths:
  - "**/*.ts"
  - "**/*.tsx"
  - "src/**/*.ts"
  - "src/**/*.tsx"
---

# TypeScript style

## Strictness

- `tsconfig.json` must enable `strict: true`. If a file needs a narrower
  rule, add a `// @ts-expect-error <reason>` comment — never `// @ts-ignore`.
- Do not use `any`. Use `unknown` at module boundaries and narrow with
  type guards. Explicit `any` is reserved for third-party shims.
- Prefer `readonly` on interface and type members that are not mutated
  after construction.

## Imports

- Use ES module `import` syntax, never `require`.
- Group imports: Node builtins, third-party packages, then local modules,
  separated by blank lines.
- Prefer named exports over default exports so renames and auto-imports
  are lossless.

## Types vs interfaces

- `interface` for object shapes that may be extended or augmented.
- `type` for unions, tuples, mapped types, and aliases. Do not mix —
  choose one per declaration and stick with it.

## Naming

- `camelCase` for variables, functions, and methods.
- `PascalCase` for classes, interfaces, type aliases, and React components.
- `UPPER_SNAKE_CASE` for module-level constants.
- Exported React components live in their own file; the file name matches
  the component name (`UserAvatar.tsx` exports `UserAvatar`).
