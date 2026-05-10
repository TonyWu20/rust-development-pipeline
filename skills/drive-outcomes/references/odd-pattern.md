# ODD Pattern: Outcome-Driven Development

This document defines the Outcome-Driven Development (ODD) workflow that replaces
the TDD (ch12-04) pattern. TDD's "test IS the specification" philosophy rewards
process compliance over outcome correctness — agents write tests that look right
(pass/vacuous) but provide zero protection against format-level bugs. ODD
reorients: **tests are hypotheses about outcomes, anchored to something outside
the black box.**

## The ODD Progression

```
Goal → Criteria → Tests → Outcomes
```

1. **Goal** — intent, direction, preference. Not yet measurable: "build a parser
   for CASTEP .check files."
2. **Criteria** — what winning looks like. Measurable conditions with provenance:
   "parse(calc.check) yields 36 k-point records" (Source: .check header, offset 0x00).
3. **Tests** — hypotheses about outcomes. Each test says "if the implementation is
   correct, outcome X occurs under condition Y."
4. **Outcomes** — observed results. Pass/fail against criteria. Gaps drive iteration.

## Core Principle: Anchor to Ground Truth

Every test assertion must be falsifiable against something **external to the code
under test**. The test must be capable of failing when the implementation is wrong.

### Good assertions (anchored externally)

```rust
// GOOD: Anchored to real fixture file — parse a known .check and verify specific values
let parsed = parse_cell("fixtures/cu111/calc.cell").unwrap();
assert_eq!(parsed.num_ions, 16);  // Source: calc.cell, line 42

// GOOD: Cross-validated against reference output
let residual = max_residual(parsed_density, reference_density);
assert!(residual < 1e-8, "Residual {}", residual);
// Source: CASTEP's own residual for this system is 2.3e-9
```

### Placebo assertions (NOT anchored)

```rust
// PLACEBO: Passes for any real number — only fails on NaN
assert!(value.is_finite());

// PLACEBO: Circular round-trip — parser bugs survive if symmetric
assert_eq!(parse(write(x)), x);

// PLACEBO: Loose bound chosen without source
assert!(residual < 10.0);  // Real residual is 2.3e-9

// PLACEBO: Shape-only — wrong encoding can still produce 36 elements
assert_eq!(result.len(), 36);
```

## Placebo Test Taxonomy

These patterns look like real tests but provide zero protection. The pipeline
must detect and flag every one of them.

### 1. Vacuous assertions

Pass for any real number. Test the type system, not the value.

| Pattern | It passes when | Real failure case |
|---------|---------------|-------------------|
| `assert!(x.is_finite())` | x is any finite f64 | x is NaN or Inf |
| `assert!(x.is_ok())` | Result is Ok | Result is Err |
| `assert!(x > 0.0)` | x is any positive | x is negative (but wrong by 10^8 still passes) |
| `assert_eq!(x.len(), N)` | length matches | Content is garbage but N elements present |

**Fix**: Replace with value assertions that reference a known-good source.

### 2. Circular round-trip

Construct synthetic data, serialize, parse, assert equivalence. Only detects
asymmetric encoding/decoding bugs — format misinterpretations survive.

```rust
// What the agent writes (PLACEBO):
let original = create_synthetic_data();
let bytes = encode(&original);
let decoded = decode(&bytes);
assert_eq!(original, decoded);

// What passes: encode adds incorrect header, decode reads it back wrong → symmetric = green
// What fails: TRWTF is the header is 12 bytes, not 16 — but round-trip can't tell
```

**Fix**: Parse a real fixture file produced by the reference implementation.
Compare parsed values against known-good expected values, not against a
circular encode/decode.

### 3. Placeholder bounds

A numeric threshold written without reference to ground truth. The agent chooses
a number it knows the code will pass — typically very loose.

```rust
// PLACEBO: Passes for any reasonable output
assert!(residual < 10.0);  // Real residual is 2.3e-9

// What happened in chemrust-hamiltonian Phase-03:
// CASTEP's own potential residual was ~2.3e-8 Hartree
// The test asserted max_residual < 10.0 Hartree
// The code produced 34 Hartree — still "passed"
```

