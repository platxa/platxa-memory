---
name: python-style
description: Python source-style rules — imports, typing, docstrings, naming
paths:
  - "**/*.py"
  - "src/**/*.py"
---

# Python style

## Imports

- Standard-library imports first, third-party next, first-party last, each
  group separated by a blank line. Let `ruff check --select I` enforce this.
- Never use `from foo import *`. Import specific names even when the
  upstream module advertises `__all__`.
- Prefer absolute imports within the package. Relative imports are reserved
  for sibling modules inside a leaf package.

## Typing

- Every public function and method has type hints on parameters and return
  value. Private helpers (`_prefix`) may omit annotations only when the
  body is a one-line pass-through.
- Use `from __future__ import annotations` so forward references in type
  hints work without quoting.
- `Any` is a code smell. Prefer `object` for "I don't care" or a `TypeVar`
  for "any specific type".

## Docstrings

- Every public module, class, and function has a one-line docstring
  describing the contract. Multi-line docstrings document side effects,
  raised exceptions, and non-obvious invariants.
- Docstring body uses plain Markdown; no RST directives.

## Naming

- `snake_case` for functions, methods, and module-level names.
- `PascalCase` for classes and type aliases.
- `UPPER_SNAKE_CASE` for module-level constants.
- A leading underscore marks a name as private; a trailing underscore
  resolves a conflict with a builtin (`class_`, `type_`).
