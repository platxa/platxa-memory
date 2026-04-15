---
name: ruby-style
description: Ruby source-style rules — naming, blocks, method conventions
paths:
  - "**/*.rb"
  - "lib/**/*.rb"
  - "app/**/*.rb"
  - "bin/*"
---

# Ruby style

## Naming

- `snake_case` for methods, variables, and file names.
- `PascalCase` for classes and modules.
- `SCREAMING_SNAKE_CASE` for constants.
- Predicate methods end with `?`; mutating methods end with `!`. A `!`
  method must have a non-`!` counterpart (`sort!` and `sort`).

## Blocks

- Use `{ ... }` for single-line blocks and `do ... end` for multi-line
  blocks. Do not mix.
- Prefer `.each` over explicit `for` loops. Prefer `.map` / `.select` /
  `.reject` over `.each` accumulating into an array.

## Methods

- One method, one job. A method longer than ~10 lines is a refactoring
  candidate; split along the seams of its comments.
- Keyword arguments for anything beyond two parameters. Positional
  arguments are fine for one or two well-known parameters.
- Raise `ArgumentError` for invalid caller input; raise a domain error
  subclass for business-rule violations.

## Frozen strings

- Include `# frozen_string_literal: true` at the top of every file.
  Mutating a literal is a bug waiting to happen.
