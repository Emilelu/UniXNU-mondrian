#!/bin/sh
# Extra candidate-only checks: sanitizers, repeatability, symbol hygiene.
# Not production evidence and not a compliance result.
set -eu
cd "$(dirname "$0")"
OUT="${1:-$(mktemp -d)}"
CC="${CC:-cc}"
mkdir -p "$OUT"
$CC -std=c11 -O1 -g -Wall -Wextra -Werror -DK60_RAIL_OBS_HOST_TEST -pthread \
    -fsanitize=address,undefined \
    -I . -o "$OUT/candidate-tests-san" entry.c rail_obs.c
"$OUT/candidate-tests-san" --list > "$OUT/cases.txt"
san_fail=0
while IFS= read -r case; do
    if ! "$OUT/candidate-tests-san" candidate "$case" > "$OUT/san-$case.log" 2>&1; then
        san_fail=$((san_fail + 1))
        echo "SANITIZER FAIL $case"
    elif grep -Eq 'ERROR: (AddressSanitizer|LeakSanitizer)|runtime error:' "$OUT/san-$case.log"; then
        san_fail=$((san_fail + 1))
        echo "SANITIZER REPORT $case"
    fi
done < "$OUT/cases.txt"
echo "ASAN_UBSAN: $([ "$san_fail" -eq 0 ] && echo CLEAN || echo FINDINGS) ($san_fail)"
if nm "$OUT/candidate-tests-san" 2>/dev/null | grep -q K60PmicRail; then
    echo "SYMBOLS: FAIL (candidate links a production rail symbol)"
else
    echo "SYMBOLS: CLEAN (no K60PmicRail symbol)"
fi
i=1
while [ "$i" -le 10 ]; do
    if ! ./run-tests.sh "$OUT/run-$i" > "$OUT/run-$i.log" 2>&1; then
        echo "REPEAT: FAIL at iteration $i"
        exit 1
    fi
    i=$((i + 1))
done
echo "REPEAT: 10/10 full candidate runs passed"
echo "CASES: $(wc -l < "$OUT/cases.txt")"
[ "$san_fail" -eq 0 ]
