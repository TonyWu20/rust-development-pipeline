---
name: drive-outcomes
description: Merged Stage 1+2 — define success criteria, explore against real fixtures, validate, implement, and produce a forensic record. One continuous session with a checkpoint in the middle. Replaces /elaborate-plan + /explore-implement. Use when the user says "/drive-outcomes <plan-path>", "drive the outcomes for this phase", after /init-project completes, or when a phase plan is ready for ODD-driven implementation.
---

# Drive Outcomes

Merges outcome-definition (Stage 1) and implementation (Stage 2) into one
continuous session with a checkpoint. This eliminates cold-start information loss
between planning and implementation — the agent that validates criteria against
real data is the same agent that implements production code.

Session A (define + explore) produces a forensic TASKS.md. The user reviews and
may `/clear` or continue. Session B (implement in worktree) reads that artifact,
refactors exploratory snippets into production code, and commits.

## Trigger

`/drive-outcomes <plan-path>`

Where `<plan-path>` is the path to `PHASE_PLAN.md` (the output of `/init-project`
or `/next-phase-plan`).

## Pre-flight

The target project MUST have a CONTEXT.md (produced by `/init-project`). If none
exists, prompt the user to run `/init-project` first and stop.

## Command-line Tools

- use `fd` instead of `find`
- use `rg` instead of `grep`

## Output

- `notes/plans/<phase-slug>/DECISIONS.md` — design decisions from the grill
- `notes/plans/<phase-slug>/TASKS.md` — forensic task breakdown with success criteria

## Process

### Session A: Define + Explore

#### Step 1: Setup

```bash
# Set stage marker and session start for metrics tracking
echo "drive-outcomes" > .claude/.current_stage
date +%s%3N > .claude/.session_start

# Determine phase slug from plan path
PHASE_SLUG=$(basename $(dirname <plan-path>))
mkdir -p notes/plans/$PHASE_SLUG

# Ensure pipeline artifact directories are gitignored
grep -qx '.pipeline-worktrees/' .gitignore 2>/dev/null || echo '.pipeline-worktrees/' >> .gitignore
grep -qx '.claude/' .gitignore 2>/dev/null || echo '.claude/' >> .gitignore
```

#### Step 2: Load Context

Read the constitution, plan, deferred items, and failure patterns:

```bash
# Read the constitution
cat CONTEXT.md
cat CONTEXT-MAP.md 2>/dev/null || echo "NO_CONTEXT_MAP"
fd -e md . docs/adr/ 2>/dev/null | sort | while read f; do
  echo "=== $f ===" && cat "$f" && echo ""
done

# Read the plan
cat <plan-path>

# Read deferred improvements from prior phases
fd deferred.md notes/pr-reviews/ | while read f; do echo "=== $f ==="; cat "$f"; done

# Read failure patterns
cat notes/failure-patterns.md 2>/dev/null || echo "No failure patterns catalog yet"

# Read the ODD pattern reference
cat "${CLAUDE_PLUGIN_ROOT}/skills/drive-outcomes/references/odd-pattern.md"
```

#### Step 3: Grill — Goals, Criteria, and Ground Truth

Launch a grill-me subagent that interviews the user about:
1. **Goals**: What is this phase trying to achieve?
2. **Fixture files**: What real data files exist for the target functionality?
   Ask explicitly. If no fixtures exist, criteria must still cite concrete expected
   values from a spec or reference implementation.
3. **Success criteria**: For each goal, what would winning look like? What concrete
   values can be extracted from fixtures?
4. **Architecture decisions**: Crate boundaries, type choices, patterns — but
   focused on outcomes, not implementation tactics.
5. **Domain language**: Validate terms against CONTEXT.md. Update CONTEXT.md inline.

The agent references `odd-pattern.md` for placebo test detection and fixture
anchoring protocol. It does NOT discuss implementation details (those are discovered
in Steps 5-6).

Output: `notes/plans/<slug>/DECISIONS.md` with:
- Declared fixture paths (with descriptions)
- Success criteria (per-goal, concrete, source-cited)
- Architectural decisions
- Domain terms validated

#### Step 4: Explore — Validate Criteria Against Real Data

For each set of criteria declared in the grill:
1. If fixture files exist, write exploratory snippets that read them and assert
   against the declared criteria.
2. Run them. If they fail:
   - Criteria may be wrong (wrong expected value, wrong tolerance) — adjust and
     document why.
   - The format may be different from what the criteria assumed — update criteria.
3. If no fixture files exist, verify each criterion can produce a meaningful
   assertion. If criteria are too weak (e.g., "should parse successfully"), flag
   them and ask the user for concrete expected values.

This step is interactive — findings are reported to the user as they happen.

#### Step 5: Write Forensic TASKS.md

Write `notes/plans/<slug>/TASKS.md` following the forensic-tasks-spec.md format.
This is the checkpoint artifact. It includes:

- Declared fixtures at the top level
- Success criteria per task (anchored, sourced, falsifiable, with verification
  granularity and counter-example/test-fixture scope)
- Test code that references real fixture files
- Exploration notes documenting what was learned, adjusted, or surprised
- Grouped tasks with dependency mapping
- ODD pattern reference path

#### Checkpoint Pause

Present the forensic TASKS.md to the user for review:

