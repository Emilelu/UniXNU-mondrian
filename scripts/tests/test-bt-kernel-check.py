#!/usr/bin/env python3
"""Exercise scripts/check-bluetooth-kernel.py on synthetic artifacts."""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-bluetooth-kernel.py"
NEEDLES = [b"com.apple.uart.sk.bluetooth", b"com.apple.uart.bluetooth", b"[bluetooth power]", b"[bluetooth sk]",
           b"com.apple.uart", b"qbt_power_on", b"qbt_boot", b"qbt_firmware",
           b"K60BluetoothRadio", b"mac-address-bluetooth0"]

failures = []


def check(condition, message):
    if condition:
        print(f"PASS {message}")
    else:
        failures.append(message)
        print(f"FAIL {message}")


def run(kernel, extra=()):
    return subprocess.run([sys.executable, str(SCRIPT), "--kernel", str(kernel), *extra],
                          capture_output=True, text=True)


with tempfile.TemporaryDirectory() as tmp:
    good = Path(tmp) / "good.macho"
    good.write_bytes(b"\x00".join(NEEDLES))
    r = run(good)
    check(r.returncode == 0, f"complete kernel passes (rc={r.returncode})")
    check("bluetooth-kernel-check: OK" in r.stdout, "summary line on success")

    bad = Path(tmp) / "bad.macho"
    bad.write_bytes(b"\x00".join(N for N in NEEDLES if N != b"qbt_power_on"))
    r = run(bad)
    check(r.returncode == 1, f"kernel without the power sysctl fails (rc={r.returncode})")
    check("qbt_power_on not found" in r.stdout, "failure names the missing needle")

    r = run(good, ["--require", "log-bluetooth"])
    check(r.returncode == 1, f"--require of an absent string fails (rc={r.returncode})")
    r = run(good, ["--require", "qbt_firmware"])
    check(r.returncode == 0, f"--require of a present string passes (rc={r.returncode})")

    missing = Path(tmp) / "nope.macho"
    r = subprocess.run([sys.executable, str(SCRIPT), "--kernel", str(missing)],
                       capture_output=True, text=True)
    check(r.returncode != 0, "absent kernel exits non-zero")

if failures:
    print(f"bluetooth-kernel-check test: {len(failures)} failure(s)")
    sys.exit(1)
print("bluetooth-kernel-check test: OK")
