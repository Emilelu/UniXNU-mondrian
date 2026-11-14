#!/usr/bin/env bash
# Repair git worktree pointers after they were created from Windows.
#
# `git worktree add` run from Windows PowerShell writes `gitdir: E:/...` into
# <worktree>/.git and `E:/.../.git` into .git/worktrees/<name>/gitdir. Git inside
# WSL cannot resolve either form: the first is a Windows path, the second points
# at the .git FILE (which git rejects, because it expects a directory) — so every
# worktree shows up as "prunable" and commands run there use the wrong tree.
#
# This rewrites both sides to the /mnt/e form. Idempotent.
set -euo pipefail

# 默认修复本脚本所在的检出；在 worktree 里跑时把主检出路径当第一个参数传进来，或设 K60_REPO。
REPO="${K60_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
MAIN="${1:-$REPO}"
HACK=$(cd "$MAIN/.." && pwd)
WT_DIR="$MAIN/.git/worktrees"

[ -d "$WT_DIR" ] || { echo "repair-worktrees: no worktrees under $MAIN"; exit 0; }

fixed=0
for dir in "$WT_DIR"/*/; do
    name=$(basename "$dir")
    wt="$HACK/$name"
    if [ ! -d "$wt" ]; then
        echo "skip $name: no worktree directory at $wt"
        continue
    fi
    # .git/worktrees/<name>/gitdir points at the worktree's .git FILE, absolute.
    printf '%s/.git\n' "$wt" > "$dir/gitdir"
    # <worktree>/.git points at the directory holding the per-worktree state.
    printf 'gitdir: ../%s/.git/worktrees/%s\n' "$(basename "$MAIN")" "$name" > "$wt/.git"
    echo "repaired $name"
    fixed=$((fixed + 1))
done

echo "repair-worktrees: $fixed worktree(s) rewritten"
git -C "$MAIN" worktree list
