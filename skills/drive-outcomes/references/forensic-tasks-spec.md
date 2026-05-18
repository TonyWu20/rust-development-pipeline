# Forensic TASKS.md Format Specification

Extends the tasks-spec.md format with Outcome-Driven Development sections. The
TASKS.md is no longer just an implementation spec — it's a forensic record of
what was learned during exploration, which criteria were validated vs adjusted,
and why.

## New: Phase Metadata

```markdown
# Phase {N}: {Phase Name}
**Source branch:** feature/xxx
**Plan:** plans/phase-{N}/PHASE_PLAN.md
**Decisions:** plans/phase-{N}/DECISIONS.md

## Declared Fixtures
{List of fixture files declared by the user during the grill. Each entry includes
 the path and what it validates:}
- `fixtures/cu111/calc.check` — wavefunction records, eigenvalues
- `fixtures/cu111/calc.cell` — ionic positions, lattice vectors
```

## New: Success Criteria in lib-tdd tasks

Each lib-tdd task gains a `Success Criteria` section before the TDD interface:

```markdown
### TASK-{N}: {short description}
**Goal:** {G1 | G2 | ...}
**Files:** `path/to/file1.rs`
**Depends on:** {TASK-ID or "none"}
**Kind:** lib-tdd

**Success Criteria:**
- `parse("fixtures/cu111/calc.check")` yields 36 k-point records
  (Source: calc.check header, offset 0x00)
- `eigenvalues[0][0] == -14.523` ± 1e-6
  (Source: CASTEP source vion.F90:156, cross-validated with calc.pot_fmt)
- `max_residual(parsed, reference) < 1e-8`
  (Source: cross-validated against calc.pot_fmt ground truth)

**Test Interface:**
- **Test file:** `path/to/test_file.rs`
- **Test module:** {module name}
- **Test function:** `test_fn_name`
- **Test code:**
  ```rust
  #[test]
  fn test_fn_name() {
      // assertions anchored to success criteria
  }
  ```
- **Signature:** `pub fn foo(...) -> ...`
- **Expected behavior:** {what passing means}

**Changes:**
- **{create|modify|delete}** `path/to/file.rs`:
  {implementation approach}

**Acceptance:** {commands that run against real fixtures}
```

## Success Criteria Rules

Each criterion must be:

1. **Falsifiable** — must be possible for it to fail when the implementation is
   wrong. `result.len() == 36` passes this (wrong format → wrong count), but
   `result.is_finite()` does not.
2. **Anchored** — cites the source of the expected value
   (`(Source: calc.check header, offset 0x00)`). If no source can be cited, the
   criterion must still be concrete enough to detect wrong output.
3. **Specific** — concrete inputs and outputs. Not "parse correctly" but
   "`parse("fixtures/cu111/calc.check")` yields 36 k-point records."

## Format Rules

Same as tasks-spec.md, plus:

1. **Success Criteria** go immediately after `**Kind:**`, before the test interface.
2. **Test Interface** is renamed from "TDD Interface" to "Test Interface" to avoid
   confusion with the old TDD pattern.
3. **Declared Fixtures** at the top level list all fixtures that were declared
   during the grill session. Individual tasks reference fixture paths concretely
   in their success criteria.
4. Each criterion's `(Source: ...)` is part of the bullet text, not a separate
   field — markdown is self-validating.

## Exploration Notes (optional)

Tasks that went through exploration (vs. direct implementation) may include
an Exploration Notes section documenting what was learned:

```markdown
**Exploration Notes:**
- Initial criteria assumed header offset 0x00, but real data had a 12-byte
  version prefix. Adjusted to offset 0x0C.
- eigenvalues[0] expected -14.523, measured -14.520 — within tolerance.
  Adjusted tolerance from 1e-8 to 1e-6.
```
