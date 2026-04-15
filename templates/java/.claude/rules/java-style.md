---
name: java-style
description: Java source-style rules — naming, imports, nullability
paths:
  - "**/*.java"
  - "src/main/java/**/*.java"
---

# Java style

## Naming

- `PascalCase` for classes, interfaces, and enum types.
- `camelCase` for methods, fields, and local variables.
- `UPPER_SNAKE_CASE` for constants (`static final`).
- Package names are lowercase, no underscores, and mirror the reverse
  DNS of the owning organisation (`com.example.module`).

## Imports

- No wildcard imports (`import foo.*;`). One import per type.
- Organise imports in groups: Java stdlib, third-party, then project
  packages — alphabetical within each group.
- Do not depend on IDE auto-import to remove unused imports; the CI
  formatter is the source of truth.

## Nullability

- Annotate parameters and return values with `@Nullable` or `@NonNull`
  from `org.jspecify.annotations` (or the project's chosen nullability
  library). Unannotated references are assumed non-null.
- Do not return `null` from a method that returns a collection. Return
  an empty immutable collection (`List.of()`, `Map.of()`).

## Immutability

- Prefer `final` on fields and local variables that are not reassigned.
  The compiler does not require it, but readers do.
- Factory methods over constructors for types with more than three
  fields or optional parameters. `Builder` pattern when the type is
  public API.
