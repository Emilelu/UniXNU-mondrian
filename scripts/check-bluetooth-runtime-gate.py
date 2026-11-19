#!/usr/bin/env python3
"""Keep the Bluetooth runtime mounts and the Data mount gate in step.

0526 (runtime mount) and 0527 (launchd cache) only exist inside
#if defined(XNU_OWNER_DATA_MOUNT) in bsd/kern/kern_exec.c, because the addon is
unpacked onto the Data volume. The iOS 27 defconfig does not set that switch, so
on this branch the mounts are compiled out by design.

The invariant this checker enforces is one-directional: the gate may stay
closed without the mounts, but it must never open without them. Flipping
CONFIG_XNU_OWNER_DATA_MOUNT=y in configs/mondrian_ios27_defconfig is therefore a
change that cannot land silently -- the build fails here until the two patches
are in the series, which is the whole point of the F3 step.

Usage:
    python3 scripts/check-bluetooth-runtime-gate.py
    python3 scripts/check-bluetooth-runtime-gate.py --tree /path/to/tree --out report
"""
import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SERIES = ROOT / "patches" / "xnu-12377" / "series"
DEFCONFIG = ROOT / "configs" / "mondrian_ios27_defconfig"
KERN_EXEC = pathlib.Path("bsd/kern/kern_exec.c")

MOUNTS = ("0526-", "0527-")
SWITCH = "CONFIG_XNU_OWNER_DATA_MOUNT"
GATE = "#if defined(XNU_OWNER_DATA_MOUNT) && XNU_OWNER_DATA_MOUNT"


def series_entries(path):
    entries = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        entries.append(line)
    return entries


def mounts_in_series(entries):
    return [e for e in entries if any(e.startswith(prefix) for prefix in MOUNTS)]


def gate_enabled(defconfig):
    pattern = re.compile(r"^\s*" + re.escape(SWITCH) + r"\s*=\s*([yn])\s*$")
    for line in defconfig.read_text().splitlines():
        match = pattern.match(line)
        if match:
            return match.group(1) == "y"
    return False


def prepare_in_gate(tree):
    """Return (found, inside) for native_bt_runtime_prepare in kern_exec.c."""
    lines = (tree / KERN_EXEC).read_text().splitlines()
    target = None
    for number, line in enumerate(lines):
        if "native_bt_runtime_prepare(proc_t p" in line:
            target = number
            break
    if target is None:
        return False, False
    depth = 0
    gate_depth = None
    for number in range(target):
        stripped = lines[number].strip()
        if stripped.startswith('#if'):
            depth += 1
            if stripped == GATE:
                gate_depth = depth
        elif stripped.startswith('#endif'):
            depth -= 1
    inside = gate_depth is not None and depth >= gate_depth
    return True, inside


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--series", default=str(SERIES))
    parser.add_argument("--defconfig", default=str(DEFCONFIG))
    parser.add_argument("--tree", help="a patched tree, to check where the call sits")
    parser.add_argument("--out", help="write a JSON report here")
    args = parser.parse_args()

    failures = []
    entries = series_entries(pathlib.Path(args.series))
    mounts = mounts_in_series(entries)
    enabled = gate_enabled(pathlib.Path(args.defconfig))

    print(f"series: {len(entries)} entries, mounts {', '.join(mounts) or 'none'}")
    print(f"defconfig: {SWITCH}={'y' if enabled else 'absent'}")

    if enabled and not mounts:
        failures.append(
            f"{SWITCH}=y without {MOUNTS[0]}*/{MOUNTS[1]}* in the series: the Data volume "
            "now mounts, so the runtime overlays must be there too"
        )
    if not enabled and mounts:
        print("state: gated-off -- the mounts are in the series but the switch is closed,")
        print("       so they are compiled out; this is the documented stage-0 boundary")
    if enabled and mounts:
        print("state: active -- the mounts are in the series and the switch is open")

    inside = None
    if args.tree:
        found, inside = prepare_in_gate(pathlib.Path(args.tree))
        if not found:
            failures.append("native_bt_runtime_prepare is missing from bsd/kern/kern_exec.c")
        elif not inside:
            failures.append(
                "native_bt_runtime_prepare sits outside the XNU_OWNER_DATA_MOUNT gate"
            )
        else:
            print("tree: native_bt_runtime_prepare is inside the Data mount gate")

    report = {
        "series_entries": len(entries),
        "mounts": mounts,
        "gate_enabled": enabled,
        "state": "active" if enabled else "gated-off",
        "prepare_in_gate": inside,
        "failures": failures,
        "hardware_verified": False,
    }
    if args.out:
        out = pathlib.Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(f"report: {out / 'report.json'}")

    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        print("bluetooth-runtime-gate: FAILED")
        return 1
    print("bluetooth-runtime-gate: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
