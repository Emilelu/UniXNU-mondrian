#!/bin/bash
# macOS GitHub Actions preflight for the K60 device repo.
# Runs in the UniXNU core checkout; DEVICE_DIR points at this repo.
set -euo pipefail
dir=$(cd "$(dirname "$0")" && pwd)
"$dir/apply-core-patches.sh" "$PWD"

# The pong Mac scripts stand in the Pong developer machine: they pin the Xcode
# developer directory and the pong driver sources to /Volumes/PongDev, and
# build-xnu-4k-baseline.sh only builds the ArmDT/ArmCpu archives when
# PONG_NATIVE_DRIVER_SOURCE is set. On a runner the device checkout is the
# source, and the Xcode of the image is in DEVELOPER_DIR.
if [ -n "${GITHUB_ENV:-}" ] && [ -n "${DEVICE_DIR:-}" ]; then
  echo "PONG_NATIVE_DRIVER_SOURCE=$DEVICE_DIR" >> "$GITHUB_ENV"
fi

python3 - "$DEVICE_DIR" <<'PY'
import pathlib
import sys

device = pathlib.Path(sys.argv[1])
replacements = [
    # macos-26 is arm64; the guard only needs to reject a non-Darwin host.
    ("platform.system() != 'Darwin' or platform.machine() != 'x86_64'",
     "platform.system() != 'Darwin'"),
    # Never override the runner's Xcode with the Pong developer path.
    ("DEVELOPER = '/Volumes/PongDev/Applications/Xcode.app/Contents/Developer'",
     "DEVELOPER = os.environ.get('DEVELOPER_DIR', '/Applications/Xcode.app/Contents/Developer')"),
]
for path in sorted(device.glob('scripts/build-pong-*-macos.py')):
    text = path.read_text()
    for old, new in replacements:
        text = text.replace(old, new)
    path.write_text(text)
PY

# Install the auto-slide prelink wrapper (device-repo copy; submodule untouched).
if [ -f kits/XnuPrelink/emit_prelink.py ]; then
  cp kits/XnuPrelink/emit_prelink.py kits/XnuPrelink/emit_prelink_orig.py
  cp "$dir/emit_prelink_autoslide.py" kits/XnuPrelink/emit_prelink.py
  echo "installed auto-slide prelink wrapper"
else
  echo "WARNING: kits/XnuPrelink/emit_prelink.py missing (submodule not checked out)" >&2
fi
