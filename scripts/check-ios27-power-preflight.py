#!/usr/bin/env python3
"""Preflight the iOS 27 copy of the power line.

The carry manifest (docs/research/power/CARRY.toml) only proves that the seven
pure C modules still hash the same. Three other failures have already cost
rounds of work on the 27 line, and each of them is visible offline:

  * the sleep-trace patch guards its report calls with `#if defined(PONG)`, but
    the 27 profile is not PONG, so both reports vanish and the platform-sleep
    judge can never pass (P-255 family: a guard that looks harmless);
  * the 16.6.1 builder pins MACHINE_CONFIGS=PONG, and the 12377 source has no
    pexpert/pexpert/arm64/PONG.h, so `make installhdrs` stops with
    `Unsupported CURRENT_MACHINE_CONFIG PONG`; board.toml must route to the
    generic builder (3cc8cbc9) for the 27 profile;
  * a judge that was written on the 16 line but never merged into the 27 tree
    cannot be run there, so the flight has no verdict.

This script reads both trees and says which of those still hold. It never
writes, never boots, never touches the network.

usage:
  python3 scripts/check-ios27-power-preflight.py
  python3 scripts/check-ios27-power-preflight.py --tree E:/hackios/xnekom-ios27
exit: 0 clean, 1 blockers, 2 unusable input
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

MANIFEST = Path("docs/research/power/CARRY.toml")
SERIES = Path("patches/xnu") / "series"
PICKER = Path("scripts") / "pick-xnu-builder.sh"
GENERIC = "build-xnu-generic.sh"
JUDGES = ("judge-k60-mode1-console.py", "judge-k60-handoff-console.py",
          "judge-k60-sleep-console.py")
REPORT_CALLS = ("k60_platform_sleep_report", "armcpu_sleep_report")

PASS, WARN, BLOCK = "PASS", "WARN", "BLOCKER"


def device_root() -> Path:
    env = os.environ.get("K60_REPO")
    return Path(env).resolve() if env else Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Unusable(Exception):
    """The inputs cannot be judged at all: a missing manifest or wrong tree."""


def manifest_modules(device: Path) -> dict[str, list[tuple[str, str]]]:
    path = device / MANIFEST
    if not path.is_file():
        raise Unusable(f"no carry manifest at {path}")
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    out: dict[str, list[tuple[str, str]]] = {}
    for module in data.get("module", []):
        name = module.get("name")
        files = module.get("files", [])
        if not name or not files:
            raise SystemExit("ios27-preflight: a carry module has no name or files")
        out[name] = [(entry["path"], entry["sha256"]) for entry in files]
    if not out:
        raise Unusable("the carry manifest lists no modules")
    return out


def check_tree(tree: Path) -> str:
    """The tree argument must be a device checkout; anything else is unusable."""
    if not tree.is_dir():
        raise Unusable(f"{tree} is not a directory")
    missing = [rel for rel in ("board.toml", "drivers/PongPower", str(SERIES))
               if not (tree / rel).exists()]
    if missing:
        raise Unusable("not a device checkout: missing " + ", ".join(missing))
    return str(tree)


def check_carry(tree: Path, modules: dict[str, list[tuple[str, str]]]) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for name, files in sorted(modules.items()):
        drift, miss = [], []
        for rel, want in files:
            path = tree / rel
            if not path.is_file():
                miss.append(rel)
            elif sha256_file(path) != want:
                drift.append(rel)
        if miss:
            rows.append((BLOCK, name, "missing " + ", ".join(miss)))
        elif drift:
            rows.append((BLOCK, name, "drifted " + ", ".join(drift)))
        else:
            rows.append((PASS, name, f"{len(files)} file(s) identical"))
    return rows


def check_report_guard(tree: Path) -> tuple[str, str]:
    series = tree / SERIES
    if not series.is_file():
        return WARN, "no patches/xnu/series in the 27 tree"
    offenders = []
    for line in series.read_text(encoding="utf-8", errors="replace").splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        patch = (series.parent / entry).resolve()
        if not path_inside(patch, tree) or not patch.is_file():
            continue
        text = patch.read_text(encoding="utf-8", errors="replace")
        if not any(call in text for call in REPORT_CALLS):
            continue
        guarded = [n for n, row in enumerate(text.splitlines(), 1)
                   if "#if defined(PONG)" in row or "#ifdef PONG" in row]
        if guarded:
            offenders.append(f"{entry}:{guarded[0]}")
    if offenders:
        return BLOCK, ("the report calls are behind #if defined(PONG) ("
                       + ", ".join(offenders)
                       + "); the 27 profile is not PONG, so both reports vanish "
                         "and the sleep judge can never pass — move the guard to a "
                         "driver-level macro such as K60_PLATFORM_SLEEP_REPORT")
    return PASS, "the sleep reports are not behind a PONG guard"


def path_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def check_builder(tree: Path) -> tuple[str, str]:
    picker = tree / PICKER
    if not picker.is_file():
        if (tree / "scripts" / "build-xnu-4k-baseline.sh").is_file():
            return BLOCK, ("no scripts/pick-xnu-builder.sh: the only builder pins "
                           "MACHINE_CONFIGS=PONG, which the 12377 source cannot "
                           "satisfy (3cc8cbc9 added the dispatch)")
        return WARN, "no builder scripts in the 27 tree"
    try:
        done = subprocess.run(["sh", str(picker), "board.toml"], cwd=tree,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError) as error:
        return WARN, f"could not run the builder picker: {error}"
    chosen = (done.stdout or "").strip().splitlines()
    if done.returncode != 0 or not chosen:
        return WARN, f"the builder picker exited {done.returncode}"
    picked = Path(chosen[-1].strip()).name
    if picked.endswith(GENERIC):
        return PASS, f"board.toml routes to {picked}"
    return BLOCK, (f"board.toml routes to {picked}, which pins MACHINE_CONFIGS=PONG; "
                   "the 12377 source has no pexpert/pexpert/arm64/PONG.h and "
                   "installhdrs stops with Unsupported CURRENT_MACHINE_CONFIG PONG")


def check_judges(tree: Path, device: Path) -> tuple[str, str]:
    missing = [name for name in JUDGES if not (tree / "scripts" / name).is_file()]
    if not missing:
        return PASS, f"{len(JUDGES)} judge(s) present"
    absent_here = [name for name in missing if not (device / "scripts" / name).is_file()]
    if absent_here:
        return WARN, "missing in the 27 tree " + ", ".join(missing)
    return BLOCK, ("missing in the 27 tree " + ", ".join(missing)
                   + "; merge them or the 27 flight has no verdict")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tree", default=os.environ.get("K60_IOS27_TREE"),
                        help="the iOS 27 checkout; also read from K60_IOS27_TREE "
                             "(no default: the path belongs to the caller, not the repo)")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    device = device_root()
    if not args.tree:
        print("❌ input                  no --tree and no K60_IOS27_TREE")
        print("ios27-power-preflight: INVALID (name the iOS 27 checkout)")
        return 2
    tree = Path(args.tree)
    try:
        modules = manifest_modules(device)
        detail = check_tree(tree)
    except Unusable as error:
        print(f"❌ input                  {error}")
        print(f"ios27-power-preflight: INVALID ({error})")
        return 2
    rows: list[tuple[str, str, str]] = [(PASS, "tree", detail)]
    rows.extend(check_carry(tree, modules))
    for name, check in (("sleep-report-guard", check_report_guard),
                        ("builder-route", check_builder)):
        state_, detail_ = check(tree)
        rows.append((state_, name, detail_))
    state_, detail_ = check_judges(tree, device)
    rows.append((state_, "judges", detail_))

    blockers = [row for row in rows if row[0] == BLOCK]
    warnings = [row for row in rows if row[0] == WARN]
    if not args.quiet:
        for state_, name, detail in rows:
            mark = {PASS: "✅", WARN: "⚠️ ", BLOCK: "❌"}[state_]
            print(f"{mark} {name:<22} {detail}")
    verdict = "PASS" if not blockers else "FAIL"
    print(f"ios27-power-preflight: {verdict} ({len(rows)} item(s), "
          f"{len(blockers)} blocker(s), {len(warnings)} warning(s))")
    return 0 if not blockers else 1


if __name__ == "__main__":
    sys.exit(main())
