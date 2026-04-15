---
name: typescript-testing
description: Testing conventions for TypeScript projects (Jest / Vitest)
paths:
  - "**/*.test.ts"
  - "**/*.test.tsx"
  - "**/*.spec.ts"
  - "**/*.spec.tsx"
  - "tests/**/*.ts"
  - "tests/**/*.tsx"
---

# TypeScript testing

## Framework

- Default to Vitest for library and Vite-based projects; Jest for
  Create-React-App legacy repos. Do not mix both in the same package.
- Tests live next to the source they exercise (`foo.ts` + `foo.test.ts`)
  OR under a top-level `tests/` tree — pick one pattern per package.

## Naming

- Test files: `<source>.test.ts` or `<source>.spec.ts`.
- Top-level `describe` names the subject under test (class, function, or
  component name). Nested `describe` names behaviours or states. `it`
  phrases an expectation as a sentence ("returns zero when list empty").

## Assertions

- One expected behaviour per `it`. Use `toEqual` for structural equality,
  `toBe` for identity, and `toMatchObject` for partial matches — never
  mix them arbitrarily.
- Snapshot tests are reserved for output that is genuinely stable
  (component renders, generated files). Don't snapshot API responses or
  other fast-changing payloads.

## Mocks

- Prefer dependency injection over module-level mocks. When mocking is
  unavoidable, use `vi.mock` / `jest.mock` at the top of the file and
  include a comment explaining why the real module is not used.
- Reset mocks between tests via `beforeEach(() => vi.resetAllMocks())` so
  test order never affects outcomes.
