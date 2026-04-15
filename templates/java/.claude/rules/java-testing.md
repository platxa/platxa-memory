---
name: java-testing
description: Testing conventions for Java projects (JUnit 5)
paths:
  - "src/test/java/**/*.java"
  - "**/*Test.java"
  - "**/*Tests.java"
  - "**/*IT.java"
---

# Java testing (JUnit 5)

## Layout

- Tests live under `src/test/java/` mirroring the `src/main/java/`
  package structure. A test for `com.example.foo.Bar` lives at
  `src/test/java/com/example/foo/BarTest.java`.
- Integration tests use the suffix `IT` (`FooIT.java`). Build tooling
  (Failsafe / Gradle) runs them separately from unit tests.

## Naming

- Test classes: `<ClassUnderTest>Test` or `<ClassUnderTest>Tests`.
- Test methods: `camelCase` describing the behaviour. JUnit 5 supports
  `@DisplayName("...")` for human-readable names in reports — use it
  when the method name alone would be cryptic.

## Assertions

- Use `org.junit.jupiter.api.Assertions` (`assertEquals`,
  `assertThrows`, `assertAll`). AssertJ is allowed if the project
  already uses it; do not mix both.
- Every assertion has a failure message unless the default diff is
  self-evidently clear.

## Fixtures

- Use `@TempDir Path tempDir` for filesystem fixtures.
- Use `@BeforeEach` / `@AfterEach` for per-test setup and teardown;
  reserve `@BeforeAll` / `@AfterAll` for genuinely immutable shared
  state.
- Mock with Mockito when the real collaborator is slow or has side
  effects; otherwise inject the real implementation.
