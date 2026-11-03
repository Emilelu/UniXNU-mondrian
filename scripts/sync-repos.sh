#!/usr/bin/env bash
# Sync every local copy of the K60 sources with its upstream.
#
# Read-only by default: fetch goes first for every repo, and a fast-forward
# merge only happens for repos that are clean, have no local commits of their
# own, and are explicitly listed as "pull". Repos that carry local work are
# reported and left alone -- merging those is a decision, not a cron job.
#
# Usage: bash sync-repos.sh [--dry-run]
set -uo pipefail

DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

LOG=/mnt/d/Android/k60-ios/SYNC-LOG.md
STAMP=$(date '+%Y-%m-%d %H:%M:%S %Z')

# path|mode   mode "pull" = fast-forward when clean, "report" = never merge
REPOS="
/home/emilelu/hackios/UniXNU|pull
/tmp/k60build|report
/home/emilelu/hackios/UniXNU-mondrian|pull
/home/emilelu/hackios/uefi-mondrian|pull
/home/emilelu/hackios/UniXNU-pong|report
/home/emilelu/hackios/UniXNU-sheng|pull
/home/emilelu/hackios/UniXNU-sm8475-common|pull
/home/emilelu/hackios/UniXNU-docs|pull
/mnt/d/Android/k60-ios/ios-sweet-k60|report
/mnt/d/Android/k60-ios/refs/ios-sweet-k60|report
"

out() { printf '%s\n' "$*" | tee -a /tmp/k60-sync-last.txt; }

: > /tmp/k60-sync-last.txt
out "## $STAMP"
out ""
out "| repo | branch | behind | ahead | dirty | action |"
out "|---|---|---|---|---|---|"

for entry in $REPOS; do
    path=${entry%|*}
    mode=${entry#*|}
    [ -d "$path/.git" ] || [ -e "$path/.git" ] || continue

    name=$(basename "$path")
    git -C "$path" fetch --all --prune -q 2>/dev/null

    branch=$(git -C "$path" rev-parse --abbrev-ref HEAD 2>/dev/null)
    up=$(git -C "$path" rev-parse --abbrev-ref '@{u}' 2>/dev/null)
    if [ -z "$up" ]; then
        out "| $name | $branch | ? | ? | ? | no upstream |"
        continue
    fi
    behind=$(git -C "$path" rev-list --count "HEAD..$up" 2>/dev/null)
    ahead=$(git -C "$path" rev-list --count "$up..HEAD" 2>/dev/null)
    dirty=$(git -C "$path" status --porcelain 2>/dev/null | wc -l)

    action="report"
    if [ "$mode" = "pull" ] && [ "$behind" -gt 0 ] && [ "$ahead" -eq 0 ] && [ "$dirty" -eq 0 ]; then
        if [ "$DRY" -eq 1 ]; then
            action="would ff"
        else
            if git -C "$path" merge --ff-only -q "$up" 2>/dev/null; then
                action="ff to ${up#*/}"
            else
                action="ff FAILED"
            fi
        fi
    elif [ "$behind" -eq 0 ]; then
        action="up to date"
    fi

    out "| $name | $branch | $behind | $ahead | $dirty | $action |"
done

out ""
{
    echo ""
    echo "---"
    echo ""
    cat /tmp/k60-sync-last.txt
} >> "$LOG"

echo
echo "=== written to $LOG ==="
