---
name: debug-outcomes
description: Debug an existing fixture-anchored system that passes its acceptance test but produces wrong physics or wrong output. Classifies prior investigation notes, establishes external anchor criteria, applies upstream-audit rule, implements fix with discriminator-value tests, and captures resolution. Use when the user says "/debug-outcomes", "debug this failure", "the test passes but the output is wrong", or describes a symptom in a system that already has fixture files and a passing (but loose) acceptance test.
---

# Debug Outcomes

Handles the **debug shape**: an existing fixture-anchored system whose acceptance
test passes but whose output violates physics or known-good reference values. This
is distinct from `/drive-outcomes` (new development against a phase plan) and
`/diagnose-tests` (static audit). The entry point is a symptom, not a plan file.

The key risks in this shape are:
1. Re-validating a correct algorithm instead of auditing its inputs.
2. Treating DERIVED intermediates from prior (buggy) sessions as ground truth.
3. Writing a tight test after the fix rather than before — losing the red step.

## Trigger

`/debug-outcomes "<symptom>"`

Where `<symptom>` is a free-text description of the observed wrong output
(e.g., `"V_ion = +82 Ha at atom site, expected ≈ -21 Ha"`).

## Pre-flight

```bash
cat CONTEXT.md 2>/dev/null || echo "NO_CONTEXT_MD"
fd --no-ignore -t f . fixtures/ 2>/dev/null | head -5
```

- If CONTEXT.md is absent: stop and prompt `/init-project` first.
- If no fixture files are discoverable: redirect to `/drive-outcomes` — this skill
  requires external ground truth. Without fixtures there is no anchor.

## Command-line Tools

- use `fd` instead of `find`
- use `rg` instead of `grep`

## References

- ODD pattern (placebo taxonomy, fixture anchoring, upstream audit rule,
  discriminator value selection): `${CLAUDE_PLUGIN_ROOT}/skills/drive-outcomes/references/odd-pattern.md`
- Forensic TASKS.md format (if fix is large enough to warrant task breakdown):
  `${CLAUDE_PLUGIN_ROOT}/skills/drive-outcomes/references/forensic-tasks-spec.md`

## Output

- `notes/debug/<slug>/INVESTIGATION.md` — prior-note classification
- `notes/debug/<slug>/CRITERIA.md` — external anchor criteria
- `notes/debug/<slug>/DIAGNOSTIC_SELFTEST.md` — diagnostic self-test results
- `notes/debug/<slug>/DIVERGENCE_SURFACE.md` — divergence-surface enumeration
- `notes/debug/<slug>/RESOLUTION.md` — root cause, fix location, reclassified claims
- `notes/failure-patterns.md` — appended entry

## Process

### Step 1: Setup

```bash
echo "debug-outcomes" > .claude/.current_stage
date +%s%3N > .claude/.session_start
SLUG="debug-$(date +%Y%m%d-%H%M)"
mkdir -p notes/debug/$SLUG
```

Read CONTEXT.md, ADRs, `notes/failure-patterns.md`, and `odd-pattern.md`.

### Step 2: Classify Prior Investigation Notes

Scan `notes/` for any investigation notes, session logs, or plan files referencing
the symptom:

```bash
rg -l "<symptom-keyword>" notes/ 2>/dev/null
```

For every numeric claim found in those files, classify it and record in
`notes/debug/$SLUG/INVESTIGATION.md`:

| Class | Definition | Admissible as criterion? |
|-------|-----------|--------------------------|
| **EXTERNAL** | From a fixture file, published spec, or reference implementation output | Yes |
| **DERIVED** | Computed by our own pipeline (possibly buggy) | No — not without independent corroboration |
| **HYPOTHESIZED** | Inferred or estimated from scaling arguments | No |

Classification procedure: for each number, ask "where did this come from?" Trace
it to its origin. If the origin is our own code or a prior session's output, it
is DERIVED regardless of how it was phrased ("expected", "needed", "target").

Only EXTERNAL claims may become success criteria in Step 3.

**Memory citation rule**: claims from prior sessions' memory entries
auto-classify as DERIVED unless they carry all three of:
1. **Verification granularity** — what level of detail was verified
   (per-point formula, full pipeline against fixture, signature comparison, etc.)
