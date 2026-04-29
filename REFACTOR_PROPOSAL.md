# Refactor proposal of the pipeline

## The evolution of this pipeline

This pipeline was design based on several core principles:

1. Plan first and execute
2. Deterministic Execution via TOML Plans and Compiled Scripts
3. Separate planning and execution to save token bills: local LLM or cheap LLM
   models execute, expensive high performance LLM plans.
4. Context management via subagent orchestration: shield the main conversation
   from unnecessary contexts from tool executions and task executions.
5. High quality output comes from clear and comprehensive planning, strictly
   followed executions, and final cross-validation to prevent goal shifting and
   ensure LLM efforts are not blind with local extrema.

Details can be read from [README.md](./README.md) and [INTRODUCTION.md](./INTRODUCTION.md).

### About this branch and current status.

This branch is trying to address the recurring problems during fix rounds of repo
`TonyWu20/castep_workflow_framework`. ([feature_request](./feature-requests/reduce_recurring_problems.md))
As I am able to use a more capable local LLM (`Qwen3.6-35B-A3B` quantized
version) instead of the `Qwopus3.5-9B` model (one of the original ground-truths that this
pipeline was built on), I try to let it draft the enriched plan and pr reviews.
Because in the `main` branch version of this pipeline, these two stages are done
by the high performance cloud LLMs, with substantial token usage on reading
files to research on how to write the code and what is changed after the
implementations. Also, several trial attemps of using the `Qwen3.6-35B-A3B` to
review were judged by the cloud LLMs, and the results were often majorly
accepted with minor overlooks of details or misalignments with the project
development plans. With these observation, this branch was created to experiment
if the role of local LLM can be promoted to further reduce token spent on
mechanic works of cloud LLM. Therefore, more deterministic output scripts were
designed and implemented, and the session/model-separated `gather` and `judge`
skills were proposed.

## Real user experience and observations of the current branch

The only user of this pipeline is still the author myself. After days of
application of this branch, I experienced and observed several issues:

1. Very long execution time in the `per-file-anaylsis` in the `review-pr-gather`
   skill. The `strict-code-reviewer` in `per-file-analysis` often accumulates large context, from my
   observation, up to 100K tokens, and the local LLM struggles to complete the
   request processing at this stage.
2. The `gather-diff-data` initially reports the git add/rm tracks of the
   compiled script artifacts, adding noise to the `per-file-analysis`. This has
   been addressed by adding filter regex patterns in the script.
3. Quality regressions from `enrich-plan-gather` and `enrich-plan-judge` even if
   these skills were both executed with cloud LLMs (like `Sonnet` for gather,
   `Opus` for judge). See the issue #9: this double-check chain of skills still
   produce incorrect task code and task execution order.

I began to reflect on the pipeline. Here is what I think:

- The main pipeline stage design is correct: high-level articulated plan generated with user-involved declaration and decisions,
  elaboration of detail code implementation, strict execution guaranteed by
  deterministic input/output with scripts, review of implementations and fix until
  approval of merge.
- The `enrich-plan`/`implementation-executor` separation was initially try to
  cut down the bill on updating the line of code to files. However, with the
  introduction of scripts, the execution phase could be already cheap for even
  cloud models, because unnecessary actions are properly prevented by hooks.
- The `enrich-plan-gather` and `enrich-plan-judge` separate the contexts in two
  claude code sessions. Though this separation of contexts is good for
  preventing hallucinations and misleading self-assurance of LLMs, it causes
  troubles when the implementations need a broader view on the codebase,
  especially when one implementation will affects its upstream and downstream
  dependencies. The separation of sessions do not help mitigate the errors from
  this.
- Doom loop trouble: Currently, the `enrich-plan` and fix plan drafting in `review-pr` both have
  the same caveat: the LLM agents do "mental dance" on writing the code piece,
  that means they have to deduce how each piece of code would affect the entire
  codebase over the static current source files. This should be the root cause
  of the recurring issues that missing pub re-exports and misalignments of code
  signatures. Even worse, the fix plan is drafted with the same deduction from the
  static analysis of codebase. This create a doom loop: the more it needs to
  implement, the more potential errors from failure of predictions on the
  subsequent changes, the more errors or misinterpreted implementations need to be
  fixed, and the more recurring issues generated from deducing the fixes.

## Attempts and Ideas to improve

### The in-development [`rust-workspace-map`](../rust-workspace-map) binary

