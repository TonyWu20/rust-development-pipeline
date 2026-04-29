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
#   worktree-utils.sh merge <worktree-path> [target-branch]
#       Merge changes from a worktree into the main repo's current branch
#       (or target-branch).
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
  worktree-utils.sh merge <worktree-path> [target-branch]
  worktree-utils.sh discover <plan-slug>
EOF
    exit 1
}

cmd_create() {
    local wt_path="$1"
    local branch="$2"

    if [ -d "$wt_path" ]; then
        echo "Worktree already exists at $wt_path" >&2
        exit 0
    fi

    # Check if branch exists locally
    if git show-ref --verify --quiet "refs/heads/$branch"; then
        git worktree add "$wt_path" "$branch"
    else
        git worktree add -b "$branch" "$wt_path" HEAD
    fi
    echo "Created worktree at $wt_path on branch $branch"
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
    local wt_path="$1"
    local target_branch="${2:-$(git rev-parse --abbrev-ref HEAD)}"

    if [ ! -d "$wt_path" ]; then
        echo "Worktree $wt_path does not exist" >&2
        exit 1
    fi

    # Get the branch name from the worktree
    local wt_branch
    wt_branch=$(git -C "$wt_path" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")

    echo "Merging worktree branch '$wt_branch' into '$target_branch'..."

    # Generate patches for each commit on the worktree branch
    local work_dir
    work_dir=$(mktemp -d)
    local patch_dir="$work_dir/patches"
    mkdir -p "$patch_dir"

    # Get list of commits on the worktree branch not on main
    local commits
    commits=$(git -C "$wt_path" log --oneline "$DEFAULT_BRANCH..HEAD" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$commits" -eq 0 ]; then
        # Check for uncommitted changes
        if ! git -C "$wt_path" diff HEAD --quiet 2>/dev/null; then
            git -C "$wt_path" diff HEAD > "$patch_dir/uncommitted.patch"
            echo "Created patch for uncommitted changes"
        else
            echo "No changes to merge — worktree is up to date"
        fi
    else
        # Export each commit as a patch
        local i=0
        while IFS= read -r commit; do
            local hash
            hash=$(echo "$commit" | awk '{print $1}')
            git -C "$wt_path" format-patch --stdout -1 "$hash" > "$patch_dir/$i-${hash}.patch" 2>/dev/null
            i=$((i + 1))
        done < <(git -C "$wt_path" log --reverse --oneline "$DEFAULT_BRANCH..HEAD" 2>/dev/null)

        # Check for uncommitted changes too
        if ! git -C "$wt_path" diff HEAD --quiet 2>/dev/null; then
            git -C "$wt_path" diff HEAD > "$patch_dir/uncommitted.patch"
        fi
    fi

    # Apply patches
    for patch in "$patch_dir"/*.patch; do
        [ -f "$patch" ] || continue
        echo "Applying patch: $(basename "$patch")"
        if git apply "$patch" 2>/dev/null; then
            echo "  Patch applied successfully"
        else
            echo "  Warning: patch apply failed (may already be applied)" >&2
        fi
    done

    # Clean up
    rm -rf "$work_dir"
    echo "Merge complete"
}

cmd_discover() {
    local plan_slug="$1"

    # Check deterministic paths first
    local base="/tmp/${plan_slug}"
    for dir in "$base"*; do
        [ -d "$dir" ] || continue
        if git -C "$dir" rev-parse --git-dir >/dev/null 2>&1; then
            echo "$dir"
        fi
    done

    # Fallback: scan git worktree list
    git worktree list 2>/dev/null | grep "$plan_slug" | awk '{print $1}' || true
}

# ── Main ──────────────────────────────────────────────────────────────────────

if [ $# -lt 1 ]; then
    usage
fi

case "$1" in
    create)
        [ $# -ge 3 ] || usage
        cmd_create "$2" "$3"
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
    merge)
        [ $# -ge 2 ] || usage
        cmd_merge "$2" "${3:-}"
        ;;
    discover)
        [ $# -ge 2 ] || usage
        cmd_discover "$2"
        ;;
    *)
        usage
        ;;
esac