**Fix**: Every numeric assertion must include `(Source: ...)` citing where the
expected value, bound, or tolerance came from:
- A fixture file: `(Source: calc.pot_fmt header has residual=2.3e-8)`
- Reference implementation: `(Source: CASTEP vion.F90:156, formula sqrt(4π))`
- Published spec: `(Source: CASTEP 20.1 user guide, p. 42)`

### 4. Synthetic data mirroring parser expectations

Hand-crafted binary/text data that matches what the parser expects. By
construction, these can never fail on format bugs:

```rust
// PLACEBO: Synthetic data matches parser's own format assumptions
let data = vec![0u8; 1024];  // Parser happens to read 1024 bytes at offset 0
assert_eq!(parse(&data).offset_0_value(), 0);  // Always passes

// Real fixture has offsets that reveal format misinterpretations
// e.g., real header has 3× (tag + dims), synthetic has 1× (tag + dims)
```

**Fix**: Use real fixture files when they exist. If no fixtures exist, the success
criteria must still cite concrete expected values from a spec, not from the
implementation being tested.

## Fixture Anchoring Protocol

When fixture files exist, the pipeline must use them. The user declares fixture
paths during the grill interview; these are recorded in DECISIONS.md.

### Rule
If fixture files exist for the functionality being implemented, tests MUST read
from those fixtures and assert against known-good values.

If no fixture files exist, tests MUST assert against concrete expected values
with a cited source (spec document, reference implementation, published formula).

### What to extract from fixture files
- **Header fields**: record counts, dimension sizes, format version
- **Known values**: specific array elements at known positions
- **Cross-validation**: compare output against reference implementation's output
  for the same input — `max_residual(our_output, reference_output) < 1e-8`

## The ODD Cycle in the Pipeline

Each lib-tdd task follows this cycle, replacing the old TDD red-green-refactor:

| ODD Step | What happens | Artifact |
|----------|-------------|----------|
| **Define criteria** | Read fixture files, extract concrete expected values, write success criteria with source citations | Success Criteria in TASKS.md |
| **Explore** | Write exploratory snippets against real fixtures — validate that criteria are achievable | Exploratory code (temp) |
| **Adjust** | If real data surprises us, adjust criteria before committing to them | Updated Success Criteria |
| **Implement** | Refactor exploratory code into proper module positions, implement production code | Production code |
| **Verify** | Run acceptance against real fixtures, measure outcomes against criteria | Outcomes record |
| **Forensic record** | Write what was learned: which criteria surprised us, what we adjusted, why | Forensic TASKS.md |

### Acceptance criteria structure

Each acceptance command should be falsifiable against ground truth:

```bash
# GOOD: Exit code based on cross-validation
cargo test -p my-crate -- test_against_reference

# PLACEBO: No meaningful failure condition
cargo test -p my-crate  # passes if all tests use vacuous assertions
```

## Success Criteria Format in TASKS.md

```markdown
### TASK-N: Parse wavefunction records
**Kind:** lib-tdd
**Goal:** Reproduce CASTEP wavefunction parse from .check file

**Success Criteria:**
- `parse("fixtures/cu111/calc.check")` yields 36 k-point records
  (Source: calc.check header, offset 0x00)
- eigenvalues[0][0] == -14.523 ± 1e-6
  (Source: CASTEP source vion.F90:156, cross-validated with calc.pot_fmt)
- max_residual(parsed, reference) < 1e-8
  (Source: cross-validated against calc.pot_fmt ground truth)

**Test file:** `tests/wave_parser_tests.rs`
...
```

Each success criterion must be:
- **Falsifiable**: must be possible for it to fail
- **Anchored**: cites source of expected value
- **Specific**: concrete inputs and outputs, not general properties

## When NOT to Use This Pattern

Same as TDD: CLI argument parsing, config file generation, Cargo.toml edits,
I/O adapters, main.rs wiring. Use `kind: "direct"` instead.
