#!/bin/sh
# Candidate-only host contract check for the UNINTEGRATED rail observation core.
# Not production code, not a compliance result. One fresh process per case.
set -eu
cd "$(dirname "$0")"
OUT="${1:-$(mktemp -d)}"
CC="${CC:-cc}"
mkdir -p "$OUT"
$CC -std=c11 -O1 -Wall -Wextra -Werror -DK60_RAIL_OBS_HOST_TEST -pthread \
    -I . -o "$OUT/candidate-tests" entry.c rail_obs.c
"$OUT/candidate-tests" --list > "$OUT/cases.txt"
if grep -Evq '^[a-z0-9][a-z0-9-]*$' "$OUT/cases.txt"; then
    echo "CANDIDATE_CORE_RESULT: INFRA bad --list line" >&2
    exit 2
fi
pass=0
fail=0
while IFS= read -r case; do
    if "$OUT/candidate-tests" candidate "$case" > "$OUT/$case.log" 2>&1; then
        pass=$((pass + 1))
    else
        fail=$((fail + 1))
        echo "FAIL $case"
        tail -3 "$OUT/$case.log"
    fi
done < "$OUT/cases.txt"
total=$((pass + fail))
echo "CANDIDATE_CORE_RESULT: $([ "$fail" -eq 0 ] && echo PASS || echo FAIL) $pass/$total cases (candidate-only, not canonical compliance)"
[ "$fail" -eq 0 ]
