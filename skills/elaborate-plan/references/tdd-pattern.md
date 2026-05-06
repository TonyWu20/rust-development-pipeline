# TDD Pattern: The ch12-04 Workflow

This document codifies the Test-Driven Development workflow from the Rust book's
Chapter 12.4 ("Adding Functionality with Test-Driven Development") as a reusable
pattern for the pipeline's `lib-tdd` tasks.

## The Core Cycle

The ch12-04 TDD cycle has four repeating steps:

1. **Write a failing test** — specify the behavior you want. Run it, confirm it
   fails for the expected reason (the function doesn't exist yet, or returns
   wrong data).
2. **Write minimal code to pass** — do the minimum to make the test compile and
   pass. Start with a stub, then fill in logic incrementally.
3. **Refactor while green** — clean up the implementation. The test stays green
   throughout; it protects against regressions.
4. **Repeat** — add the next test, implement, refactor.

### The test IS the specification

The critical insight is that the test defines the public API *before* any
implementation exists. It specifies:

- **The function signature** — exact parameter types and return type
- **The expected behavior** — concrete inputs and outputs
- **The edge cases** — what happens with empty input, missing values, etc.

The implementation agent must treat the test code as an immutable contract: it
can only change the production code to satisfy the test, never the test itself.

### Incremental implementation

The ch12-04 chapter demonstrates this pattern with the `search` function:

```
Step 1 (RED):   Write test_search_one_result() that calls search("duct", contents)
                and expects vec!["safe, fast, productive."]
                → cargo test → fails (search doesn't exist)

Step 2 (Stub):  Define fn search(query: &str, contents: &str) -> Vec<&str> { vec![] }
                → cargo test → fails (returned empty vec, expected one line)

Step 3 (Lines): Add .lines() iteration
                → still fails (no filtering)

Step 4 (Filter):Add .contains() check
                → still fails (returns all lines, not just matches)

Step 5 (Push):  Store matching lines in a mutable vector
                → cargo test → PASSES (GREEN)

Step 6 (Clean): Refactor iterator chain, simplify
                → cargo test → still GREEN
```

Each step is verified by `cargo test`. The test never changes — only the
implementation evolves.

## Applying TDD in directions.json

When a task uses `kind: "lib-tdd"`, the `tdd_interface` embeds the test code
that the implementation agent writes first. The task's relationship to the TDD
cycle is:

| TDD Step | directions.json field | What the agent does |
|----------|----------------------|---------------------|
| RED | `tdd_interface.test_code` | Write the test verbatim, run `cargo test` — confirm failure |
| Stub | `tdd_interface.signature` | Write minimal implementation matching the signature, confirm test still fails behaviorally |
| GREEN | `changes[].guidance` | Implement the full logic, run `cargo test` until passing |
| Refactor | `changes[].guidance` | Clean up while `cargo test` stays green |
| Verify | `wiring_checklist` + `acceptance` | Confirm wiring and run full acceptance |

## Test Quality Checklist

A TDD test is a good specification when:

- [ ] It calls the function with concrete inputs
- [ ] It asserts concrete output with `assert_eq!` or similar
- [ ] The assertion would fail if the function returned the wrong value
- [ ] It covers at least one edge case (empty input, error state, boundary)
- [ ] It does NOT use `assert!(true)` or trivial always-pass assertions
- [ ] The test function name describes the behavior being tested

## Anti-Patterns to Avoid

- **Write implementation first, then test** — this produces tests that validate
  the implementation rather than specify the design. The test becomes a passive
  observer instead of an active contract.
- **Trivial test** — `assert!(true)` or "test calls function but doesn't check
  output." The test must be falsifiable: it must be possible for it to fail.
- **Test and implementation in separate tasks** — the implementation agent
  never sees the test, so the test can't drive the design. In this pipeline,
  both live in a single `lib-tdd` task.
- **Changing the test to match the implementation** — the test IS the
  specification. If the test is wrong, the specification is wrong. But in the
  normal TDD cycle, only the implementation changes.

## When NOT to Use This Pattern

- **CLI argument parsing** — the interface is defined by the framework (clap,
  structopt), not by a test
- **Config file generation** — I/O-heavy, hard to unit test
- **Cargo.toml edits** — not Rust code
- **I/O adapters** — database connections, HTTP clients, filesystem operations
- **main.rs wiring** — glue code that connects components
- **Any code where the interface is dictated by external constraints** rather
  than by the test

For these cases, use `kind: "direct"` (the default) with the existing
edit→check→fix loop.
