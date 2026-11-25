#!/usr/bin/env bash
# Export the read-only reference repositories at their upstream default branch.
#
# Why this exists: sync-repos.sh can only merge --ff-only repositories that are
# clean and have no local commits. The reference clones (sheng, zizhan, pong,
# t970, liuqin) carry local commits or are deliberately detached, so every four
# hours they were fetched and then reported as "behind": fetched forever, never
# actually refreshed. This script makes "fetched" mean "a readable tree at the
# upstream commit" under /mnt/e/iOS Port/Work/references/latest, without touching the
# working copy and without any force operation (iron rule 18).
set -euo pipefail

OUT=/mnt/e/iOS Port/Work/references/latest
REPOS=${K60_REFERENCE_REPOS:-"UniXNU-sheng UniXNU-zizhan UniXNU-pong UniXNU-t970 UniXNU-liuqin"}
mkdir -p "$OUT"

status=0
for name in $REPOS; do
    repo=/mnt/e/iOS Port/Sources/$name
    if [ ! -e "$repo/.git" ]; then
        echo "reference $name: no git checkout; skipped"
        continue
    fi
    remote=origin
    git -C "$repo" remote | grep -qx "$remote" || remote=$(git -C "$repo" remote | head -1)
    if [ -z "$remote" ]; then
        echo "reference $name: no remote; skipped"
        continue
    fi
    ref=$(git -C "$repo" symbolic-ref -q "refs/remotes/$remote/HEAD" || true)
    if [ -z "$ref" ]; then
        ref="refs/remotes/$remote/main"
    fi
    commit=$(git -C "$repo" rev-parse --verify "$ref" 2>/dev/null || true)
    if [ -z "$commit" ]; then
        echo "reference $name: cannot resolve $ref; skipped"
        status=1
        continue
    fi
    dest=$OUT/$name
    rm -rf "$dest"
    mkdir -p "$dest"
    git -C "$repo" archive "$commit" | tar -x -C "$dest"
    printf '%s\n' "$commit" > "$dest/.reference-commit"
    echo "reference $name: exported $(git -C "$repo" rev-parse --short "$commit") ($(find "$dest" -type f | wc -l) files)"
done
exit "$status"
