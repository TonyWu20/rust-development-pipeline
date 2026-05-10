# Why ODD Over TDD

## The Problem with TDD in AI-Assisted Development

Test-Driven Development (TDD) as codified in the classic ch12-04 red-green-refactor
cycle has a fundamental assumption that breaks under AI-assisted development:
**the test writer and the implementer are the same entity with the same
understanding of the codebase**.

When an AI agent writes both the test and the implementation sequentially, the
"test IS the specification" philosophy creates a closed loop:

1. The agent writes a test based on its understanding of the problem
2. The agent implements to pass that test
3. The test passes → the implementation is correct *by definition*
4. There is no point where reality enters the system

This rewards **process compliance** over **outcome correctness**. An agent that
follows the red-green-refactor steps perfectly produces passing tests even when
the code is substantively wrong — because the test was written with the same
misunderstanding as the implementation.

### Real-World Evidence: 6 Bugs Survived All Pipeline Gates

In the chemrust-hamiltonian Phase-03 cycle, every bug that survived review was
of this class:

| Bug | How TDD Certified It |
|-----|----------------------|
| Wrong binary format layout | Unit test used synthetic single-record data matching the agent's own format assumptions |
| Per-kpoint eigenvalues fused into one record | TASKS.md said "flat arrays," test validated shape not content |
| Missing physics terms (sqrt(4π), Coulomb tail) | Unit test only checked is_finite() |
| Loose integration bound (10 Hartree vs 1e-8) | Bound chosen without reference to ground truth |

Every test passed. Every review checked the test against the spec. The spec matched
the test. The code was wrong.

## The ODD Alternative

Outcome-Driven Development (ODD) breaks the closed loop by requiring every
assertion to be anchored to something **external to the code under test**.

**Goal** → **Criteria** → **Tests** → **Outcomes**

| ODD Step | What Changes | Why It Matters |
|----------|-------------|----------------|
| Define criteria | Expected values must cite a source (fixture file, reference implementation, published spec) | The agent can't invent the answer — it must find it in the real world |
| Explore | Write snippets against real data, validate criteria are achievable | Reality enters the system before implementation begins |
| Implement | Build to satisfy criteria, not abstract guidance | The target is fixed and external |
| Verify | Run against real fixtures, compare output to criteria | Outcomes are measured, not assumed |

## The Key Insight

TDD says: "Write the test first, then implement to pass it."

ODD says: "Define what winning looks like in terms of something you can't control,
then build until you get there."

The test is not the specification. The test is a **hypothesis about an outcome**.
The specification is the ground truth — the real file, the reference output, the
published formula.

## When Not to Use ODD

ODD is not a universal replacement. It applies when:

**Use ODD:** Library code with real reference data (parsers, numerical kernels,
file I/O, format converters, simulation code).

**Don't use ODD:** CLI argument parsing, config file generation, Cargo.toml edits,
main.rs wiring, I/O adapters, code dictated by external constraints. Use
`kind: "direct"` with edit→check→fix.

## The Placebo Test Taxonomy

These patterns emerge naturally under TDD and are all caught by ODD's
ground-truth requirement:

| Pattern | How It Passes | How ODD Catches It |
|---------|--------------|-------------------|
| `assert!(x.is_finite())` | Passes for any real number — only fails on NaN | Requires value assertion: `assert!(x - expected < 1e-8)` with source |
| `parse(write(x)) == x` | Symmetric bugs survive round-trip | Requires parsing a known-good file and checking against reference values |
| `residual < 10.0` (no source) | Loose bound chosen to pass any implementation | Requires cited source: `(Source: reference residual = 2.3e-8)` |
| Synthetic empty buffer | Matches parser's own starting assumptions | Requires real data when fixtures exist |

## Relationship to TDD

ODD does not discard the useful parts of TDD — write assertions before code,
incremental implementation, refactor while green. What it removes is the
self-referential loop where the same agent writes both the test and the answer,
and only the test is consulted as the oracle.

The pipeline still writes tests before code. The tests still drive the design.
But the truths they assert come from **outside the agent**, not from the agent's
own understanding of the problem.