2. **Citation** — `file:line` in the reference implementation, reachable in
   ≤60 seconds
3. **Counter-example / test-fixture scope** — what input distribution exercised
   the claim (without this, "verified" only means "verified on one input")

Without these three fields, a memory entry is a hypothesis, not evidence.

### Step 3: Establish External Anchor Criteria

Discover fixture files:

```bash
fd --no-ignore -t f . fixtures/ 2>/dev/null | sort
```

For each fixture file relevant to the symptom, extract concrete expected values
directly from the file — not from prior notes. Write to
`notes/debug/$SLUG/CRITERIA.md`:

```markdown
# Anchor Criteria: <symptom-slug>

## Fixture Files
- `fixtures/<path>` — <what it contains>

## Success Criteria
- <assertion> (Source: <fixture-path>, <field or offset>)
- <assertion> (Source: <reference-impl-file>:<line>)
```

Each criterion must be EXTERNAL and falsifiable. If no EXTERNAL anchor can be
established, stop and tell the user — the bug cannot be debugged without ground
truth.

### Step 4: Divergence Surface Enumeration

Before testing any hypothesis, enumerate every place the local pipeline could
plausibly disagree with the reference implementation for the observed symptom
class. Write to `notes/debug/$SLUG/DIVERGENCE_SURFACE.md`.

Use these generic divergence-surface categories as a starting point
(project-specific items supersede where applicable):

- **Data layout / axis ordering** — Fortran vs row-major indexing in arrays
- **Normalization / scaling conventions** — do round-trip factors cancel?
- **Sign / direction conventions** — forward/inverse FFT sign, phase convention
- **Boundary / edge-case handling** — conditional guards in the reference
  (every `if` / `when` / `case` / early-return)
- **Unit conversion at any boundary** — eV ↔ Ha, Å ↔ Bohr, inverse-length conv.
- **Parser precision / offset assumptions** — record size, header offset,
  endianness
- **Decomposition / parallel artifacts** — per-node vs gathered representation
- **Diagnostic comparison code** — indexing layout of the diagnostic itself

For each item, classify as:
- **Ruled out by anchor X** — the external anchor from Step 3 eliminates this
  possibility (cite which anchor)
- **To be tested in Step 7** — not yet ruled out; the Loose-then-Tighten cycle
  will investigate

**Items cannot be ruled out by prior-session memory unless that memory carries
verification granularity, citation (file:line), and counter-example/scope.**
A prior memory that says "X was verified" without these three fields is
DERIVED and cannot eliminate a divergence-surface item.

Goal: breadth-first enumeration before diving deep on any single item.
This prevents depth-first hypothesis chaining from prior sessions' biases.

### Step 5: Diagnostic Verification

Before trusting any diagnostic or comparison code in downstream steps, verify
every diagnostic code path against the external anchors from Step 3.

1. **Enumerate diagnostics** — list every diagnostic script, comparison
   function, and analysis tool that downstream steps will use. Write to
   `notes/debug/$SLUG/DIAGNOSTIC_SELFTEST.md`.

2. **Self-test each diagnostic** — for each enumerated path, query ≥10 sample
   points through **2 structurally independent code paths** and assert
   agreement at every point:

   ```python
   # Path A: high-level diagnostic function being verified
   result_a = compute_v_ion(parsed_data)
   # Path B: manual computation from first principles
   result_b = manual_v_ion(parsed_data, formula="V_eff - V_H - V_xc")
   assert abs(result_a - result_b) < 1e-6
   ```

   Independence means different indexing scheme, iteration order, or formula
   derivation — not the same logic in different syntax.

   Record pass/fail per sample point in `DIAGNOSTIC_SELFTEST.md`.

3. **If any sample point disagrees** — the diagnostic code has a bug. Fix the
   diagnostic before proceeding to Step 6. Do NOT interpret the diagnostic
   output; the diagnostic is part of the debug surface and is wrong by default.

