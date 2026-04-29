# Fix Plan: enrich-plan-judge — 4 Categories of Detection Gaps (Issue #9)

## Context

After the `enrich-plan-judge` skill approved a 12-task MVP plan for `rust-workspace-map`, execution left **38 errors** (34 clippy + 4 compile). The judge caught 2 blocking issues but missed 4 categories of flaws.

**Concrete root cause**: `sd -F` exits 0 even when the `before` pattern is not found. When TASK-1 modified lib.rs and auto-fixes shifted content, TASK-8's compiled `sd` script ran successfully but applied zero changes. The verification hook ran `cargo check`, which passed because the old code still compiled. TASK-8 was marked PASSED but its `build_map` function was never added.

---

## Changes

### File 1: `skills/enrich-plan-judge/SKILL.md` (primary)

#### 3A.2 — New: Lint attribute detection (addresses Cat-3, Cat-4)

Insert after Step 3A (before Step 3B). The judge reads `Cargo.toml` and crate roots:

```markdown
**A.2 Lint enforcement detection**

Check the target crate for lint attributes that turn warnings into errors:

```bash
rg -n '#!\[(warn|deny|forbid)\(.*(clippy|warnings)' src/lib.rs src/main.rs 2>/dev/null
rg -A5 '\[lints\.clippy\]' Cargo.toml 2>/dev/null
```

Record as `LINT_ENFORCEMENT`:
- `#![warn(clippy::pedantic)]` → all generated code MUST pass `cargo clippy -- -D warnings`. `cargo check` alone is INSUFFICIENT.
- `#![deny(warnings)]` or `#![forbid(warnings)]` → any warning is a hard compile error.
- `[lints.clippy]` in Cargo.toml enabling pedantic → same treatment.
```

#### Step 3B — Modified: Acceptance criteria based on LINT_ENFORCEMENT

Change (line 93):
```
- `cargo check -p crate` is sufficient for non-behavioral changes
```
to:
```
- `cargo check -p crate` is sufficient for non-behavioral changes in crates WITHOUT lint enforcement
- **If LINT_ENFORCEMENT detected:** `cargo clippy -p crate -- -D warnings` is REQUIRED
- For tasks adding or modifying `use` statements: prefer `cargo clippy -p crate` to catch unused imports
```

#### 3B.2 — New: Cross-task before-block staleness check (addresses Cat-1)

Insert after the before-block spot-check paragraph. The judge simulates forward application:

```markdown
**3B.2 Cross-task before-block staleness**

Read `[dependencies]` from the plan. For each task, identify files that BOTH this task and at least one dependency touch.

For each overlap — the before-block was verified against HEAD, but at execution time dependencies have already modified the file. Simulate:

1. Start with HEAD file content (`git show HEAD:<file>`)
2. Apply each dependency's `after` blocks sequentially (substitute `before` → `after`)
3. Result is the "expected state" when this task runs
4. **Verify each before-block exists in expected state**: pick a 40-80 char excerpt, check via substring match
5. If NOT found → **the before-block is stale**. Correct it to match the accumulated state.

Fallback (if full simulation too complex): pairwise comparison — does the dependency's `after` alter/remove the region the dependent's `before` targets? Flag high-probability overlaps.
```

#### 3B.3 — New: Builder API usage check (addresses Cat-2)

Insert after 3B.2:

```markdown
**3B.3 Builder pattern check**

If any `after` block uses builder chains (`.builder()` + setters + `.build()`):

1. **bon typestate**: if the project depends on `bon`, methods that transition the state machine prevent subsequent setters from being available. All optional setters MUST come before state-transitioning methods.

2. **General ordering rules** (all frameworks):
   - Required fields via constructor first
   - Optional setters next
   - State-transitioning methods after optional setters
   - `.build()` / `.call()` last, nothing after it

3. **Red flags**: any setter called AFTER a state-transitioning method is likely incorrect. Flag it — the dry-run will confirm.

If uncertain about a builder's state machine, note a CONTEXT_GAP.
```

#### Step 5 — Modified: Sequential verification + clippy

Replace Step 5 items 2-3 (lines 144-152). Key changes:

1. **Apply tasks in dependency order, verifying before-blocks at each step** (not all-at-once)
2. **Before each change**: verify the before-block excerpt exists in the file via `rg -F`
3. **After each change**: verify the after-block excerpt exists (confirms `sd` matched and applied)
4. **Compile gate**: if LINT_ENFORCEMENT → `cargo clippy --workspace -- -D warnings`; else `cargo check`
5. **Always also run**: `cargo clippy --workspace -- -W unused -W clippy::pedantic`
6. **Revision loop add**: stale before-block, clippy warnings, builder violations, unused imports

#### Step 6 — Modified: Report new findings

Add to the "Present to the user" list:
```
- Whether LINT_ENFORCEMENT was detected and how acceptance criteria were adjusted
- Any cross-task before-block staleness corrections made
- Any builder ordering corrections made
```

### File 2: `skills/enrich-plan-gather/SKILL.md` (secondary)

#### Step 2 — Modified: Record lint attributes in codebase-state

In "Record current state per file" (lines 152-160), add:
```
- **Lint enforcement**: any `#![warn(...)]`, `#![deny(...)]`, `#![forbid(...)]` at file top. Record exact attributes.
```

#### Step 4 — Modified: Acceptance criteria guidance

After the acceptance array template (lines 288-294), add:
```markdown
**Acceptance criteria guidance:**
- If `codebase-state.md` records lint enforcement (e.g., `#![warn(clippy::pedantic)]`), use `cargo clippy -p <crate> -- -D warnings` instead of `cargo check`
- For tasks that add or modify `use` statements, prefer `cargo clippy` to catch unused imports
```

---

## Verification

1. Re-run the MVP plan through `/enrich-plan-gather` and `/enrich-plan-judge` on `rust-workspace-map`:
   - Judge detects `#![warn(clippy::pedantic)]` in lib.rs → adjusts acceptance criteria
   - Sequential dry-run catches TASK-8's stale before-blocks before execution
   - Clippy runs on generated "after" blocks during dry-run
   - Bon builder ordering checked in TASK-9's Config builder chain
2. Lighter test: run the judge on a small test plan with a known before-block staleness (task A changes a file, task B's before-block references old content) → verify detection
