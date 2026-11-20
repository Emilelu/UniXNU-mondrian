#!/bin/sh
# SPDX-License-Identifier: BSD-2-Clause-Patent
# One command for the audio lane's iOS 27 preflight. Nothing here needs a device.
#
#   sh scripts/check-audio27-preflight.sh
#   K60_GATES=<gates checkout> sh scripts/check-audio27-preflight.sh --pac-only
#
# The PAC checks belong to the audio preflight because stage 0 intentionally
# excludes audio lane objects. --pac-only limits the run to these source and
# link-input assertions and their fixtures. It emits no objects or images.
#
# Runs, in order:
#   1. the migration list, including the one-guard rule for the driver macro
#   2. the glue against the six-symbol kernel stub set
#   3. the macro itself: three symbols with it, none without
#   4. the glue's link-time needs against the wiring table
#   5. the glue's copy set against what the compiler opens
#   6. the conf-files appender's host tests (the anchor miss must fail loudly), and the
#      chaining hook the builder points at, which ends with one verdict line
#   7. the wiring applier: copy, conf/files, the printed builder line, the hook
#   8. the weak call site: links without the glue, runs with it
#   9. the amplifier probe running on the host against a zero page
#  10. the playback judge's host tests
#  11. the amplifier side's host tests (979 cases)
#  12. the wiring walked in order, hook included, on a tree without the button driver
#  13. the 27 interface, product, include, stub, collision and closure checkers' own
#      tests, that every log line the 27 pages quote is one a printf prints, and that
#      the file:line citations still point at the code they name, and that the judge's
#      chip table and the driver's agree
#      the boot argument has one name in the driver, the audit, the judge,
#      the triage and the wiring page, and it is documented
#  14. the patch emitter's own tests
#  15. the four interfaces, the stub declarations they are compiled against, and the
#      symbol table, against a real 27 XNU tree when one is
#      on disk (XNU27_REPO overrides the search), plus the 0531 patch regenerated from
#      the same block and checked against its pinned digest, and - once the Lead books
#      it in patches/xnu-12377 - the series copy against the same emitter
#  16. the 27 driver hands over the conf-files hook and the per-object define, and
#      the framework still passes its whole environment through - one row each,
#      because any of the three can break while the build stays green - when a
#      k60-gates checkout is reachable (K60_GATES)
#  17. - when XNU27_KERNEL names a built kernel or boot image - whether that product
#      really carries the audio
#  18. the sheng ABI checker's own tests
#  19. sheng's audio host tests, its ABI constants and its add-on mount contract at that
#      commit, when its checkout is reachable; the row names the commit it ran on, because
#      a stale checkout passes just as quietly
# Reports each check and exits nonzero if any check fails.

# How many rows this file prints with every checkout in place. The tail counts
# the rows it actually printed and compares them with this number, so a new row
# that nobody counted fails here instead of leaving the pages wrong.
ROWS_EXPECTED=57

case "$#:$*" in
0:) rows_expected=$ROWS_EXPECTED; label=PREFLIGHT ;;
1:--pac-only) rows_expected=4; label='PAC PREFLIGHT' ;;
*) printf 'Usage: %s [--pac-only]\n' "$0" >&2; exit 2 ;;
esac

# The rows are printed by whatever prints them, so the count is taken from the
# file the run leaves behind rather than from a counter every site has to keep.
if [ -z "${K60_PREFLIGHT_INNER:-}" ]; then
	inner=$(mktemp)
	K60_PREFLIGHT_INNER=1 sh "$0" "$@" > "$inner" 2>&1
	status=$?
	sed '/^PREFLIGHT OK$/d' "$inner"
	rows=$(grep -cE '^(ok|skip|FAIL) ' "$inner" || true)
	ok=$(grep -c '^ok ' "$inner" || true)
	skip=$(grep -c '^skip ' "$inner" || true)
	failed=$(grep -c '^FAIL ' "$inner" || true)
	rm -f "$inner"
	if [ "$status" -ne 0 ]; then
		exit "$status"
	fi
	if [ "$rows" -ne "$rows_expected" ]; then
		printf 'ROWS FAILED %s rows printed, %s declared\n' "$rows" "$rows_expected"
		echo "$label FAILED"
		exit 1
	fi
	printf '%s OK %s rows (%s ok, %s skip, %s FAIL), as declared\n' \
	    "$label" "$rows" "$ok" "$skip" "$failed"
	exit 0
