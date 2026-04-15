---
name: python-testing
description: Pytest layout and conventions for Python projects
paths:
  - "tests/**/*.py"
  - "**/test_*.py"
  - "**/*_test.py"
  - "conftest.py"
  - "**/conftest.py"
---

# Python testing (pytest)

## Layout

- Test files live under `tests/` and mirror the `src/` package tree.
- Fixture helpers shared across multiple modules live in the nearest
  `conftest.py`. Do not import fixtures from other test modules directly.
- Integration tests that require external services are marked with
  `@pytest.mark.integration` and skipped by default in CI.

## Naming

- Test files: `test_<module>.py`.
- Test functions: `test_<behaviour_being_verified>` — a full sentence with
  underscores, not a camelCased verb ("test_rejects_empty_input" not
  "testRejectsEmptyInput").
- Parametrise via `@pytest.mark.parametrize`; do not write loops over
  cases inside a single test function.

## What to assert

- One behaviour per test. If a test needs three assertions to describe one
  behaviour (e.g. `returncode`, `stdout`, and side-effect file), that is
  one test. If it needs to test three behaviours, that is three tests.
- Test the public contract, not the implementation. Reaching into private
  internals (`_prefix` attributes) couples tests to refactors.

## Fixtures

- Prefer `tmp_path` over string manipulation for temporary filesystem
  state. It is per-test and auto-cleaned.
- Reset environment variables with `monkeypatch.setenv` /
  `monkeypatch.delenv` rather than mutating `os.environ` directly.
