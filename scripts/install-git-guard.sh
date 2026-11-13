#!/usr/bin/env bash
# Install the system-wide git guard.
#
# Why this exists: on 2026-11-14 the Lead ran `git checkout --` in a checkout
# that belonged to the touch agent and destroyed eight uncommitted files; seven
# were unrecoverable. The repository already had scripts/git-safe.sh, but a
# voluntary wrapper cannot stop somebody typing plain `git`. This installer puts
# a wrapper in /usr/local/bin, which precedes /usr/bin on PATH, so every `git`
# in the distro goes through it.
#
# The guard snapshots before it refuses, refuses only when the tree holds another
# actor's uncommitted work, and never blocks reads.
#
# Usage:  sudo bash scripts/install-git-guard.sh [--check]
set -euo pipefail

GUARD=/usr/local/bin/git
REAL=/usr/bin/git.real

if [ "${1:-}" = "--check" ]; then
    status=0
    if [ -x "$REAL" ]; then echo "ok   $REAL exists"; else echo "FAIL $REAL missing"; status=1; fi
    if [ -x "$GUARD" ]; then echo "ok   $GUARD exists"; else echo "FAIL $GUARD missing"; status=1; fi
    resolved=$(command -v git || true)
    if [ "$resolved" = "$GUARD" ]; then
        echo "ok   git resolves to $GUARD"
    else
        echo "FAIL git resolves to ${resolved:-nothing}, expected $GUARD"
        status=1
    fi
    exit "$status"
fi

[ "$(id -u)" = "0" ] || { echo "install-git-guard: run as root" >&2; exit 1; }

ROOT=$(cd "$(dirname "$0")/.." && pwd)

# Keep one pristine copy of the real binary. Re-installing must not replace it
# with our own wrapper, which would recurse forever.
if [ ! -x "$REAL" ]; then
    cp -a /usr/bin/git "$REAL"
    echo "saved the real git as $REAL"
fi

install -m 0755 "$ROOT/scripts/git-guard" "$GUARD"
echo "installed $GUARD"

resolved=$(command -v git || true)
if [ "$resolved" != "$GUARD" ]; then
    echo "warning: git resolves to $resolved, not $GUARD" >&2
    echo "warning: /usr/local/bin must precede /usr/bin on PATH" >&2
fi

"$GUARD" --version
bash "$ROOT/scripts/install-git-guard.sh" --check
