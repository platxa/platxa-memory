---
name: ruby-testing
description: Testing conventions for Ruby projects (RSpec / Minitest)
paths:
  - "spec/**/*.rb"
  - "test/**/*.rb"
  - "**/*_spec.rb"
  - "**/*_test.rb"
---

# Ruby testing

## Framework

- RSpec for new projects. Minitest is acceptable for Rails projects
  that already ship with it — do not introduce RSpec into a Minitest
  codebase or vice versa.

## Layout

- RSpec: specs live under `spec/`, mirroring `lib/` / `app/`. A spec
  for `lib/foo/bar.rb` lives at `spec/foo/bar_spec.rb`.
- Minitest: tests live under `test/`, mirroring `lib/` / `app/`. A test
  for `lib/foo/bar.rb` lives at `test/foo/bar_test.rb`.

## Naming

- RSpec: outer `describe` names the class under test; nested `describe`
  names methods (`#instance_method`, `.class_method`); `context` names
  state; `it` describes behaviour in a sentence.
- Minitest: test methods start with `test_` followed by a snake-case
  sentence describing the behaviour.

## Assertions

- RSpec: prefer `expect(actual).to eq(expected)` over `should` syntax.
  Use matcher aliases (`to include`, `to match`, `to be_a`) to express
  intent.
- Minitest: use the assertion that matches intent — `assert_equal` for
  values, `assert_kind_of` for types, `assert_raises` for exceptions.

## Fixtures and doubles

- Prefer factories (FactoryBot) over raw ActiveRecord `.create!` in
  Rails specs so the data is controlled from test code, not fixtures.
- Use doubles sparingly. A double that mirrors every method of a real
  collaborator is a sign the real collaborator is easy enough to use
  in the test.
