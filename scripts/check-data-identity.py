#!/usr/bin/env python3
"""Gate: the Data window identity in the config must match what the device publishes.

Two independent facts are checked, both derived from artefacts rather than from
prose:

1. ``CONFIG_XNU_OWNER_DATA_VOLUME_UUID`` must equal a volume UUID that actually
   appeared in the newest console log for the ``PongDataWindow``. When no console
   log is available the check reports SKIP rather than guessing.
2. The UFS Data branch of ``offline-owner-systemos-mount.patch`` must accept a
   window at least as large as the Data window recorded in the newest
   ``unixnu`` manifest dump.

Why this exists: P-152 and P-153. The config named the 32 MiB seed's volume UUID
while the device carried a 19.87 GiB volume, and the size ceiling stayed at the
seed-era 2 GiB. Both failures produced a kernel self-panic with no obvious
relation to the config value.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CONFIG = REPO / "configs" / "mondrian_defconfig"
PATCH = REPO / "patches" / "xnu" / "offline-owner-systemos-mount.patch"
EVIDENCE = Path("/mnt/e/k60-work/evidence")
MANIFEST = Path("/mnt/e/k60-work/scratch/cur-manifest.bin")

UUID_RE = re.compile(r"[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}")
CONFIG_RE = re.compile(
    r'^CONFIG_XNU_OWNER_DATA_VOLUME_UUID\s*=\s*"([^"]+)"', re.MULTILINE)
CEILING_RE = re.compile(
    r"size\s*>\s*UINT64_C\(0x([0-9a-fA-F]+)\)")
WINDOW_RE = re.compile(
    r"window media uuid=([0-9A-Fa-f-]{36})\b.*depth=")
DATALINE_RE = re.compile(r"^\s*Data:\s*off=\d+\s+size=(\d+)", re.MULTILINE)


def newest_console() -> Path | None:
    logs = sorted(EVIDENCE.glob("usblog-*/console.log"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    for log in logs:
        try:
            if log.stat().st_size > 4096:
                return log
        except OSError:
            continue
    return None


def check_uuid(problems: list[str], notes: list[str]) -> None:
    match = CONFIG_RE.search(CONFIG.read_text(encoding="utf-8"))
    if not match:
        problems.append("configs/mondrian_defconfig: CONFIG_XNU_OWNER_DATA_VOLUME_UUID missing")
        return
    configured = match.group(1).upper()
    if not UUID_RE.fullmatch(configured):
        problems.append(f"configured Data volume UUID is not a UUID: {configured}")
        return

    log = newest_console()
    if log is None:
        notes.append("no console log >=4 KiB under /mnt/e/k60-work/evidence -> UUID cross-check skipped")
        return
    text = log.read_text(encoding="utf-8", errors="replace")
    observed = {u.upper() for u in WINDOW_RE.findall(text)}
    if not observed:
        notes.append(f"{log.name} has no 'window media uuid' lines -> UUID cross-check skipped")
        return
    if configured in observed:
        notes.append(f"Data UUID {configured} observed in {log.parent.name}")
        return
    problems.append(
        "configured Data volume UUID "
        f"{configured} never appeared in the newest console log "
        f"({log.parent.name}); observed volumes: {', '.join(sorted(observed))}. "
        "See P-152 - take the UUID from the log, not from seed/k60-data-seed.dbr.")


def check_ceiling(problems: list[str], notes: list[str]) -> None:
    text = PATCH.read_text(encoding="utf-8", errors="replace")
    ceilings = [int(v, 16) for v in CEILING_RE.findall(text)]
    if not ceilings:
        problems.append("offline-owner-systemos-mount.patch: no size ceiling found")
        return
    ceiling = max(ceilings)
    if not MANIFEST.is_file():
        notes.append("no manifest dump at /mnt/e/k60-work/scratch/cur-manifest.bin -> ceiling cross-check skipped")
        return
    raw = MANIFEST.read_bytes()
    rows = DATALINE_RE.findall(raw.decode("latin-1"))
    if not rows:
        notes.append("manifest dump has no Data row -> ceiling cross-check skipped")
        return
    data_bytes = max(int(r) for r in rows)
    if data_bytes > ceiling:
        problems.append(
            f"UFS Data ceiling 0x{ceiling:x} ({ceiling} B) is below the device's Data "
            f"window ({data_bytes} B). See P-153.")
    else:
        notes.append(
            f"ceiling 0x{ceiling:x} covers the {data_bytes} B Data window")


def main() -> int:
    problems: list[str] = []
    notes: list[str] = []
    check_uuid(problems, notes)
    check_ceiling(problems, notes)
    for note in notes:
        print(f"  · {note}")
    if problems:
        print("❌ Data 卷身份检查未通过：")
        for problem in problems:
            print(f"   - {problem}")
        return 1
    print("✅ Data 卷身份与尺寸天花板检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