The `rust-workspace-map` is a thin Rust-native tool inspired by
[tirth8205/code-review-graph](https://github.com/tirth8205/code-review-graph).
We want to build a tool to produce LLM agent-ready-to-understand structured
output. The following is quoted from the [mvp
plan](../rust-workspace-map/plans/mvp/MVP_PLAN.md).

This could accelerate the explorations for LLM agents whenever it needs
knowlegde about the codebase, and it is designed for LLM agents from the ground
up---I asked LLM agents to design features and interfaces based on their own
perspective.

> ### Core Design Goal: O(1) lookup for LLM agents
>
> This tool exists to answer structural questions about a Rust workspace in **constant time — one hashmap access, no tree traversal, no path guessing**. An LLM agent asking a question should get an answer the way an IDE answers: instant, precise, pre-computed.
>
> The three flat indexes (`symbols`, `name_index`, `files`) pre-compute the relationships a human engineer builds through interactive IDE navigation:
>
> | Agent question                                 | IDE equivalent         | Lookup                                                                                                       | Cost                             |
> | ---------------------------------------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------ | -------------------------------- |
> | "Is `Task` a type? Where is it defined?"       | Go-to-definition       | `name_index["Task"]` → `symbols[path]`                                                                       | O(1)                             |
> | "What file contains module `foo::bar`?"        | Go-to-file             | iterate `files`, match `entry.module_path == "foo::bar"` (or in-memory reverse map built once at index time) | O(1) amortized                   |
> | "What modules does `lib.rs` declare?"          | File structure view    | `files["core/src/lib.rs"].module_path` → `crates[].modules[]` join → `submodules`                            | O(1) hop, then O(1) join         |
> | "Is this file reachable from the module tree?" | Module graph view      | `files[path].parent_module_file.is_some()` (or file is a crate root)                                         | O(1)                             |
> | "Which crate exports `Task`?"                  | (no direct IDE analog) | `cross_references.types["Task"].exported_by`                                                                 | O(1) — already shipping in 0.1.0 |
>
> This is the fundamental difference from the hierarchical `crates → modules → publicItems` tree alone. That tree requires the agent to traverse, filter, and guess module paths. The flat indexes eliminate traversal entirely — the agent asks one question, makes one lookup, gets one answer. The tool is not a JSON dump for humans to browse; it is a query engine where every query is O(1) and every answer fits in a few hundred tokens.
>
> **Note on what's _not_ O(1) in MVP:** "Who imports this symbol?" at file:line granularity is intentionally deferred — the existing `cross_references.types[name].imported_by` answers it at crate granularity, which covers most measured workflows. File:line precision adds extraction cost and per-symbol storage that no current pipeline integration cites. Add when a measured workflow demands it.

### Refactor the pipeline in view of context management

Our pipeline breakdown was not centric on context engineering from the ground
up. Therefore, a first principle analysis is needed to refactor it properly.

In my opinion, we should first try to sort out the context dependencies for each
task and pipeline stages. Then, we should evaluate on what would be the minimum
viable context size for each task and stage. For example, when discussing the
next phase plan with the users, the agents clearly should have full context of
the repo's current status, previous decided plans, deferred changes and
improvements, and the user's feedback and insights. When the agent is asked to
elaborate on the decided plan for actual code implementations, it should has an
overall understanding of the codebase, to tell for each task which files would
be affected by the planned changes or new/deleted line of codes. Then from this
preliminary breakdown of the plan, group the tasks base on the related files, so
subagents assigned to elaborated on the code implementations would know exactly
which files would be affected and need validations. For the subagents who are
told to elaborated the code implementations, it'd be better they own a worktree
workspace so they can do trail-and-error explorations. They will receive dynamic
feedback step by step when they try to implement the changes, adjust correctly
from the compiler feedback or validation commands. So the key insight is, no
more "mental simulation" of how the added changes interact with the existing
codebase or status that prior mentally simulated changes have been done. Allow
the local models to self explore under the elaborated directions from cloud
models.

Therefore, the pipeline would kind of recover to the main branch states, but
with a clear context management principles in mind: Separate and control the
context for main agent and subagents based on their roles and assignment,
plan decomposed based on the judgement of context availability (minimum viable),
dynamic explorations of code implementation for local LLM agents with constraints and guides provided from the smarter LLM agents.
Finally, with the new backbone of the pipeline, integrate tools and scripts that
can accurately direct the LLM agents to get what they need and what they want,
to improve token efficiency.
