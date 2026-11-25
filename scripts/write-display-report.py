#!/usr/bin/env python3
"""Write build/native-legacy-display/build-report.json for the board archive.

The kernel builder (scripts/build-xnu-generic.sh:674-689) refuses the archive
unless the report's archive_sha256 matches the bytes and every source_sha256
entry matches the file under the tree root.

    scripts/write-display-report.py <Tree>
"""
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
out = root / "build/native-legacy-display"
archive = out / "libNativeLegacyDisplay.late.a"

sources = [
    root / "drivers/GopFramebuffer" / name
    for name in (
        "NativeLegacyDisplay.cpp",
        "NativeGOPPresenter.cpp",
        "NativeLegacyRequest.h",
        "NativeGOPWire.h",
        "NativeHalfCodes.h",
        "NativeGpuTrace.h",
    )
]
sources.append(out / "OriginalLegacyFramebufferABI.h")

report = {
    "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    "source_sha256": {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sources
        if path.exists()
    },
}
(out / "build-report.json").write_text(json.dumps(report, indent=2) + "\n")
print(f"wrote {out / 'build-report.json'} ({len(report['source_sha256'])} sources)")
