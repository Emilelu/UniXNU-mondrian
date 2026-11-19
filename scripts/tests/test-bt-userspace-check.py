#!/usr/bin/env python3
"""Exercise scripts/check-bluetooth-userspace.py on synthetic stages."""
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-bluetooth-userspace.py"
NATIVE = "cfd94854d0a2efd3ca4a2de6e55349f43fd0d274a4b8bfa9937f29d9f7208cb1"

failures = []


def check(condition, message):
    if condition:
        print(f"PASS {message}")
    else:
        failures.append(message)
        print(f"FAIL {message}")


def macho(filetype=2, dylibs=("/usr/lib/libSystem.B.dylib",), platform=2,
          minos=0x1B0000, cputype=0x0100000C, subtype=2):
    commands = struct.pack("<IIIIII", 0x32, 24, platform, minos, 0, 0)
    for name in dylibs:
        raw = name.encode() + b"\0"
        raw += b"\0" * (-len(raw) % 8)
        commands += struct.pack("<IIIIII", 0x0C, 24 + len(raw), 24, 0, 0, 0) + raw
    header = struct.pack("<IiiIIIII", 0xFEEDFACF, cputype, subtype, filetype,
                         len(dylibs) + 1, len(commands), 0, 0)
    return header + commands


def build_stage(root, bluetoothd=None, bluetool=None, type0=None, report=None,
                firmware=b"firmware", runtime=None, manifest_bytes=None,
                manifest_sha=None):
    stage = Path(root) / "stage"
    (stage / "userland" / "bin").mkdir(parents=True)
    (stage / "userland" / "lib").mkdir(parents=True)
    (stage / "firmware" / "qca").mkdir(parents=True)
    (stage / "userland" / "bin" / "bluetoothd").write_bytes(
        bluetoothd if bluetoothd is not None else macho())
    (stage / "userland" / "bin" / "BlueTool").write_bytes(
        bluetool if bluetool is not None else macho(dylibs=("/usr/lib/libxpc.dylib",
                                                            "/usr/lib/libSystem.B.dylib"))
        + b"com.apple.BlueTool\0")
    (stage / "userland" / "lib" / "QcaBTType0.dylib").write_bytes(
        type0 if type0 is not None else macho(filetype=6))
    body = report if report is not None else {
        "built": True,
        "target": "arm64e-apple-ios27.0",
        "native_input_sha256": NATIVE,
        "native_entitlements_preserved": True,
        "hardware_verified": False,
    }
    (stage / "report.json").write_text(json.dumps(body))
    marker = runtime if runtime is not None else {
        "native_input_sha256": NATIVE,
        "files": [],
    }
    (stage / "userland" / "bin" / "QcaBluetooth.runtime").write_text(json.dumps(marker))
    digest = hashlib.sha256(firmware).hexdigest()
    (stage / "firmware" / "qca" / "hpbtfw21.tlv").write_bytes(firmware)
    manifest = {
        "commit": "test",
        "files": {
            "hpbtfw21.tlv": {"bytes": len(firmware), "sha256": manifest_sha or digest},
            "hpnv20.b2f": {"bytes": 4, "sha256": hashlib.sha256(b"nvm!").hexdigest()},
        },
    }
    if manifest_bytes is not None:
        (stage / "manifest.json").write_bytes(manifest_bytes)
    else:
        (stage / "manifest.json").write_text(json.dumps(manifest))
    return stage


def run(stage, extra=()):
    return subprocess.run([sys.executable, str(SCRIPT), "--stage", str(stage),
                           "--manifest", str(Path(stage) / "manifest.json"), *extra],
                          capture_output=True, text=True)


