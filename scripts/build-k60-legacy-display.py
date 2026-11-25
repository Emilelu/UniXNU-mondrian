#!/usr/bin/env python3
"""Build the K60 legacy display archive (GopFramebuffer) for the 27 kernel line.

Why this exists
---------------
The 27 kernel has no IOFRAMEBUFFER source in tree: the display family is only
present as a prelinked kext.  GopFramebuffer bridges to it through the vtable
fixture in legacy-display-24A446.json.  sheng's builder does that, but it also
links keystore, keyboard, USB and Bluetooth probes, and it names
``kits/sheng/LegacyDisplayProbe.cpp`` which is not in any public repository.
So the device has to produce its own archive.

Modes
-----
--check (default)   Validate the inputs and print the exact plan.  Reads only;
                    never invokes a compiler.  This is the mode allowed while
                    the build freeze is on.
--plan              Same as --check but prints the command lines verbatim.
--run               Execute the plan.  Refuses unless K60_ALLOW_BUILD=1, so a
                    freeze cannot be broken by accident.

Exit codes: 0 ok, 2 inputs incomplete, 3 refused by the freeze guard,
1 execution failure.
"""
from __future__ import annotations

import argparse
import re
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REQUIRED_FIXTURE_KEYS = (
    "kernelcache_sha256", "collection_slide", "vtable", "instance_size",
    "slots", "methods", "leaves", "bindings", "checks", "display",
    "request", "names",
)
REQUIRED_SOURCES = (
    "NativeLegacyDisplay.cpp",
    "NativeGOPPresenter.cpp",
)
REQUIRED_HEADERS = (
    "NativeLegacyRequest.h",
    "NativeGOPWire.h",
    "NativeHalfCodes.h",
    "NativeGpuTrace.h",
    "OriginalMobileFramebufferABI.h",
)
DEFAULT_OUTPUT = "build/native-legacy-display/libNativeLegacyDisplay.late.a"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()



def declared_symbols(sources: list[Path]) -> set[str]:
    """Names the component refers to but does not define (first-pass, regex)."""
    text = "".join(p.read_text(encoding="utf-8", errors="replace") for p in sources)
    headers = "".join(h.read_text(encoding="utf-8", errors="replace")
                      for h in sorted(sources[0].parent.glob("*.h")))
    text = text + headers
    names = set(re.findall(r"native_legacy_[a-z0-9_]+", text))
    defined = set()
    for n in names:
        if any(re.search(r"\b" + re.escape(n) + r"\s*\([^;]{0,400}\)\s*(?:const\s*)?\{", line)
               and not re.search(r"\b(?:if|while|for|switch)\s*\(", line)
               for line in text.splitlines()):
            defined.add(n)
        elif re.search(r"\b" + re.escape(n) + r"\s*(?:\[[^\]]*\])*\s*=(?!=)", text):
            defined.add(n)
    return names - defined