> "Forensic TASKS.md written at `notes/plans/{slug}/TASKS.md`. {N} tasks in {M} groups.
>
> Success criteria are anchored to:
> - {N} fixture files declared
> - {N} criteria with concrete expected values
> - {N} criteria adjusted during exploration
>
> Review the TASKS.md. When you're satisfied, reply 'continue' to proceed to
> implementation. You may also `/clear` and re-invoke with `/drive-outcomes --resume`.

Commit the checkpoint:

```bash
git add notes/plans/$PHASE_SLUG/
git add .gitignore
git commit -m "docs: add forensic TASKS.md for $(basename $PHASE_SLUG)"
```

### Session B: Implement (same session or resumed)

If continuing in the same session, proceed to Step 6. If resumed after `/clear`:

```bash
# Restore state
echo "drive-outcomes" > .claude/.current_stage
PHASE_SLUG=$(basename $(dirname <tasks-path>))

# Read checkpoint
cat notes/plans/$PHASE_SLUG/TASKS.md
cat notes/plans/$PHASE_SLUG/DECISIONS.md
```

#### Step 6: Create Per-Group Worktree

For each task group in TASKS.md (starting from the first incomplete group):

```bash
git checkout -b impl/<phase-slug>/<group-id>
```

#### Step 7: Implement Tasks (edit→check→fix)

Implement each task sequentially, dispatching on `kind`:

**`kind: lib-tdd`**: Launch implementation-executor with `workflow: 'odd'`:
- Read success criteria and test code from TASKS.md
- Follow ODD cycle (criteria → explore → implement → refactor → verify)
- Tests MUST use declared fixture files and assert against concrete values
- After VERIFIED: auto-review, commit with `feat(<slug>): <task-id> (ODD): <desc>`

**`kind: direct`**: Apply changes with edit→check→fix loop (up to 5 iterations):
- Read files, apply changes per guidance
- Run cargo check, fix, repeat
- Run acceptance, auto-review, commit

**Auto-review before commit** (both kinds):
1. Diff check — only files in scope
2. Intent check — matches guidance
3. Ground-truth check — no placebo assertions, fixtures used when declared
4. Acceptance check — commands pass
5. Conditional-guard parity check — for lib-tdd tasks involving algorithm
   porting from a reference: every `if`/`when`/`case`/early-return in the
   reference function must have a corresponding condition in our implementation
   or an explicit justification why it's not needed. Source both the reference
   line and the justification.

**Update resume note** after each task:
```markdown
# Resume: <slug>/<group-id>
**Tasks done**: TASK-1, TASK-2
**Next task**: TASK-3
**Status**: in-progress
```

#### Step 8: Workspace Validation

After all tasks in a group complete:

```bash
cd "${CLAUDE_PROJECT_DIR}" && cargo check --workspace 2>&1
cd "${CLAUDE_PROJECT_DIR}" && cargo clippy --workspace -- -D warnings 2>&1
cd "${CLAUDE_PROJECT_DIR}" && cargo test --workspace 2>&1 | tail -40
```

#### Step 9: Merge Sub-branch

```bash
FEATURE_BRANCH=$(git rev-parse --abbrev-ref HEAD | sed 's|impl/.*||')
git checkout "$FEATURE_BRANCH"
git merge --ff-only impl/<phase-slug>/<group-id>
git branch -d impl/<phase-slug>/<group-id>
```

Workspace validation again on the feature branch:

```bash
cd "${CLAUDE_PROJECT_DIR}" && cargo check --workspace 2>&1
cd "${CLAUDE_PROJECT_DIR}" && cargo clippy --workspace -- -D warnings 2>&1
cd "${CLAUDE_PROJECT_DIR}" && cargo test --workspace 2>&1 | tail -40
```

Clean up resume note:

```bash
rm -f "${CLAUDE_PROJECT_DIR}/.claude/resume-<slug>-<group-id>.md"
```

#### Step 10: Report

```bash
CLAUDE_PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}" CLAUDE_PROJECT_DIR="${CLAUDE_PROJECT_DIR}" \
  uv run --directory "${CLAUDE_PLUGIN_ROOT}" python \
  "${CLAUDE_PLUGIN_ROOT}/scripts/eval-session-metrics.py" drive-outcomes
```

> "Outcomes driven for phase \"{Phase Name}\".
>
> {N} tasks implemented, criteria anchored to {M} fixture files.
> Exploration adjusted {K} criteria during validation.
>
> Next step: `/make-judgement notes/plans/{slug}/TASKS.md` for cross-group review."

## Boundaries

**Will:**
- Grill the user on goals and success criteria (not implementation tactics)
- Ask the user to declare fixture files explicitly
- Write exploratory snippets against real data before committing to criteria
- Produce forensic TASKS.md with anchored success criteria
- Implement in worktrees with compiler feedback
- Auto-review for placebo tests before commit
- Leave a forensic record of what was learned and adjusted
- Re-verify factual claims from subagent summaries by reading cited sources
  directly before taking action on them

**Will not:**
- Discuss implementation patterns or tactics during the grill (that's what
  exploration is for)
- Use exact before/after blocks — guidance is descriptive
- Skip fixture anchoring when fixtures exist
- Allow vacuous assertions in test code