with tempfile.TemporaryDirectory() as tmp:
    stage = build_stage(tmp)
    # The staged bluetoothd is synthetic, so it already differs from the
    # native input the report names; one firmware file also has to exist for
    # every manifest entry, so drop the second entry from the manifest view.
    r = run(stage)
    check(r.returncode == 1 and "firmware complete" in r.stdout,
          f"a manifest entry without a file fails (rc={r.returncode})")

    stage = build_stage(Path(tmp) / "good")
    manifest_path = stage / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    del manifest["files"]["hpnv20.b2f"]
    manifest_path.write_text(json.dumps(manifest))
    r = run(stage, ["--require", "com.apple.BlueTool"])
    check(r.returncode == 0, f"complete stage passes (rc={r.returncode})")
    check("bluetooth-userspace-check: OK" in r.stdout, "summary line on success")

    stage = build_stage(Path(tmp) / "nolibxpc",
                        bluetool=macho(dylibs=("/usr/lib/libSystem.B.dylib",)))
    manifest_path = stage / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    del manifest["files"]["hpnv20.b2f"]
    manifest_path.write_text(json.dumps(manifest))
    r = run(stage)
    check(r.returncode == 1, "BlueTool without libxpc fails")
    check("BlueTool links libxpc" in r.stdout, "the failure names the missing dylib")

    stage = build_stage(Path(tmp) / "oldminos",
                        bluetool=macho(dylibs=("/usr/lib/libxpc.dylib",), minos=0x1A0000))
    manifest_path = stage / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    del manifest["files"]["hpnv20.b2f"]
    manifest_path.write_text(json.dumps(manifest))
    r = run(stage)
    check(r.returncode == 1 and "BlueTool ios 27" in r.stdout,
          "BlueTool built for iOS 26 fails")

    stage = build_stage(Path(tmp) / "arm64", bluetoothd=macho(subtype=0))
    manifest_path = stage / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    del manifest["files"]["hpnv20.b2f"]
    manifest_path.write_text(json.dumps(manifest))
    r = run(stage)
    check(r.returncode == 1 and "bluetoothd mach-o" in r.stdout,
          "a non-arm64e bluetoothd fails")

    stage = build_stage(Path(tmp) / "badtype", type0=macho(filetype=2))
    manifest_path = stage / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    del manifest["files"]["hpnv20.b2f"]
    manifest_path.write_text(json.dumps(manifest))
    r = run(stage)
    check(r.returncode == 1 and "QcaBTType0 arm64e dylib" in r.stdout,
          "an executable posing as the type-0 library fails")

    for name, body, needle in (
        ("built", {"built": False}, "report built"),
        ("verified", {"hardware_verified": True}, "report not hardware verified"),
        ("input", {"native_input_sha256": "0" * 64}, "report native input"),
        ("target", {"target": "arm64e-apple-ios26.0"}, "report target"),
    ):
        stage = build_stage(Path(tmp) / name)
        manifest_path = stage / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        del manifest["files"]["hpnv20.b2f"]
        manifest_path.write_text(json.dumps(manifest))
        report = json.loads((stage / "report.json").read_text())
        report.update(body)
        (stage / "report.json").write_text(json.dumps(report))
        r = run(stage)
        check(r.returncode == 1 and needle in r.stdout, f"report with {name} changed fails")

    stage = build_stage(Path(tmp) / "hash")
    manifest_path = stage / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    del manifest["files"]["hpnv20.b2f"]
    manifest["files"]["hpbtfw21.tlv"]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest))
    r = run(stage)
    check(r.returncode == 1 and "firmware bytes and hashes" in r.stdout,
          "a firmware hash mismatch fails")

    stage = build_stage(Path(tmp) / "marker", runtime={"native_input_sha256": "0" * 64})
    manifest_path = stage / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    del manifest["files"]["hpnv20.b2f"]
    manifest_path.write_text(json.dumps(manifest))
    r = run(stage)
    check(r.returncode == 1 and "runtime marker input" in r.stdout,
          "a runtime marker naming another input fails")

    stage = build_stage(Path(tmp) / "needle",
                        bluetool=macho(dylibs=("/usr/lib/libxpc.dylib",)))
    manifest_path = stage / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    del manifest["files"]["hpnv20.b2f"]
    manifest_path.write_text(json.dumps(manifest))
    r = run(stage, ["--require", "com.apple.BlueTool"])
    check(r.returncode == 1 and "BlueTool contains" in r.stdout,
          "--require of an absent string fails")


    stage = build_stage(Path(tmp) / "same")
    manifest_path = stage / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    del manifest["files"]["hpnv20.b2f"]
    manifest_path.write_text(json.dumps(manifest))
    identical = hashlib.sha256((stage / "userland" / "bin" / "bluetoothd").read_bytes()).hexdigest()
    report = json.loads((stage / "report.json").read_text())
    report["native_input_sha256"] = identical
    (stage / "report.json").write_text(json.dumps(report))
    r = run(stage, ["--bluetoothd-sha256", identical])
    check(r.returncode == 1 and "bluetoothd re-signed" in r.stdout,
          "a bluetoothd that still matches the native input fails")

if failures:
    print(f"bluetooth-userspace-check test: {len(failures)} failure(s)")
    sys.exit(1)
print("bluetooth-userspace-check test: OK")
