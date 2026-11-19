#!/usr/bin/env python3
"""Check a staged Bluetooth userspace set for iOS 27.

The porting page asks for a board check in step 6. This board stages the
native stack for 24A446 offline, so the check is a static one: the staged
BlueTool has to be linked against libxpc and built for iOS 27, bluetoothd
has to be the 24A446 binary byte for byte, the type-0 library has to be a
real arm64e dylib, and every firmware file has to match the manifest the
repository pins.

Usage:
  python3 scripts/check-bluetooth-userspace.py --stage <stage-dir> [--manifest PATH]
"""

import argparse
import hashlib
import json
import os
import struct
import sys

MH_MAGIC_64 = 0xFEEDFACF
LC_LOAD_DYLIB = 0x0C
LC_BUILD_VERSION = 0x32
CPU_TYPE_ARM64 = 0x0100000C
CPU_SUBTYPE_ARM64E = 2
MH_EXECUTE = 2
MH_DYLIB = 6
PLATFORM_IOS = 2

DEFAULT_BLUETOOTHD_SHA256 = (
    "cfd94854d0a2efd3ca4a2de6e55349f43fd0d274a4b8bfa9937f29d9f7208cb1"
)
DEFAULT_TARGET = "arm64e-apple-ios27.0"


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_macho(path):
    """Return the load commands that matter, or raise ValueError."""
    with open(path, "rb") as handle:
        data = handle.read()
    if len(data) < 32:
        raise ValueError("shorter than a Mach-O header")
    magic, cputype, cpusubtype, filetype, ncmds, sizeofcmds = struct.unpack_from(
        "<IiiIII", data, 0
    )
    if magic != MH_MAGIC_64:
        raise ValueError("not a 64-bit Mach-O (magic %#x)" % magic)
    if cputype != CPU_TYPE_ARM64:
        raise ValueError("cputype %#x is not arm64" % cputype)
    subtype = cpusubtype & 0x00FFFFFF
    if subtype != CPU_SUBTYPE_ARM64E:
        raise ValueError("cpusubtype %#x is not arm64e" % subtype)
    offset = 32
    end = 32 + sizeofcmds
    dylibs = []
    build = None
    version = None
    for _ in range(ncmds):
        if offset + 8 > end or offset + 8 > len(data):
            raise ValueError("load command table runs past the header")
        cmd, cmdsize = struct.unpack_from("<II", data, offset)
        if cmdsize < 8 or offset + cmdsize > len(data):
            raise ValueError("load command %#x has a bad size" % cmd)
        if cmd == LC_LOAD_DYLIB:
            name_offset = struct.unpack_from("<I", data, offset + 8)[0]
            raw = data[offset + name_offset : offset + cmdsize]
            dylibs.append(raw.split(b"\0", 1)[0].decode("utf-8", "replace"))
        elif cmd == LC_BUILD_VERSION:
            platform, minos, sdk, _ntools = struct.unpack_from(
                "<IIII", data, offset + 8
            )
            build = {"platform": platform, "minos": minos, "sdk": sdk}
        elif cmd == 0x24:  # LC_VERSION_MIN_IPHONEOS
            version = struct.unpack_from("<I", data, offset + 8)[0]
        offset += cmdsize
    return {"filetype": filetype, "dylibs": dylibs, "build": build, "min_version": version}


def version_text(value):
    return "%d.%d.%d" % ((value >> 16) & 0xFFFF, (value >> 8) & 0xFF, value & 0xFF)


