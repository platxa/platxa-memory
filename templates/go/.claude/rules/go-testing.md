---
name: go-testing
description: Testing conventions for Go projects (stdlib testing package)
paths:
  - "**/*_test.go"
---

# Go testing

## Layout

- Tests live next to the code they exercise (`foo.go` + `foo_test.go`)
  in the same package. External test packages use the `_test` suffix on
  the package name (`package foo_test`) to verify only the exported API.
- Table-driven tests are the default for functions with multiple cases.
  Use `t.Run(tt.name, func(t *testing.T) { ... })` so cases show up as
  independent subtests.

## Naming

- Test functions: `TestFunctionName_BehaviourBeingVerified` — the
  underscore separates the subject from the behaviour.
- Benchmark functions: `BenchmarkFunctionName`.
- Example functions: `ExampleFunctionName`; the output comment is
  verified by `go test`.

## Assertions

- Use the stdlib `testing` package. Do not pull in an assertion library
  unless the project already has one.
- Prefer `t.Errorf` for continue-after-failure and `t.Fatalf` for
  cannot-continue failures. Always include the actual and expected
  values in the message: `got %v, want %v`.

## Fixtures

- Use `t.TempDir()` for filesystem state. It is per-test and cleaned up
  automatically.
- For environment variables, use `t.Setenv`. Direct `os.Setenv` leaks
  state across tests.
- Parallelise independent tests with `t.Parallel()` at the top of the
  test body. Do not parallelise tests that share mutable state.
