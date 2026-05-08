#!/usr/bin/env bash
# worktree-utils.sh — Git worktree management for the explore-implement pipeline.
#
# Usage:
#   worktree-utils.sh create <worktree-path> <branch>
#       Create a new worktree at <worktree-path> on <branch>.
#       Creates the branch from HEAD if it doesn't exist.
#
#   worktree-utils.sh remove <worktree-path>
#       Remove a worktree safely.
#
#   worktree-utils.sh list [plan-slug]
#       List all worktrees, optionally filtered by plan-slug.
#
#   worktree-utils.sh status <worktree-path>
#       Show status of a worktree: commits ahead, uncommitted changes, etc.
#
#
#   worktree-utils.sh discover <plan-slug>
#       Find existing worktrees matching a plan-slug via deterministic path
#       and git worktree list.

set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
DEFAULT_BRANCH="${DEFAULT_BRANCH:-main}"

usage() {
    cat <<'EOF'
Usage:
  worktree-utils.sh create <worktree-path> <branch>
  worktree-utils.sh remove <worktree-path>
  worktree-utils.sh list [plan-slug]
  worktree-utils.sh status <worktree-path>
  worktree-utils.sh discover <plan-slug>
EOF
    exit 1
}

cmd_create() {
    local wt_path="$1"
    local branch="$2"
    local source_branch_file=""

    # Parse optional flags after positional args
    shift 2
    while [ $# -gt 0 ]; do
        case "$1" in
            --source-branch-file)
                source_branch_file="$2"
                shift 2
                ;;
            *)
                echo "Unknown option: $1" >&2
                exit 1
                ;;
        esac
    done

    # Check git worktree list first (authoritative), not just directory existence
    if git worktree list --porcelain 2>/dev/null | grep -q "^worktree $wt_path$"; then
        echo "Worktree already registered at $wt_path (git worktree list)" >&2
        exit 0
    fi

    if [ -d "$wt_path" ]; then
        echo "Warning: directory exists at $wt_path but git does not list it as a worktree." >&2
        echo "This may be a stale directory from a prior session. Remove it first:" >&2
        echo "  rm -rf '$wt_path'" >&2
        exit 1
    fi

    # Check if branch exists locally
    if git show-ref --verify --quiet "refs/heads/$branch"; then
        git worktree add "$wt_path" "$branch"
    else
        git worktree add -b "$branch" "$wt_path" HEAD
    fi

    # Capture source branch for final echo (backward compat) and --source-branch-file
    source_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "HEAD")

    if [ -n "$source_branch_file" ]; then
        echo "$source_branch" > "$source_branch_file"
    fi

    echo "Created worktree at $wt_path on branch $branch"
    echo "SOURCE_BRANCH=$source_branch"
}

cmd_remove() {
    local wt_path="$1"
    if [ ! -d "$wt_path" ]; then
        echo "Worktree $wt_path does not exist" >&2
        exit 0
    fi
    git worktree remove "$wt_path" 2>/dev/null || {
        # Force remove if clean-up needed
        git worktree remove --force "$wt_path" 2>/dev/null || {
            echo "Warning: could not remove worktree at $wt_path" >&2
        }
    }
    echo "Removed worktree at $wt_path"
}

cmd_list() {
    local filter="${1:-}"
    if [ -n "$filter" ]; then
        git worktree list | grep "$filter" || echo "No worktrees matching '$filter'"
    else
        git worktree list
    fi
}

cmd_status() {
    local wt_path="$1"
    if [ ! -d "$wt_path" ]; then
        echo "Worktree $wt_path does not exist" >&2
        exit 1
    fi

    echo "=== Worktree: $wt_path ==="
    echo ""

    # Branch
    local branch
    branch=$(git -C "$wt_path" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    echo "Branch: $branch"

    # Commits ahead of the default branch
    local ahead
    ahead=$(git -C "$wt_path" log --oneline "$DEFAULT_BRANCH..HEAD" 2>/dev/null | wc -l | tr -d ' ')
    echo "Commits ahead of $DEFAULT_BRANCH: $ahead"

    # Uncommitted changes
    local uncommitted
    uncommitted=$(git -C "$wt_path" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
    echo "Uncommitted files: $uncommitted"

    # Recent commits
    echo ""
    echo "Recent commits:"
    git -C "$wt_path" log --oneline -5 2>/dev/null || echo "  (none)"

    # Diff from HEAD
    local has_diff=false
    if git -C "$wt_path" diff HEAD --quiet 2>/dev/null; then
        has_diff=false
    else
        has_diff=true
    fi
    echo ""
    echo "Has uncommitted changes: $has_diff"
}

cmd_merge() {
    echo "Deprecated: use 'git merge <worktree-branch>' directly." >&2
    echo "Models handle merging; the script added unnecessary rigidity." >&2
    exit 1
}

cmd_discover() {
    local plan_slug="$1"

    # Primary: use git worktree list (authoritative)
    local found=false
    while IFS= read -r line; do
        local path="${line%% *}"
        if echo "$path" | grep -q "$plan_slug"; then
            echo "$path"
            found=true
        fi
    done < <(git worktree list --porcelain 2>/dev/null | grep "^worktree " | sed 's/^worktree //')

    # Fallback: scan .pipeline-worktrees/ convention
    local wt_base="${CLAUDE_PROJECT_DIR:-.}/.pipeline-worktrees"
    if [ -d "$wt_base" ]; then
        for dir in "$wt_base"/*"$plan_slug"*; do
            [ -d "$dir" ] || continue
            if ! $found; then
                echo "$dir"
            fi
        done
    fi

    if ! $found; then
        echo "No worktrees matching '$plan_slug'" >&2
    fi
}

# ── Main ──────────────────────────────────────────────────────────────────────

if [ $# -lt 1 ]; then
    usage
fi

case "$1" in
    create)
        [ $# -ge 3 ] || usage
        wt_path="$2" branch="$3"
        shift 3
        cmd_create "$wt_path" "$branch" "$@"
        ;;
    remove)
        [ $# -ge 2 ] || usage
        cmd_remove "$2"
        ;;
    list)
        cmd_list "${2:-}"
        ;;
    status)
        [ $# -ge 2 ] || usage
        cmd_status "$2"
        ;;
    discover)
        [ $# -ge 2 ] || usage
        cmd_discover "$2"
        ;;
    *)
        usage
        ;;
esac