def probe_defined(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    hits = re.findall(r"\b(native_legacy_[a-z0-9_]+)\s*\([^;{]{0,400}\)\s*(?:const\s*)?\{", text)
    return set(hits)


def check_inputs(component: Path, fixture: Path) -> list[str]:
    problems: list[str] = []
    if not component.is_dir():
        problems.append(f"component directory missing: {component}")
        return problems
    for name in REQUIRED_SOURCES + REQUIRED_HEADERS:
        if not (component / name).is_file():
            problems.append(f"component file missing: {component / name}")
    if not fixture.is_file():
        problems.append(f"vtable fixture missing: {fixture}")
        return problems
    try:
        doc = json.loads(fixture.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        problems.append(f"vtable fixture is not JSON: {fixture}: {exc}")
        return problems
    missing = [k for k in REQUIRED_FIXTURE_KEYS if k not in doc]
    if missing:
        problems.append(f"vtable fixture lacks {len(missing)} key(s): {', '.join(missing)}")
    slots = doc.get("slots")
    if isinstance(slots, list) and len(slots) < 100:
        problems.append(f"vtable fixture has only {len(slots)} slots, expected a full table")
    return problems


def plan(component: Path, fixture: Path, xnu: Path, output: Path, cc: str) -> dict:
    doc = json.loads(fixture.read_text(encoding="utf-8"))
    sources = [component / name for name in REQUIRED_SOURCES]
    includes = [
        "-I", str(component),
        "-I", str(xnu / "EXTERNAL_HEADERS"),
        "-I", str(xnu / "osfmk"),
        "-I", str(xnu / "bsd"),
        "-I", str(xnu / "iokit"),
    ]
    flags = ["-target", "arm64-apple-ios27.0", "-std=c++17", "-O2", "-fno-exceptions",
             "-fno-rtti", "-DKDEFS_ONLY=0", "-arch", "arm64e"]
    fakeroot = xnu.parent / "fakeroot"
    if (fakeroot / "usr" / "include").is_dir():
        flags += ["-isysroot", str(fakeroot), "-I", str(fakeroot / "usr" / "include")]
    commands = []
    objects = []
    for src in sources:
        obj = output.parent / (src.stem + ".o")
        objects.append(obj)
        commands.append([cc, *flags, *includes, "-c", str(src), "-o", str(obj)])
    commands.append(["llvm-ar", "rcs", str(output), *[str(o) for o in objects]])
    return {
        "fixture": str(fixture),
        "slots": len(doc.get("slots") or []),
        "methods": len(doc.get("methods") or {}),
        "bindings": len(doc.get("bindings") or {}),
        "sources": [str(s) for s in sources],
        "includes": includes,
        "commands": commands,
        "output": str(output),
    }


def main(argv: list[str]) -> int:
    repo = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--component", default="/mnt/e/iOS Port/Work/references/GopFramebuffer",
                    help="GopFramebuffer component checkout")
    ap.add_argument("--fixture", default=str(repo / "scripts/legacy-display-24A446.json"),
                    help="vtable fixture copied from the reference device")
    ap.add_argument("--xnu", default=os.environ.get("XNU_TREE", ""),
                    help="assembled XNU tree (needs EXTERNAL_HEADERS)")
    ap.add_argument("--output", default=str(repo / DEFAULT_OUTPUT))
    ap.add_argument("--cc", default=os.environ.get("K60_CC", "clang"))
    ap.add_argument("--probe", default="", help="LegacyDisplayProbe.cpp to reconcile against")
    ap.add_argument("--plan", action="store_true", help="print the command lines")
    ap.add_argument("--run", action="store_true", help="execute (requires K60_ALLOW_BUILD=1)")
    args = ap.parse_args(argv)

    component = Path(args.component)
    fixture = Path(args.fixture)
    problems = check_inputs(component, fixture)
    if problems:
        for p in problems:
            print(f"GOP DISPLAY: {p}", file=sys.stderr)
        print(f"GOP DISPLAY: {len(problems)} input problem(s); nothing to do")
        return 2

    xnu = Path(args.xnu) if args.xnu else Path("/nonexistent")
    info = plan(component, fixture, xnu, Path(args.output), args.cc)
    print(f"gop-display: component {component}")
    print(f"gop-display: fixture {fixture} ({info['slots']} slots, {info['methods']} methods, {info['bindings']} bindings)")
    print(f"gop-display: sources {len(info['sources'])}; output {info['output']}")
    if args.xnu and not (xnu / "EXTERNAL_HEADERS").is_dir():
        print(f"GOP DISPLAY: --xnu does not look like an XNU tree: {xnu}", file=sys.stderr)
        return 2
    if args.probe:
        probe = Path(args.probe)
        if not probe.is_file():
            print(f"GOP DISPLAY: probe file missing: {probe}", file=sys.stderr)
            return 2
        want = declared_symbols(info_paths := [component / n for n in REQUIRED_SOURCES])
        have = probe_defined(probe)
        missing = sorted(want - have)
        print(f"gop-display: probe {probe}: defines {len(have & want)}/{len(want)} referenced hook(s)")
        if missing:
            print(f"GOP DISPLAY: probe lacks {len(missing)} hook(s): {', '.join(missing)}", file=sys.stderr)
            return 2
    if args.plan or not args.run:
        for cmd in info["commands"]:
            print("gop-display: " + " ".join(cmd))
        print("gop-display: check only (pass --run to build)")
        return 0

    if os.environ.get("K60_ALLOW_BUILD") != "1":
        print("GOP DISPLAY: refused: K60_ALLOW_BUILD is not 1 (build freeze)", file=sys.stderr)
        return 3
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    for cmd in info["commands"]:
        print("gop-display: run " + " ".join(cmd))
        rc = subprocess.run(cmd).returncode
        if rc != 0:
            print(f"GOP DISPLAY: command failed with {rc}", file=sys.stderr)
            return 1
    archive = Path(args.output)
    report = {
        "component": str(component),
        "fixture": str(fixture),
        "fixture_sha256": sha256(fixture),
        "sources": {str(s): sha256(s) for s in [component / n for n in REQUIRED_SOURCES]},
        "archive": str(archive),
        "archive_sha256": sha256(archive),
    }
    report_path = archive.parent / "build-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"gop-display: built {archive} ({archive.stat().st_size} bytes) sha256 {report['archive_sha256'][:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
