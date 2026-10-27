#!/bin/bash
# macOS GitHub Actions preflight for the K60 device repo.
# Runs in the UniXNU core checkout; DEVICE_DIR points at this repo.
set -euo pipefail
dir=$(cd "$(dirname "$0")" && pwd)
"$dir/apply-core-patches.sh" "$PWD"
python3 - "$DEVICE_DIR" <<'PY'
import pathlib
import sys

device = pathlib.Path(sys.argv[1])
old = "platform.system() != 'Darwin' or platform.machine() != 'x86_64'"
new = "platform.system() != 'Darwin'"
for path in device.glob('scripts/build-pong-*-macos.py'):
    text = path.read_text()
    if old in text:
        path.write_text(text.replace(old, new))
PY
