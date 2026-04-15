---
name: go-style
description: Go source-style rules — formatting, naming, package layout
paths:
  - "**/*.go"
  - "cmd/**/*.go"
  - "internal/**/*.go"
  - "pkg/**/*.go"
---

# Go style

## Formatting

- Every commit is `gofmt`-clean. CI runs `gofmt -l` and fails on any
  output. Prefer `goimports` locally to manage imports automatically.
- Line length is a suggestion, not a limit; break lines where the break
  improves readability, not to hit 100 columns.

## Naming

- Exported identifiers start with a capital letter. Package-local names
  start with lowercase. No underscores in identifiers outside of test
  files (`Test_xxx` is OK).
- Acronyms stay uppercase: `URL`, `HTTP`, `ID`. `userId` is wrong;
  `userID` is correct.
- Package names are lowercase single words, no underscores. Match the
  directory name.

## Error handling

- Functions that can fail return `(T, error)` as the last return value.
  Never encode failure in a zero value without an accompanying error.
- Wrap errors with context using `fmt.Errorf("thing: %w", err)` so
  callers can `errors.Is` / `errors.As` up the chain.
- Do not `panic` in library code. Reserve `panic` for truly impossible
  states and caller-misuse in init.

## Package layout

- `cmd/<bin>/main.go` for binaries, with all business logic behind the
  `cmd/` boundary in `internal/` or `pkg/`.
- `internal/` for code that must not be imported by other modules.
- `pkg/` for reusable library code. Empty `pkg/` is fine; don't create
  the directory until you actually have something reusable.