4. **Sanity-check against physical intuition** — before trusting any
   diagnostic output, compare against coarse physical expectation:
   - Does the reported magnitude pass a smell test?
     (e.g., V_ion = +82 Ha when V_eff - V_H - V_xc ~ -21 Ha)
   - Is the sign physically plausible for the given system?
   - Is the spatial coordinate plausible?

   When diagnostic output conflicts with intuition, treat the diagnostic as
   the likely error source. Reject any diagnostic whose output cannot be
   reproduced by at least one independent computation path.

   Reference: `odd-pattern.md` (Diagnostic Self-Verification section) for the
   full pattern description and rationale.

### Step 6: Upstream Audit Gate

Ask the user explicitly:

> "Has the algorithm formula been independently validated against the reference
> implementation (not just against our own pipeline output)?"

- **Yes** → upstream-audit mode: Step 7 targets parsers, unit conversions, and
  file format — not the algorithm. The algorithm is already correct; the bug is
  in its inputs.
- **No** → algorithm-validation mode: Step 7 validates the formula first.

This gate enforces the Upstream Audit Rule from `odd-pattern.md`: if the algorithm
has been verified and outputs still violate criteria, re-examining the algorithm
wastes sessions. The bug is upstream.

In upstream-audit mode, enumerate all inputs to the algorithm and check each:
1. Which parser produces this input?
2. What unit convention does the reference implementation use at the read boundary?
3. Does the parser convert at read time, or does the caller convert?
4. Find BOTH the read code line AND the write code line in the reference
   implementation (Read/Write Symmetry rule from `odd-pattern.md`).
5. **Conditional-skip table** — produce a table mapping every `if`/`when`/
   `case`/early-return in the reference function to our implementation's
   handling. Empty "Our condition" cells are red flags requiring explicit
   justification ("safe because input X is always Y, verified by test Z")
   or a fix to add the missing condition.

   Reference: `odd-pattern.md` (Conditional-Skip Audits section) for the
   full table format and rationale.

### Step 7: Loose-then-Tighten

0. **Diagnostic check** — if any diagnostic in use emits only summary
   statistics (no per-point backing), report to the user:

   > "The diagnostic only emits summary statistics. Should I write a
   > brute-force per-point comparison loop to get ground-truth data? If you
   > know what specific coordinates or pattern to target, tell me."

   If the user provides guidance, follow it. If the user agrees or doesn't
   know, write a brute-force per-point sweep that dumps every data point
   through a simple independently-written loop. Write the output to
   `notes/debug/$SLUG/PER_POINT_DUMP.md`.

1. **Run loose**: execute the existing acceptance test as-is. Record the actual
   observed value (e.g., `max_residual = 103.4 Ha`).

2. **Observe**: compare against EXTERNAL anchor criteria from Step 3. Compute
   discrepancy magnitude and direction.

3. **Write a tight test** that fails at the observed wrong value and passes only
   at the correct value. Apply the Discriminator Value Selection rule from
   `odd-pattern.md`: the threshold must be placed such that correct and incorrect
   implementations differ by ≥ 2×. Boundary values are brittle.

   ```rust
   // TIGHT: correct ≈ -21 Ha, wrong = +82 Ha → ratio ≈ 4×
   // threshold at -10 Ha gives clear binary signal
   assert!(v_ion < -10.0, "V_ion = {} Ha (expected < -10 Ha)", v_ion);
   // Source: Cu111_CO.pot_fmt, V_eff − V_H − V_xc = -21 Ha
   ```

4. **Confirm the tight test fails** on the current (broken) code before
   implementing any fix. If it passes, the threshold is wrong — tighten further.

5. **Brute-force guard** — after every 2 full cycles through sub-steps 1-4
   without producing a new artifact file in `notes/debug/$SLUG/`, stop and
   report to the user:

   > "I've cycled through Loose-then-Tighten twice without a breakthrough.
   > Current state: {observed values, hypotheses so far}.
   > Next step: brute-force sweep to find the discrepancy pattern.
   > Any insight on what to target, or should I dump everything?"

   If the user guides, follow guidance. Otherwise, write a brute-force
   per-point loop that dumps raw data with zero aggregation to
   `notes/debug/$SLUG/BRUTE_FORCE_DUMP.md`. Use the raw dump to identify
   the discrepancy pattern (e.g., "every 3rd point is wrong" → stride-3
   indexing bug), then return to sub-step 2 with the corrected understanding.

