---
name: file-issue
description: File a bug report or feature request for the rust-development-pipeline itself, with auto-gathered context from the current project and session. Use when the user says "/file-issue", "file a bug", "report an issue", "this is a pipeline problem", or encounters a pipeline defect during daily use.
---

# File Issue

Gathers context from the current project and session to file a structured issue on the `TonyWu20/rust-development-pipeline` repository. Lowers friction for reporting pipeline defects encountered during daily use.

## Trigger

`/file-issue`

No arguments. The skill prompts the user for issue details interactively.

## Process

### Step 1: Gather Context (Subagent)

Launch a **general-purpose subagent** to collect relevant context:

> **Agent**: general-purpose (subagent, discardable context)
>
> **Task**: Gather context for a pipeline issue report.
>
> Collect the following:
>
> 1. **Current pipeline state**:
>    ```bash
>    # Check which skills are being used
>    ls skills/*/SKILL.md 2>/dev/null
>    ```
>
> 2. **Recent session activity**:
>    - Read the `.claude/settings.local.json` for hooks configuration
>    - Read `hooks/hooks.json`
>
> 3. **Pipeline version**:
>    ```bash
>    git log --oneline -5
>    ```
>
> 4. **Current project context** (from the working directory where the issue was encountered):
>    ```bash
>    pwd
>    git remote -v 2>/dev/null
>    git log --oneline -3 2>/dev/null
>    ```
>
> Output the gathered context as structured data for the issue template.

### Step 2: Build Issue Template

Format the issue using the GitHub issue template:

```markdown
---
title: "[pipeline]: <short description>"
---

## Description

{User's description of the problem or feature request}

## Context

- **Pipeline version**: {commit hash from git log}
- **Project**: {current project URL or path}
- **Session**: {what skills were being used when the issue occurred}

## Reproduction Steps

{User-provided or auto-detected steps}

## Expected vs Actual

- **Expected**: {what should happen}
- **Actual**: {what actually happened}

## Environment

- **Pipeline branch**: {current branch}
- **OS**: {auto-detected}
- **Claude Code version**: {if available}

## Relevant Artifacts

{Paths to relevant plan files, directions.json, execution reports, etc.}
```

### Step 3: User Review

Present the formatted issue to the user for review and editing:

> "Here's the draft issue for `TonyWu20/rust-development-pipeline`:
>
> ---
>
> {ISSUE_BODY}
>
> ---
>
> Please review and edit the description above, then confirm to file the issue.
> Type 'confirm' to file, or provide changes."

### Step 4: File the Issue

Once the user confirms, file the issue:

```bash
gh issue create --repo TonyWu20/rust-development-pipeline --title "<title>" --body "<body>"
```

Report the resulting issue URL to the user.

## Boundaries

**Will:**
- Auto-gather context from the current project and pipeline state
- Format a structured issue using the project's template
- Let the user review and edit before filing
- File via `gh` CLI

**Will not:**
- File issues without user review
- Modify any project files
- Include sensitive information (API keys, tokens) in the issue
