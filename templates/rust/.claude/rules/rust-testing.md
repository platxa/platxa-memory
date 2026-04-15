---
name: rust-testing
description: Testing conventions for Rust projects (built-in test harness)
paths:
  - "tests/**/*.rs"
  - "**/*_test.rs"
  - "src/**/*.rs"
---

# Rust testing

## Where tests live

- **Unit tests** live in a `#[cfg(test)] mod tests { ... }` block at the
  bottom of the module they exercise. They can access private items.
- **Integration tests** live in `tests/` at the crate root. Each file is
  compiled as a separate crate and can only touch the public API.
- **Doc tests** live in `///` comments on public items. Every public
  function with a non-trivial contract has at least one doc test.

## Naming

- Test functions: `#[test] fn test_<behaviour>` — underscores separating
  words. Short but descriptive: `test_rejects_empty_input` beats
  `test_1`.
- `#[should_panic(expected = "...")]` tests include the expected panic
  fragment. A bare `#[should_panic]` with no expected string is brittle.

## Assertions

- `assert_eq!` / `assert_ne!` include a format string when the default
  output is ambiguous: `assert_eq!(got, want, "for input {input:?}")`.
- Prefer specific assertions over `assert!(bool)` when a more precise
  form exists. `assert_eq!(a, b)` beats `assert!(a == b)` for the error
  message alone.

## Fixtures

- Use `tempfile::TempDir` for filesystem fixtures; do not construct
  paths under `/tmp` manually.
- Run expensive setup once with `std::sync::OnceLock` rather than
  per-test — but only if the fixture is truly read-only.
