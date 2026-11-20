#!/usr/bin/env python3
"""Six cases for scripts/check-audio27-rows.py."""

import io
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
GATE = os.path.join(REPO, "scripts/check-audio27-rows.py")

PREFLIGHT = """#!/bin/sh
ROWS_EXPECTED=%s
if [ -z "${K60_PREFLIGHT_INNER:-}" ]; then
	printf 'ROWS FAILED %%s rows printed, %%s declared\n' "$rows" "$ROWS_EXPECTED"
fi
"""

PAGE = """# an audio page

随后%d行 `ok`、一行随环境的 `skip`。
"""

RECORD = """[evidence.audio27]
result = "preflight: %d host rows plus one skip"
"""


def tree(root, declared=51, ok=50, skip=1, host=50, tail=True, page=True, record=True):
    os.makedirs(os.path.join(root, "scripts"))
    os.makedirs(os.path.join(root, "docs/research/audio"))
    text = PREFLIGHT % declared if declared is not None else PREFLIGHT.replace("ROWS_EXPECTED=%s\n", "")
    if not tail:
        text = text.replace(text.strip().splitlines()[-3], "true")
    io.open(os.path.join(root, "scripts/check-audio27-preflight.sh"), "w").write(text)
    if page:
        body = (PAGE % ok).replace("一行", "%d行" % skip, 1) if skip != 1 else PAGE % ok
        io.open(os.path.join(root, "docs/research/audio/PAGE.md"), "w").write(body)
    if record:
        io.open(os.path.join(root, "porting.toml"), "w").write(RECORD % host)


def run(root):
    return subprocess.run([sys.executable, GATE, root], capture_output=True, text=True)


def case(root, name, want, *needles, **kwargs):
    tree(root, **kwargs)
    done = run(root)
    text = done.stdout + done.stderr
    if done.returncode != want:
        print("FAILED %s: exit %d, wanted %d\n%s" % (name, done.returncode, want, text.strip()))
        return False
    for needle in needles:
        if needle not in text:
            print("FAILED %s: %r missing\n%s" % (name, needle, text.strip()))
            return False
    return True


def main():
    base = tempfile.mkdtemp(prefix="rows-")
    kept = 0
    cases = [
        ("consistent", 0, ["ROWS OK 51 rows declared"], {}),
        ("page overcounts", 1, ["but the preflight", "declares 51"], {"skip": 2}),
        ("record drifts", 1, ["porting.toml records 49 host rows plus one skip"], {"host": 49}),
        ("no constant", 1, ["declares no ROWS_EXPECTED"], {"declared": None}),
        ("no comparison", 1, ["no longer compares the rows it printed"], {"tail": False}),
        ("no page claim", 1, ["no audio page states how many rows"], {"page": False}),
    ]
    for name, want, needles, kwargs in cases:
        root = os.path.join(base, name.replace(" ", "-"))
        if case(root, name, want, *needles, **kwargs):
            kept += 1
    shutil.rmtree(base, ignore_errors=True)
    if kept != len(cases):
        print("TESTS FAILED %d of %d cases" % (len(cases) - kept, len(cases)))
        return 1
    print("TESTS OK %d cases" % len(cases))
    return 0


if __name__ == "__main__":
    sys.exit(main())
