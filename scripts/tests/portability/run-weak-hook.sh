#!/bin/sh
# Prove the 27 call site links with or without the glue behind it.
#
# The hook in bsd/kern/bsd_init.c declares pong_audio_amp_probe() weak and
# tests it for null. That is only worth writing if it really links when the
# symbol is absent, so this compiles the block the applier writes, links it
# twice - once with no provider, once with one - and runs both.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../../.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

python3 - "$repo" "$work/call.c" <<'PY'
import importlib.util, pathlib, sys
repo, out = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("wiring", pathlib.Path(repo) / "scripts" / "apply-audio27-wiring.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
src = "#include <stddef.h>\n" + "static void tail(void)\n{\n" + mod.INIT_BLOCK + "}\nint main(void) { tail(); return 0; }\n"
pathlib.Path(out).write_text(src)
PY

cat > "$work/provider.c" <<'EOF'
#include <stdlib.h>
int pong_audio_amp_probe(void) { exit(42); return 0; }
EOF

cc -std=gnu11 -Wall -Wextra -Werror -o "$work/absent" "$work/call.c" 2> "$work/absent.log" || {
	cat "$work/absent.log"
	echo "FAIL: the call site does not link without the glue";
	exit 1
}
"$work/absent"
absent_rc=$?

cc -std=gnu11 -Wall -Wextra -Werror -o "$work/present" "$work/call.c" "$work/provider.c"
set +e
"$work/present"
present_rc=$?
set -e

[ "$absent_rc" -eq 0 ] || { echo "FAIL: the hook ran although no provider was linked (exit $absent_rc)"; exit 1; }
[ "$present_rc" -eq 42 ] || { echo "FAIL: the hook never reached the provider (exit $present_rc)"; exit 1; }
echo "WEAK OK absent links and skips, present runs (exit 42)"