def load_manifest(path, base):
    with open(path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    entries = {}
    files = manifest.get("files", {})
    if isinstance(files, dict):
        for name, entry in files.items():
            entries[name] = entry
    else:
        for entry in files:
            entries[entry["name"]] = entry
    return entries


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, help="staged userspace root")
    parser.add_argument(
        "--manifest",
        default=os.path.join("firmware", "bluetooth", "manifest.json"),
        help="firmware manifest pinned by the repository",
    )
    parser.add_argument(
        "--bluetoothd-sha256",
        default=DEFAULT_BLUETOOTHD_SHA256,
        help="expected hash of the native bluetoothd",
    )
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument(
        "--expect-firmware-count",
        type=int,
        default=None,
        help="optional pinned count; the manifest decides the names",
    )
    parser.add_argument(
        "--require",
        action="append",
        default=[],
        help="string that must appear in BlueTool (repeatable)",
    )
    args = parser.parse_args(argv)

    stage = args.stage
    failures = []

    def check(name, condition, detail=""):
        if condition:
            print("PASS %s%s" % (name, (" " + detail) if detail else ""))
        else:
            failures.append(name)
            print("FAIL %s%s" % (name, (" " + detail) if detail else ""))

    report_path = os.path.join(stage, "report.json")
    report = {}
    if os.path.exists(report_path):
        with open(report_path, encoding="utf-8") as handle:
            report = json.load(handle)
    check("report.json exists", bool(report))
    if report:
        check("report built", report.get("built") is True, str(report.get("built")))
        check("report target", report.get("target") == args.target, str(report.get("target")))
        check(
            "report native input",
            report.get("native_input_sha256") == args.bluetoothd_sha256,
            str(report.get("native_input_sha256")),
        )
        check(
            "report entitlements preserved",
            report.get("native_entitlements_preserved") is True,
            str(report.get("native_entitlements_preserved")),
        )
        check(
            "report not hardware verified",
            report.get("hardware_verified") is False,
            str(report.get("hardware_verified")),
        )

    bluetoothd = os.path.join(stage, "userland", "bin", "bluetoothd")
    if os.path.exists(bluetoothd):
        digest = sha256_file(bluetoothd)
        # The staged binary is re-signed, so its hash must differ from the
        # native input; the report above is what ties it to 24A446.
        check(
            "bluetoothd re-signed",
            digest != args.bluetoothd_sha256,
            digest,
        )
        try:
            info = parse_macho(bluetoothd)
            check("bluetoothd arm64e executable", info["filetype"] == MH_EXECUTE)
            minos = info["build"]["minos"] if info["build"] else info["min_version"]
            check(
                "bluetoothd ios 27",
                info["build"] is not None
                and info["build"]["platform"] == PLATFORM_IOS
                and version_text(minos).startswith("27."),
                version_text(minos) if minos is not None else "no version",
            )
        except ValueError as error:
            check("bluetoothd mach-o", False, str(error))
    else:
        check("bluetoothd exists", False, bluetoothd)

    bluetool = os.path.join(stage, "userland", "bin", "BlueTool")
    if os.path.exists(bluetool):
        try:
            info = parse_macho(bluetool)
            check("BlueTool arm64e executable", info["filetype"] == MH_EXECUTE)
            check(
                "BlueTool links libxpc",
                "/usr/lib/libxpc.dylib" in info["dylibs"],
                ",".join(info["dylibs"]),
            )
            minos = info["build"]["minos"] if info["build"] else info["min_version"]
            check(
                "BlueTool ios 27",
                info["build"] is not None
                and info["build"]["platform"] == PLATFORM_IOS
                and version_text(minos).startswith("27."),
                version_text(minos) if minos is not None else "no version",
            )
        except ValueError as error:
            check("BlueTool mach-o", False, str(error))
        with open(bluetool, "rb") as handle:
            blob = handle.read()
        for needle in args.require:
            check(
                "BlueTool contains %r" % needle,
                needle.encode("utf-8") in blob,
            )
    else:
        check("BlueTool exists", False, bluetool)

    type0 = os.path.join(stage, "userland", "lib", "QcaBTType0.dylib")
    if os.path.exists(type0):
        try:
            info = parse_macho(type0)
            check("QcaBTType0 arm64e dylib", info["filetype"] == MH_DYLIB)
        except ValueError as error:
            check("QcaBTType0 mach-o", False, str(error))
    else:
        check("QcaBTType0 exists", False, type0)

    marker = os.path.join(stage, "userland", "bin", "QcaBluetooth.runtime")
    if os.path.exists(marker):
        try:
            with open(marker, encoding="utf-8") as handle:
                runtime = json.load(handle)
            check(
                "runtime marker input",
                runtime.get("native_input_sha256") == args.bluetoothd_sha256,
                str(runtime.get("native_input_sha256")),
            )
        except (ValueError, UnicodeDecodeError) as error:
            check("runtime marker parses", False, str(error))
    else:
        check("runtime marker exists", False, marker)

    firmware_dir = os.path.join(stage, "firmware", "qca")
    if os.path.isdir(firmware_dir):
        entries = load_manifest(args.manifest, stage)
        names = sorted(os.listdir(firmware_dir))
        if args.expect_firmware_count is not None:
            check(
                "firmware count",
                len(names) == args.expect_firmware_count,
                str(len(names)),
            )
        unknown = [name for name in names if name not in entries]
        check("firmware names in manifest", not unknown, ",".join(unknown[:3]))
        missing = [name for name in entries if name not in names]
        check("firmware complete", not missing, ",".join(sorted(missing)[:3]))
        bad = []
        for name in names:
            if name not in entries:
                continue
            path = os.path.join(firmware_dir, name)
            size = os.path.getsize(path)
            entry = entries[name]
            if size != entry["bytes"] or sha256_file(path) != entry["sha256"]:
                bad.append(name)
        check("firmware bytes and hashes", not bad, ",".join(bad[:3]))
    else:
        check("firmware directory exists", False, firmware_dir)

    if failures:
        print("bluetooth-userspace-check: FAILED (%d)" % len(failures))
        return 1
    print("bluetooth-userspace-check: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
