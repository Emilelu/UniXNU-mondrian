#!/usr/bin/env python3
"""Gate: the Data window identity in every config must match what the device publishes.

Two independent facts are checked, both derived from artefacts rather than from
prose:

1. Every ``configs/*defconfig`` that mounts a Data window
   (``CONFIG_XNU_OWNER_DATA_MOUNT=y``) must name a volume UUID that actually
   appeared in the newest console log for the ``PongDataWindow``. When no console
   log is available the check reports SKIP rather than guessing.
2. The UFS Data branch of ``offline-owner-systemos-mount.patch`` must accept a
   window at least as large as the Data window recorded in the newest
   ``unixnu`` manifest dump.

Why this exists: P-152, P-153 and P-210. The config named the 32 MiB seed's
volume UUID while the device carried a 19.87 GiB volume, and the size ceiling
stayed at the seed-era 2 GiB. Both failures produced a kernel self-panic with no
obvious relation to the config value.

P-210 is the reason this walks *all* the configs instead of just
``configs/mondrian_defconfig``: the wifi board has its own defconfig, it carries
``CONFIG_XNU_OWNER_DATA_MOUNT=y``, and it was never scored by this gate -- which
is exactly how a seed UUID reached a shipped build (wifi-20261116c0, silent for
five seconds and then a root-mount panic with no console output at all).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO / "configs"
CONFIG = CONFIG_DIR / "mondrian_defconfig"
PATCH = REPO / "patches" / "xnu" / "offline-owner-systemos-mount.patch"
EVIDENCE = Path("/mnt/e/k60-work/evidence")
MANIFEST = Path("/mnt/e/k60-work/scratch/cur-manifest.bin")

DATA_MOUNT_KEY = "CONFIG_XNU_OWNER_DATA_MOUNT=y"
UUID_RE = re.compile(r"[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}")
CONFIG_RE = re.compile(
    r'^CONFIG_XNU_OWNER_DATA_VOLUME_UUID\s*=\s*"([^"]+)"', re.MULTILINE)
CEILING_RE = re.compile(
    r"size\s*>\s*UINT64_C\(0x([0-9a-fA-F]+)\)")
WINDOW_RE = re.compile(
    r"window media uuid=([0-9A-Fa-f-]{36})\b.*depth=")
DATALINE_RE = re.compile(r"^\s*Data:\s*off=\d+\s+size=(\d+)", re.MULTILINE)


def data_configs(config_dir: Path | None = None) -> list[Path]:
    """Every defconfig that mounts a Data window, newest name order.

    Falls back to ``configs/mondrian_defconfig`` when nothing carries the mount
    key (an older tree, or a fixture that only exercises the UUID branch).
    """
    directory = Path(config_dir) if config_dir is not None else CONFIG_DIR
    found: list[Path] = []
    for path in sorted(directory.glob("*defconfig")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if DATA_MOUNT_KEY in text:
            found.append(path)
    if found:
        return found
    fallback = directory / "mondrian_defconfig"
    return [fallback] if fallback.is_file() else []


def newest_console(evidence: Path | None = None) -> Path | None:
    root = Path(evidence) if evidence is not None else EVIDENCE
    logs = sorted(root.glob("usblog-*/console.log"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    for log in logs:
        try:
            if log.stat().st_size > 4096:
                return log
        except OSError:
            continue
    return None


def check_uuid(problems: list[str], notes: list[str],
               config_dir: Path | None = None,
               evidence: Path | None = None) -> None:
    paths = data_configs(config_dir)
    if not paths:
        problems.append("no defconfig mounts a Data window (CONFIG_XNU_OWNER_DATA_MOUNT=y)")
        return

    configured: dict[str, str] = {}
    for path in paths:
        label = path.name
        match = CONFIG_RE.search(path.read_text(encoding="utf-8", errors="replace"))
        if not match:
            problems.append(f"{label}: CONFIG_XNU_OWNER_DATA_VOLUME_UUID missing")
            continue
        value = match.group(1).upper()
        if not UUID_RE.fullmatch(value):
            problems.append(f"{label}: configured Data volume UUID is not a UUID: {value}")
            continue
        configured[label] = value

    if not configured:
        return

    log = newest_console(evidence)
    if log is None:
        notes.append("no console log >=4 KiB under the evidence root -> UUID cross-check skipped")
        return
    text = log.read_text(encoding="utf-8", errors="replace")
    observed = {u.upper() for u in WINDOW_RE.findall(text)}
    if not observed:
        notes.append(f"{log.name} has no 'window media uuid' lines -> UUID cross-check skipped")
        return

    for label, value in configured.items():
        if value in observed:
            notes.append(f"{label}: Data UUID {value} observed in {log.parent.name}")
            continue
        problems.append(
            f"{label}: configured Data volume UUID {value} never appeared in the newest "
            f"console log ({log.parent.name}); observed volumes: "
            f"{', '.join(sorted(observed))}. See P-152/P-210 - take the UUID from the log, "
            "not from seed/k60-data-seed.dbr.")


def check_ceiling(problems: list[str], notes: list[str],
                  patch: Path | None = None,
                  manifest: Path | None = None) -> None:
    patch_path = Path(patch) if patch is not None else PATCH
    manifest_path = Path(manifest) if manifest is not None else MANIFEST
    if not patch_path.is_file():
        problems.append(f"{patch_path.name}: patch is missing")
        return
    text = patch_path.read_text(encoding="utf-8", errors="replace")
    ceilings = [int(v, 16) for v in CEILING_RE.findall(text)]
    if not ceilings:
        problems.append(f"{patch_path.name}: no size ceiling found")
        return
    ceiling = max(ceilings)
    if not manifest_path.is_file():
        notes.append("no manifest dump at /mnt/e/k60-work/scratch/cur-manifest.bin -> ceiling cross-check skipped")
        return
    raw = manifest_path.read_bytes()
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


def run(config_dir: Path | None = None, evidence: Path | None = None,
        patch: Path | None = None, manifest: Path | None = None) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    notes: list[str] = []
    check_uuid(problems, notes, config_dir=config_dir, evidence=evidence)
    check_ceiling(problems, notes, patch=patch, manifest=manifest)
    return problems, notes


def main() -> int:
    problems, notes = run()
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
