#!/usr/bin/env bash
# Export every detached-HEAD reference repository at its remote default branch.
#
# Why: `merge --ff-only` does nothing on a detached HEAD, so a repo can be
# fetched every four hours and still be weeks stale (this is exactly how the
# sheng reference stayed at a68ee4e while origin/main was c8f92b2). This script
# turns "fetched" into "readable latest tree" under /mnt/e/k60-work/references.
set -euo pipefail

OUT=/mnt/e/k60-work/references/latest
mkdir -p "$OUT"

for repo in /mnt/e/hackios/*/ /mnt/e/hackios/UniXNU-sheng; do
    name=$(basename "$repo")
    [ -e "$repo/.git" ] || continue
    branch=$(git -C "$repo" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
    [ "$branch" = "HEAD" ] || continue
    remote=$(git -C "$repo" remote 2>/dev/null | grep -qx origin && echo origin || git -C "$repo" remote | head -1)
    [ -n "$remote" ] || continue
    ref=$(git -C "$repo" symbolic-ref -q "refs/remotes/$remote/HEAD" || true)
    if [ -z "$ref" ]; then
        ref="$remote/main"
        git -C "$repo" rev-parse --verify "$ref" >/dev/null 2>&1 || continue
    fi
    commit=$(git -C "$repo" rev-parse --short "$ref")
    target="$OUT/$name"
    rm -rf "$target"
    mkdir -p "$target"
    if git -C "$repo" archive "$ref" | tar -x -C "$target" 2>/dev/null; then
        printf '%s' "$commit" > "$target/.reference-commit"
        echo "exported $name at $ref $commit -> $target"
    else
        rm -rf "$target"
        echo "skip $name (archive failed)" >&2
    fi
done
