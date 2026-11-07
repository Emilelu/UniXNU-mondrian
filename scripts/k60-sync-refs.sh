#!/usr/bin/env bash
# Sync every reference repository and report how far behind the local copies are.
#
# Read-only by design: it fetches (never pulls) so a dirty work tree or an
# unpushed branch is never overwritten. It prints, per repository, the distance
# between the local HEAD and the remote default branch.
#
# Covers the 13 repositories under D:\Android\k60-ios and the WSL-side
# ~/hackios trees. Run it before building and before quoting code from any of
# these repositories.
#
#   bash scripts/k60-sync-refs.sh          # fetch and report
#   bash scripts/k60-sync-refs.sh --quiet  # only the repositories that moved
set -uo pipefail

DROOT="${K60_D_ROOT:-/mnt/d/Android/k60-ios}"
WROOT="${K60_W_ROOT:-$HOME/hackios}"
QUIET=0
[ "${1:-}" = "--quiet" ] && QUIET=1

# D-side repositories, relative to DROOT.
D_REPOS=(
  "ios-sweet-k60"
  "refs/darwin-xnu-build"
  "refs/ios-sweet"
  "refs/uefi-pong"
  "refs/UniXNU"
  "refs/UniXNU-pong"
  "refs/UniXNU-sheng"
  "refs/UniXNU-sm8550-common"
  "uefi-pong"
  "UniXNU"
  "UniXNU-fork"
  "UniXNU-liuqin"
  "UniXNU-sheng"
)

# WSL-side repositories, relative to WROOT.
W_REPOS=(
  "UniXNU-mondrian"
  "uefi-mondrian"
  "UniXNU-pong"
  "UniXNU"
)

moved=0

report() {
	local dir="$1" label="$2"
	[ -d "$dir/.git" ] || { echo "  $label: not a git repository"; return; }

	local head branch remote behind ahead
	head=$(git -C "$dir" rev-parse --short HEAD 2>/dev/null || echo '?')
	branch=$(git -C "$dir" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')
	remote=$(git -C "$dir" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || echo '')

	if [ -n "$remote" ]; then
		behind=$(git -C "$dir" rev-list --count "$remote..HEAD" 2>/dev/null || echo 0)
		ahead=$(git -C "$dir" rev-list --count "HEAD..$remote" 2>/dev/null || echo 0)
		echo "  $label: branch=$branch head=$head $remote behind=$behind ahead=$ahead"
		if [ "$behind" != "0" ]; then
			echo "      remote moved: $(git -C "$dir" log --oneline -3 "$remote" 2>/dev/null | tr '\n' '|')"
			moved=$((moved + 1))
			return 0
		fi
	else
		echo "  $label: branch=$branch head=$head (no upstream)"
	fi
	git -C "$dir" log --all --oneline -3 2>/dev/null | sed 's/^/      /'
}

echo "== fetching D:\\Android\\k60-ios =="
for r in "${D_REPOS[@]}"; do
	dir="$DROOT/$r"
	if [ ! -d "$dir/.git" ]; then
		echo "  $r: missing"
		continue
	fi
	if git -C "$dir" fetch --all --prune >/dev/null 2>&1; then
		report "$dir" "$r"
	else
		echo "  $r: FETCH FAILED"
	fi
done

echo
echo "== fetching WSL ~/hackios =="
for r in "${W_REPOS[@]}"; do
	dir="$WROOT/$r"
	if [ ! -d "$dir/.git" ]; then
		echo "  $r: missing"
		continue
	fi
	if git -C "$dir" fetch --all --prune >/dev/null 2>&1; then
		report "$dir" "$r"
	else
		echo "  $r: FETCH FAILED"
	fi
done

echo
if [ "$moved" -gt 0 ]; then
	echo "$moved repository/repositories moved. Read the change before quoting it."
else
	echo "every tracked upstream branch is up to date with the local HEAD."
fi

# A moved branch is only half the picture. The component sources under
# drivers/ are local copies, so a fix can sit already written in the
# reference tree while our copy stays on the old order. The ArmCpu Darwin 24
# start order was such a fix and the unit only found it after a panic named
# the assertion.
echo
echo "== comparing our component sources against the reference tree =="
if [ -x "$WROOT/UniXNU-mondrian/scripts/k60-compare-components.py" ] || \
   [ -f "$WROOT/UniXNU-mondrian/scripts/k60-compare-components.py" ]; then
	python3 "$WROOT/UniXNU-mondrian/scripts/k60-compare-components.py" || true
else
	echo "  k60-compare-components.py is missing"
fi