fi

set -u
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/.." && pwd)
cd "$repo" || exit 1
fail=0

# Which tree did this measure? A green line that cannot name its commit is the
# same evidence as a green line on the wrong object.
branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)
sha=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)
printf 'repo %s %s @ %s\n' "$repo" "$branch" "$sha"

# Exit 3 means "nothing to measure here", not "wrong": the emitter needs a
# pristine tree, and the series copy may not be booked yet. Skipping keeps those
# apart from a red line, and keeps a quiet absence from reading as green.
optional_row()
{
	name=$1
	shift
	out=$("$@" 2>&1)
	rc=$?
	case "$rc" in
	0) printf 'ok   %-34s %s\n' "$name" "$(printf '%s' "$out" | tail -1)" ;;
	3) printf 'skip %-34s %s\n' "$name" "$(printf '%s' "$out" | tail -1)" ;;
	*) printf 'FAIL %-34s %s\n' "$name" "$(printf '%s' "$out" | tail -1)"; fail=1 ;;
	esac
}

run()
{
	name=$1
	shift
	out=$("$@" 2>&1)
	rc=$?
	if [ "$rc" -ne 0 ]; then
		case "$name" in "PAC "*) printf '%s\n' "$out" | sed 's/^/    /' ;; esac
		printf 'FAIL %-34s %s\n' "$name" "$(printf '%s' "$out" | tail -1)"
		fail=1
		return
	fi
	printf 'ok   %-34s %s\n' "$name" "$(printf '%s' "$out" | tail -1)"
}

