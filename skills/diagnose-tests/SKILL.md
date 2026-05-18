---
name: diagnose-tests
description: Scans a Rust project's existing test suite for placebo test patterns (vacuous assertions, circular round-trip, unbounded thresholds, synthetic-only data). Produces a migration report to help projects adopt the Outcome-Driven Development (ODD) pipeline. Use when migrating from the old TDD pipeline, auditing test quality, or when the user says "/diagnose-tests", "audit my tests", "find placebo tests", or "how healthy are my tests?".
---

# Diagnose Tests

Audits a Rust project's existing test suite for placebo test patterns. Produces a
migration report listing which tests need to be rewritten under the ODD pipeline's
ground-truth anchoring requirements.

## Trigger

`/diagnose-tests [path]`

Where `[path]` is optional and defaults to the current repo root. If provided,
scans the test directory at the given path.

## How It Works

The skill scans the project's test files for known placebo patterns and compares
them against any fixture files that exist on disk. It does NOT modify any files —
only produces a report.

## Patterns Detected

### 1. Vacuous assertions
Tests that only check general properties, not concrete values:

- `assert!(x.is_finite())` — passes for any real number
- `assert!(x.is_ok())` — checks type, not value
- `assert!(x > 0.0)` — passes for any positive (wrong by 10^8 still passes)
- `assert_eq!(x.len(), N)` — checks shape, not content

### 2. Circular round-trip
Tests that construct synthetic data and round-trip through encode/decode:

- `parse(write(x)) == x` or `deserialize(serialize(x)) == x`
- These detect only asymmetric bugs — format misinterpretations survive

### 3. Unbounded thresholds
Numeric thresholds chosen without reference to ground truth:

- `max_residual < 10.0` where the real residual is 1e-6
- Any assertion with a threshold that has no cited source

### 4. Synthetic-only data
Tests that construct hand-crafted data matching the parser's own format
assumptions, rather than using real fixture files.

## Process

### Step 1: Discover test files

```bash
# Find test files by common naming patterns
fd -e rs '.+/(tests|test)/' 2>/dev/null
# Also check for inline test modules in src/
fd -e rs 'src/.+\.rs' 2>/dev/null
```

### Step 2: Scan for placebo patterns

For each test file found, read it and check for:
1. `assert!(<expr>.is_finite())` — vacuous
2. `assert!(<expr>.is_ok())` — vacuous (unless combined with a value check)
3. `parse(write` or `deserialize(serialize` — circular round-trip
4. `< threshold >` or `< .near(0.0)` without an accompanying source comment
5. `vec![0u8; N]` or similar blank synthetic data construction

### Step 3: Check for unused fixture files

```bash
# Look for potential fixture directories
fd --no-ignore -t d '(fixtures?|testdata|test-data|golden|references?)' 2>/dev/null

# List files in found fixture directories
fd --no-ignore -t f 'fixtures/' -0 2>/dev/null | xargs -0 ls -la 2>/dev/null
```

If fixture directories exist, check whether any test file references them (grep for
`fixtures` in test code). Report fixture files that exist but are not used.

### Step 4: Produce migration report

Write `notes/test-diagnostics.md` with:

```markdown
# Test Diagnostic Report

**Project**: {project name}
**Date**: {date}

## Summary

- **Total test files**: {N}
- **Tests with placebo patterns**: {N}
- **Fixture files not used**: {N}
- **Overall health**: Healthy / Needs work / Critical

## Placebo Tests Found

### 1. Vacuous assertions
| File | Line | Pattern | Severity |
|------|------|---------|----------|
| `src/foo.rs` | 42 | `is_finite()` | HIGH |

### 2. Circular round-trip
| File | Line | Pattern | Severity |
|------|------|---------|----------|
| `src/bar.rs` | 85 | `parse(write(x))` | HIGH |

### 3. Unbounded thresholds
| File | Line | Value | Severity |
|------|------|-------|----------|
| `src/baz.rs` | 120 | `residual < 10.0` | MEDIUM |

### 4. Synthetic-only data
| File | Line | Description | Severity |
|------|------|-------------|----------|
| `src/qux.rs` | 200 | Blank vec![0u8; 1024] | MEDIUM |

## Unused Fixture Files

| Fixture Path | Size | Last Modified |
|-------------|------|---------------|
| `fixtures/cu111/calc.check` | 5.2 MB | 2025-01-15 |

## Recommendations

{Concrete guidance: which tests to rewrite, which fixtures to use, what success
criteria to define.}
```

### Step 5: Report

Report to the user:

> "Test diagnostic complete. See `notes/test-diagnostics.md`.
>
> Found {N} placebo patterns across {M} files.
> {N} fixture files exist on disk but are not referenced in any test.
>
> Recommended migration path:
> 1. Review the report and fix HIGH severity items first
> 2. Declare fixture files in DECISIONS.md for future `/drive-outcomes` sessions
> 3. Run `/init-project` to set the repo constitution before adopting ODD stages"
