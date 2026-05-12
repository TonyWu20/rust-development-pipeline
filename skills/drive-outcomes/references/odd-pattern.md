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

## Upstream Audit Rule

If the algorithm formula has been independently validated against the reference
implementation and outputs still violate criteria, the next investigation round
MUST audit inputs before re-examining the algorithm.

**Trigger condition**: "algorithm validated" means the formula was checked against
a reference implementation or published derivation — not just against our own
pipeline output.

**Checklist** (work through in order):
1. Identify all inputs to the algorithm.
2. For each input, find the parser that produces it.
3. Check unit conventions at the parser boundary (Å⁻¹ vs Bohr⁻¹, Hartree vs eV,
   degrees vs radians).
4. Check file format assumptions (record size, endianness, field offset).

**Example**: USP/recpot parsers read `gmax` in Å⁻¹ but treated it as Bohr⁻¹.
The V_ion formula was correct. The fix was one line in each parser, not in the
algorithm. Multiple sessions were spent re-validating the correct formula before
the parser was audited.

### Conditional-Skip Audits

Formula-matching audits compare lines of code for structural equivalence. They
cannot detect a missing `if` guard — the formula on the executed branch matches;
what fails is the meta-question "under what conditions does this line execute?"

When auditing a reference implementation against our own, produce a
**conditional-skip table**:

| Reference line | Reference condition | Our line | Our condition |
|----------------|-------------------|----------|--------------|
| `reference.rs:42` | `if (fine_recip_grid_symmetric(n))` | `pipeline.rs:46` | unconditional |

Every `if` / `when` / `case` / early-return / guard clause in the reference
function must have a row. **Empty "Our condition" cells are red flags**,
requiring explicit justification ("safe because input X is always Y, verified
by test Z") or a fix to add the missing condition.

This catches the entire class of *absence* defects that line-by-line content
scans miss — guards that exist in the reference but not in our implementation.**

## Read/Write Symmetry

For file-format porting tasks, success criteria must cite BOTH the read code line
AND the matching write code line for each field whose unit or encoding is
non-obvious.

**Format**: `(Source: read: parser.rs:L42, write: writer.rs:L87)`

**Non-obvious fields**: unit conversions, endianness-sensitive values, packed bit
fields, fields whose meaning changes with a version flag.

**Why**: a parser that reads a field correctly but a writer that emits it in wrong
units produces a file that round-trips correctly but is wrong when consumed by an
external tool. Citing both sides pins the convention unambiguously.

## Discriminator Value Selection

When a criterion checks a numeric value, prefer probe values where correct and
incorrect implementations differ by ≥ 2×. Boundary values are brittle.

**Rule**: compute `ratio = |wrong_value / correct_value|`. If `ratio < 2`, the
criterion is a boundary value — flag it and choose a query point with a larger
discriminating ratio, or tighten the threshold to `correct_value ± tolerance`.

**Example**: correct V_ion ≈ -21 Ha, wrong V_ion = +82 Ha, ratio ≈ 4×.
A threshold of `V_ion < -10 Ha` is a good discriminator — it passes any correct
implementation and fails the typical incorrect one. `max_res < 100.0` when the
correct residual is ~1e-6 is a placeholder bound (see Placebo Taxonomy §3), not
a discriminator.

**Corollary**: `assert!(value == 52.92)` is verification (brittle to constant
updates). `assert!(value < threshold)` where the threshold is placed in the middle
of the "correct" regime is a probe — it passes under any correct implementation
and fails under the typical incorrect one.

## Classifying Prior-Session Numeric Claims

When loading prior investigation notes, classify every numeric claim before use.

| Class | Definition | Admissible as criterion? |
|-------|-----------|--------------------------|
| **EXTERNAL** | From a fixture file, published spec, or reference implementation output | Yes |
| **DERIVED** | Computed by our own pipeline (possibly buggy) | No — not without independent corroboration |
| **HYPOTHESIZED** | Inferred or estimated from scaling arguments | No |

**Classification procedure**: for each number, ask "where did this come from?"
Trace it to its origin. If the origin is our own code or a prior session's output,
it is DERIVED regardless of how it was phrased ("expected", "needed", "target").

**Only EXTERNAL claims may appear in `**Success Criteria:**` blocks.**

**Why this matters**: in the chemrust-hamiltonian debug session, prior notes
contained `V_coulomb = -79 (needed -183)` and `V_loc = +161 (needed +59)`. These
read as specifications but were DERIVED from earlier buggy computations. Using
them as criteria would have anchored the fix to wrong targets. Only
`V_eff − V_H − V_xc = -21 Ha` from `.pot_fmt` was EXTERNAL and admissible.

## Diagnostic Self-Verification

Diagnostic/comparison code has the same bug potential as production code — but
no failing test to catch it. A buggy diagnostic that emits plausible-looking
summary statistics is the most dangerous tool in a debug session: the agent
treats its output as empirical data and derives sound reasoning from false
premises.

Three patterns guard against this failure mode.

### Cross-Path Verification

Every diagnostic code path must be self-tested before its outputs are admitted
as evidence. The self-test queries the same point through **two structurally
independent code paths** and asserts agreement on ≥10 sample points.

**Structural independence** means the two paths differ in their indexing scheme,
iteration order, or formula derivation — not the same logic in different
syntax:

```python
# Path A: high-level diagnostic function
result_a = compute_v_ion(parsed_data)

# Path B: manual computation from first principles
result_b = manual_v_ion(parsed_data, formula="V_eff - V_H - V_xc")

assert abs(result_a - result_b) < 1e-6
```

A for-loop vs while-loop over the same index range is NOT independent. An
indexed access vs pointer-offset access is. A library function call vs
explicit formula expansion is.

**Why ≥10 samples**: off-by-one and wrong-offset bugs often manifest starting
at a specific array index. Sampling indices 0-9 reliably catches stride-offset
mismatches (e.g., stride-3 indexing reads wrong data starting at elements
0-2). Single-sample tests can miss these.

### Per-Point vs Summary Diagnostics

Summary statistics mask specific classes of diagnostic bug:

| Summary stat | What it masks |
|-------------|---------------|
| `mean` | Offset indexing — half wrong, half right yields approximately expected average |
| `max` / `min` | Single wildly-wrong point can be dismissed as anomaly rather than recognized as the signal |
| `count` / `len` | Shape-only — all points can be wrong but count matches |
| `at index (i,j,k)` | A wrong coordinate label sends investigation to the wrong physical site, as in the chemrust-hamiltonian session |

**Rule**: any diagnostic that emits summary statistics must also emit the full
per-point dump, or the agent must have written an independent brute-force loop
that confirms the summary is correct. Summaries without per-point backing are
inadmissible as empirical evidence.

### Suspect the Diagnostic First

When summary statistics conflict with physical or topological intuition, the
diagnostic is the FIRST thing to suspect, not the code under test.

| Observation | Likely diagnostic defect |
|-------------|-------------------------|
| Wrong sign | Indexing the wrong field, sign convention reversed |
| Order-of-magnitude error | Wrong units (Ha vs eV, Bohr vs Å), scale factor missed |
| Intermittent pattern | Stride or offset indexing bug (some correct, some wrong) |
| Coordinate at symmetry-violating site | Index mapping bug — reported location is not the actual location of the residual |
| Reported max matches prior DERIVED value | Diagnostic is reproducing prior (buggy) output rather than computing fresh |

**Do not reason about why the physics could produce the wrong value until the
diagnostic self-test passes.** The diagnostic is part of the debug surface and
is wrong by default. Treat every number it emits as a claim to be verified,
not as data to reason from.