6. **Decompose the residual** — if the failing observable is a sum of multiple
   components (e.g., V_eff = V_H + V_ion + V_xc), each component should have
   an independent EXTERNAL anchor. Write tight tests per-component, not just
   at the sum. Residuals are attributable component-by-component, not bundled.

### Step 8: Implement Fix (edit→check→fix)

Scope the fix to the upstream component identified in Step 6 (parser, unit
conversion, file format) or the algorithm if in algorithm-validation mode.

Standard loop:
- Apply change
- `cargo check --workspace 2>&1`
- Fix compiler errors
- Run the tight test from Step 7 — it must now pass
- Run the full acceptance suite — no regressions

Auto-review before commit:
1. **Diff check** — only files in scope (the upstream component)
2. **Intent check** — matches the component identified in Step 6
3. **Ground-truth check** — tight test uses EXTERNAL anchor values, not DERIVED
4. **Acceptance check** — all commands pass
5. **Source-verify subagent claims** — any factual claim drawn from a subagent
   summary must be re-verified by reading the cited source directly before
   acting. If the claim contradicts observed numerical evidence, the empirical
   evidence wins and the claim is downgraded to HYPOTHESIZED.

Commit: `fix(<component>): <symptom-slug> — <root-cause-one-line>`

### Step 9: Resolution Capture

Write `notes/debug/$SLUG/RESOLUTION.md`:

```markdown
# Resolution: <symptom-slug>

**Symptom**: <original symptom text>
**Root cause**: <one sentence>
**Fix location**: <file:line>
**Fix description**: <what changed>
**Anchor criteria used**: <list EXTERNAL claims from Step 3>
**Prior notes reclassified**:
- "<claim>" — reclassified from EXTERNAL to DERIVED because <reason>
**Date**: <ISO date>
```

Append a summary entry to `notes/failure-patterns.md` (create if absent):

```markdown
## <date>: <symptom-slug>
**Root cause**: <one sentence>
**Fix**: <file:line>
**Pattern**: <upstream-unit-mismatch | algorithm-error | format-assumption | ...>
```

Update any open investigation notes that reference this symptom: append a
RESOLVED section with a pointer to `RESOLUTION.md`.

### Step 10: Report

```bash
CLAUDE_PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}" CLAUDE_PROJECT_DIR="${CLAUDE_PROJECT_DIR}" \
  uv run --directory "${CLAUDE_PLUGIN_ROOT}" python \
  "${CLAUDE_PLUGIN_ROOT}/scripts/eval-session-metrics.py" debug-outcomes
```

> "Debug session complete.
>
> Root cause: {root-cause}.
> Fix: {file:line}.
> Tight test anchored to: {fixture-path}.
> Resolution recorded at notes/debug/{slug}/RESOLUTION.md.
>
> {N} prior-note claims reclassified (DERIVED/HYPOTHESIZED → not used as criteria).
>
> Next step: `/make-judgement` if the fix touched multiple components."

## Boundaries

**Will:**
- Classify every numeric claim from prior notes before using any as a criterion
- Require at least one EXTERNAL anchor before writing any success criterion
- Apply the upstream audit gate before touching algorithm code
- Confirm the tight test fails on broken code before implementing the fix
- Capture resolution with reclassified claims listed explicitly
- Verify diagnostic code via cross-path self-test (≥10 samples, 2 independent paths) before trusting its output
- Suspect the diagnostic first when output conflicts with physical intuition
- Trigger brute-force sweep when Loose-then-Tighten stalls without producing artifacts (report to user, ask for guidance)
- Re-verify factual claims from subagent summaries by reading cited sources
  directly before taking action on them

**Will not:**
- Accept DERIVED or HYPOTHESIZED values as success criteria
- Skip the upstream audit gate when the algorithm has been previously validated
- Write the tight test after the fix (that loses the red step)
- Restate `odd-pattern.md` content — references it by path
- Trust diagnostic output without cross-path self-test verification
- Spend excessive iterations in Loose-then-Tighten without producing empirical artifacts or consulting the user
- Accept subagent summaries as authority without source verification
