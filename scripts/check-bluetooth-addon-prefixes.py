#!/usr/bin/env python3
"""Cross-check the addon prefixes the kernel mounts against the ones we produce.

The Bluetooth runtime reaches the device as an addon: every directory the
userspace stager reports is packed under its prefix, and the kernel unpacks the
addon below /private/var/ngpu. 0526 mounts bluetooth-lib and bluetooth-bin;
0527 mounts xpc. If a prefix is renamed on one side only, the mount silently
finds nothing and the overlay is empty -- a failure that a green build cannot
show, because both halves compile.

The check is textual on purpose: it reads the patch files and the two builders
rather than a built image, so it runs in the same second as the edit.

Usage:
    python3 scripts/check-bluetooth-addon-prefixes.py
    python3 scripts/check-bluetooth-addon-prefixes.py --out report
"""
import argparse
import json
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PATCHES = ROOT / "patches" / "xnu-12377"
STAGER = ROOT / "scripts" / "build-bluetooth-userspace.py"
FRAMEWORK = pathlib.Path("/mnt/e/iOS Port/Sources/Repos/UniXNU/UniXNU/scripts/build-boot-runtime.py")

SOURCE = re.compile(r'_source\[\]\s*=\s*"(/private/var/ngpu/[^"]+)"')
PREFIX = re.compile(r"report\[['\"]directories['\"]\]\s*=\s*\{(.*?)\}", re.S)
KEY = re.compile(r"['\"]([^'\"]+)['\"]\s*:")
ADDON_DIR = re.compile(r"script\(['\"]addon-add-dir\.py['\"],\s*addon,\s*candidate,\s*['\"]([^'\"]+)['\"]")


def kernel_sources(directory=None):
    sources = {}
    for patch in sorted((directory or PATCHES).glob("05*.patch")):
        text = patch.read_text()
        for name in SOURCE.findall(text):
            sources.setdefault(name.rsplit("/", 1)[-1], []).append(patch.name)
    return sources


def stager_prefixes(path=None):
    path = path or STAGER
    if not path.is_file():
        return None
    match = PREFIX.search(path.read_text())
    return set(KEY.findall(match.group(1))) if match else set()


def framework_prefixes(path):
    if path is None or not path.is_file():
        return None
    return set(ADDON_DIR.findall(path.read_text()))


def default_framework():
    for candidate in (os.environ.get("UNIXNU_TREE"), "/mnt/e/iOS Port/Sources/Repos/UniXNU/UniXNU"):
        if candidate:
            path = pathlib.Path(candidate) / "scripts" / "build-boot-runtime.py"
            if path.is_file():
                return path
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patches", default=str(PATCHES))
    parser.add_argument("--stager")
    parser.add_argument("--framework", help="the framework checkout, if it is available")
    parser.add_argument("--out")
    args = parser.parse_args()

    sources = kernel_sources(pathlib.Path(args.patches) if args.patches else None)
    produced = stager_prefixes(pathlib.Path(args.stager) if args.stager else None)
    framework = framework_prefixes(pathlib.Path(args.framework) if args.framework else default_framework())
    failures = []

    print(f"kernel mounts: {', '.join(sorted(sources)) or 'none'}")
    if produced is None:
        failures.append(f"the stager is missing: {args.stager or STAGER}")
        produced = set()
    print(f"stager prefixes: {', '.join(sorted(produced)) or 'none'}")
    print(f"framework prefixes: {', '.join(sorted(framework)) if framework else 'not checked'}")

    for prefix, patches in sorted(sources.items()):
        if prefix in produced:
            print(f"PASS {prefix} comes from the stager ({', '.join(patches)})")
        elif framework is None:
            print(f"SKIP {prefix} comes from the framework, which is not checked out")
        elif prefix in framework:
            print(f"PASS {prefix} comes from the framework ({', '.join(patches)})")
        else:
            failures.append(
                f"{prefix} is mounted by {', '.join(patches)} but no builder packs it"
            )

    for prefix in sorted(produced - set(sources)):
        print(f"note {prefix} is staged but not mounted by the kernel")

    report = {
        "kernel_mounts": sources,
        "stager_prefixes": sorted(produced),
        "framework_prefixes": sorted(framework) if framework else None,
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
        print("bluetooth-addon-prefixes: FAILED")
        return 1
    print("bluetooth-addon-prefixes: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