# A seam checker has two verdicts that are not failures: wired (0) and nothing
# measured (3) -- the driver does not name the variable yet, or the hook it names
# is not in the checkout it runs from. Both print skip, so a waiting seam never
# reads as a green line about wiring.
seam_row()
{
	name=$1
	shift
	out=$(python3 scripts/check-audio27-builder.py "$@" 2>&1)
	rc=$?
	case "$rc" in
	0) printf 'ok   %-34s %s\n' "$name" "$(printf '%s' "$out" | tail -1)" ;;
	3) printf 'skip %-34s %s\n' "$name" "$(printf '%s' "$out" | tail -1)" ;;
	*) printf 'FAIL %-34s %s\n' "$name" "$(printf '%s' "$out" | tail -1)"; fail=1 ;;
	esac
}
# The PAC assertions and their fixtures. Without a series or a gates checkout
# the selection row degrades to a skip rather than falling back to this tree's
# copy, which may list a patch the effective series holds out.
pac_rows()
{
	run "PAC IO signatures" python3 scripts/check-audio27-fptrs.py --repo "$repo"
	run "PAC IO negative cases" python3 scripts/tests/test-audio27-fptrs.py
	run "PAC weak-link cases" python3 scripts/tests/test-audio27-weak-link.py
	set --
	if [ -n "${XNU27_SERIES:-}" ]; then
		set -- --series "$XNU27_SERIES"
	elif [ -n "${K60_GATES:-}" ]; then
		set -- --tree "$K60_GATES"
	else
		printf 'skip %-34s no effective series (set K60_GATES or XNU27_SERIES)\n' "PAC weak-link selection"
		return
	fi
	if [ -n "${AUDIO27_LINK_FILELIST:-}" ]; then set -- "$@" --link-filelist "$AUDIO27_LINK_FILELIST"; fi
	if [ -n "${AUDIO27_LINK_SYMBOLS:-}" ]; then set -- "$@" --symbols "$AUDIO27_LINK_SYMBOLS"; fi
	run "PAC weak-link selection" python3 scripts/check-audio27-weak-link.py "$@"
}
pac_rows
if [ "$label" = 'PAC PREFLIGHT' ]; then exit "$fail"; fi
run "migration list + pure C build" python3 scripts/check-audio-migration.py --compile
run "glue vs six kernel symbols" sh scripts/tests/portability/run.sh
run "driver macro really switches it" sh scripts/tests/portability/run-symbols.sh
run "glue needs only the table" sh scripts/tests/portability/run-deps.sh
run "glue builds without warnings" sh scripts/tests/portability/run-warnings.sh
run "warnings gate is honest" python3 scripts/tests/test-warnings-gate.py
run "glue copy set matches the compiler" python3 scripts/check-audio27-closure.py
run "conf-files appender is loud" python3 scripts/tests/test-audio-conffiles.py
run "conf-files hook is honest" python3 scripts/tests/test-conf-files-hook.py
run "define delivery is honest" python3 scripts/tests/test-audio27-define.py
run "one command applies the wiring" python3 scripts/tests/test-apply-audio27-wiring.py
run "weak hook links either way" sh scripts/tests/portability/run-weak-hook.sh
run "probe runs on host" sh scripts/tests/portability/run-probe.sh
run "playback judge tests" python3 scripts/tests/test-judge-audio-capture.py
run "27 triage is honest" python3 scripts/tests/test-triage-audio27.py
run "amplifier host tests" sh drivers/PongAudio/tests/run-tests.sh
run "wiring dry run" sh scripts/tests/test-wiring-dry-run.sh
run "27 interface checker is honest" python3 scripts/tests/test-audio27-kernel-api.py
run "27 product checker is honest" python3 scripts/tests/test-audio27-kernel.py
run "27 include checker is honest" python3 scripts/tests/test-audio27-includes.py
run "27 stub checker is honest" python3 scripts/tests/test-audio27-stubs.py
run "logline checker is honest" python3 scripts/tests/test-audio27-loglines.py
run "27 pages quote printed lines" python3 scripts/check-audio27-loglines.py
run "27 line citations are honest" python3 scripts/tests/test-audio27-lines.py
run "27 pages cite live lines" python3 scripts/check-audio27-lines.py
run "chip table checker is honest" python3 scripts/tests/test-audio27-chips.py
run "judge and driver agree on chips" python3 scripts/check-audio27-chips.py
run "boot argument checker is honest" python3 scripts/tests/test-audio27-bootargs.py
run "audio boot argument is wired" python3 scripts/check-audio27-bootargs.py
run "boot arguments are documented" python3 scripts/check-boot-args.py
run "commands gate is honest" python3 scripts/tests/test-audio27-commands.py
run "27 command citations resolve" python3 scripts/check-audio27-commands.py .
run "row count gate is honest" python3 scripts/tests/test-audio27-rows.py
run "row count holds" python3 scripts/check-audio27-rows.py .
run "27 collision checker is honest" python3 scripts/tests/test-audio27-collisions.py
run "27 closure checker is honest" python3 scripts/tests/test-audio27-closure.py
run "27 patch emitter is honest" python3 scripts/tests/test-emit-audio27-patch.py
run "27 series checker is honest" python3 scripts/tests/test-audio27-series.py
run "sheng abi checker is honest" python3 scripts/tests/test-sheng-abi.py
run "sheng inject checker is honest" python3 scripts/tests/test-sheng-inject.py

xnu27=${XNU27_REPO:-}
if [ -z "$xnu27" ]; then
	for candidate in /opt/k60/trees/ios27-out/feeds/xnu-* "$repo/../xnu"; do
		if [ -f "$candidate/bsd/conf/files" ] || [ -f "$candidate/.cache/xnu-work/bsd/conf/files" ]; then
			xnu27=$candidate
			break
		fi
		done
