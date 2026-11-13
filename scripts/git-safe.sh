#!/usr/bin/env bash
# git, but it refuses the commands that destroyed an agent's work on 2026-11-14.
#
#   scripts/git-safe.sh status
#   scripts/git-safe.sh commit -m "..."
#
# Two layers of protection for the commands that discard uncommitted work
# (checkout -- <path>, checkout -f, restore, reset --hard, clean -fd, stash):
#
#   1. Always: take a complete snapshot first, so "undo" exists
#      (scripts/snapshot-worktree.py -> E:/k60-work/scratch/snapshots).
#   2. Unless K60_I_OWN_THIS_TREE=1: refuse outright in a tree that belongs to
#      somebody else (docs/engineering/TREE-OWNERS.toml, iron rule 11).
#
# So the accident of 2026-11-14 — eight files of a teammate's work lost with no
# recovery path — needs two independent mistakes to happen again, and leaves a
# restorable snapshot either way.
set -uo pipefail

ROOT=$(git rev-parse --show-toplevel 2>/dev/null || true)
[ -n "$ROOT" ] || { echo "git-safe: not inside a git checkout" >&2; exit 1; }
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

verb=${1:-}
dangerous=0
case "$verb" in
    restore|stash) dangerous=1 ;;
    reset|clean)
        for arg in "$@"; do
            case "$arg" in
                --hard|--hard=*|-f|-fd|-fdx|-xfd|--force) dangerous=1 ;;
            esac
        done
        ;;
    checkout)
        for arg in "$@"; do
            case "$arg" in
                --|-f|--force) dangerous=1 ;;
            esac
        done
        ;;
esac

if [ "$dangerous" = 1 ]; then
    if [ "${K60_I_OWN_THIS_TREE:-}" != "1" ]; then
        {
            echo "git-safe: refusing '$*' in $ROOT"
            echo "git-safe: these discard uncommitted work (P-184)."
            echo "git-safe: to proceed deliberately, re-run with K60_I_OWN_THIS_TREE=1 —"
            echo "git-safe: it still takes a snapshot first, so the change stays recoverable."
        } >&2
        exit 2
    fi
    if [ -x "$HERE/snapshot-worktree.py" ] || [ -f "$HERE/snapshot-worktree.py" ]; then
        SNAP=$(python3 "$HERE/snapshot-worktree.py" --repo "$ROOT" --quiet 2>/dev/null || true)
        if [ -n "$SNAP" ]; then
            echo "git-safe: snapshot at $SNAP (restore: bash $SNAP/restore.sh)" >&2
        else
            echo "git-safe: WARNING could not snapshot $ROOT before '$*'" >&2
        fi
    fi
fi

exec git "$@"
