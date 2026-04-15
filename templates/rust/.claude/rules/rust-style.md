---
name: rust-style
description: Rust source-style rules — formatting, error handling, modules
paths:
  - "**/*.rs"
  - "src/**/*.rs"
---

# Rust style

## Formatting and lints

- `cargo fmt` on every save. `cargo clippy -- -D warnings` in CI; every
  warning is an error.
- Do not `#[allow(...)]` a clippy lint without a comment explaining why
  the lint is wrong for this site.

## Naming

- `snake_case` for functions, methods, variables, and module names.
- `PascalCase` for types, traits, and enum variants.
- `SCREAMING_SNAKE_CASE` for constants and statics.
- Acronyms follow the type convention: `HttpClient`, not `HTTPClient`.

## Error handling

- Library crates return `Result<T, E>` with a crate-local error type.
  Application crates use `anyhow::Result<T>` and `.context("...")`.
- Do not `.unwrap()` or `.expect("...")` outside of tests and example
  code. Every unwrap in production is a crash waiting to happen.
- Propagate with `?`; annotate the failure site with `.context()` so the
  error chain is readable upstream.

## Modules

- A module in `foo.rs` is preferred over `foo/mod.rs` unless the module
  has child modules. New code should not introduce new `mod.rs` files.
- `pub` is a considered decision. Prefer `pub(crate)` for items that
  cross module boundaries inside the crate but are not part of the
  public API.