fi
if [ -n "$xnu27" ]; then
	run "27 kernel interfaces are there" python3 scripts/check-audio27-kernel-api.py "$xnu27"
	run "27 stubs match the declarations" python3 scripts/check-audio27-stubs.py "$xnu27"
	run "27 tree still has the headers" python3 scripts/check-audio27-includes.py "$xnu27"
	run "27 tree has no clashing symbols" python3 scripts/check-audio27-collisions.py "$xnu27"
	optional_row "27 patch emits unchanged" python3 scripts/emit-audio27-patch.py "$xnu27" --out "$(mktemp)" --expect 3665a972557f4b15bcc232124e46f3984c2e5cec781d838845f0366b28eb8da4
	# The series copy is a third copy of the same block. It exists only after
	# the Lead books it; exit 3 means "not booked yet", which is a skip and
	# not a failure, so a quiet absence cannot hide as a green line.
	out=$(python3 scripts/check-audio27-series.py "$xnu27" 2>&1)
	rc=$?
	if [ "$rc" -eq 3 ]; then
		printf 'skip %-34s %s\n' "27 series carries the patch" "$(printf '%s' "$out" | tail -1)"
	elif [ "$rc" -ne 0 ]; then
		printf 'FAIL %-34s %s\n' "27 series carries the patch" "$(printf '%s' "$out" | tail -1)"
		fail=1
	else
		printf 'ok   %-34s %s\n' "27 series carries the patch" "$(printf '%s' "$out" | tail -1)"
	fi
else
	printf 'skip %-34s no 27 xnu tree (set XNU27_REPO)\n' "27 kernel interfaces are there"
fi

# The product itself, when there is one: a built 27 kernel or a boot image.
# Strings always decide; symbols decide when the file has a readable symbol table.
if [ -n "${XNU27_KERNEL:-}" ]; then
	run "27 kernel carries the audio" python3 scripts/check-audio27-kernel.py "$XNU27_KERNEL"
else
	printf 'skip %-34s no built kernel (set XNU27_KERNEL)\n' "27 kernel carries the audio"
fi

sheng=${SHENG_REPO:-}
if [ -z "$sheng" ]; then
	for candidate in "$repo/../UniXNU-sheng" /e/hackios/UniXNU-sheng /mnt/e/hackios/UniXNU-sheng; do
		if [ -f "$candidate/scripts/check-audioreach-host.py" ]; then
			sheng=$candidate
			break
		fi
	done
fi
gates=${K60_GATES:-}
if [ -n "$gates" ] && [ -f "$gates/scripts/build-ios27-linux.sh" ]; then
	seam_row "27 driver takes the conf hook" --gates "$gates" --seam hook
	seam_row "27 driver takes the define" --gates "$gates" --seam define
else
	printf 'skip %-34s no k60-gates checkout (set K60_GATES)\n' "27 driver takes the conf hook"
	printf 'skip %-34s no k60-gates checkout (set K60_GATES)\n' "27 driver takes the define"
fi
# The framework seam does not depend on the driver, so it is measured even
# when there is no k60-gates checkout to read.
seam_row "framework passes env to builder" --seam framework
if [ -n "$sheng" ] && [ -f "$sheng/scripts/check-audioreach-host.py" ]; then
	out=$(cd "$sheng" && python3 scripts/check-audioreach-host.py 2>&1)
	rc=$?
	if [ "$rc" -ne 0 ]; then
		printf 'FAIL %-34s %s\n' "sheng audioreach host tests" "$(printf '%s' "$out" | tail -1)"
		fail=1
	else
		sha=$(git -C "$sheng" rev-parse --short HEAD 2>/dev/null || echo unknown)
		printf 'ok   %-34s %s (%s)\n' "sheng audioreach host tests" \
		    "$(printf '%s' "$out" | tail -1)" "$sha"
		run "sheng abi constants hold" python3 scripts/check-sheng-abi.py --sheng "$sheng"
		run "sheng inject contract holds" python3 scripts/check-sheng-inject.py --sheng "$sheng"
	fi
else
	printf 'skip %-34s no sheng checkout (set SHENG_REPO)\n' "sheng audioreach host tests"
fi

if [ "$fail" -ne 0 ]; then
	echo "PREFLIGHT FAILED"
	exit 1
fi
echo "PREFLIGHT OK"
