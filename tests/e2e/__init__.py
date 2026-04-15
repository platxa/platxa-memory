"""End-to-end integration tests for platxa-memory.

These tests build a temporary scratch project, exercise the user-visible
plugin surface (CLI + hooks + templates) the way a real install would,
and assert the install → init → status happy path succeeds. Unlike the
sibling unit tests, every interaction here uses ``subprocess`` so the
shebang, argparse wiring, stdin/stdout envelope, and exit codes are all
exercised together.
"""
