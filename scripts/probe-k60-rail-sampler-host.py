#!/usr/bin/env python3
"""Offline canonical C tests: reproduction can pass while compliance stays red.

No production source is copied, patched or substituted. No PAS/SCM is linked.
A fresh output directory retains each process output and the canonical hashes.
Mode all returns 1 if any compliance assertion fails; it never normalizes xfail.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "package/tests/rail-sampler"
CANONICAL = REPO / "drivers/PongPower/K60PmicRail.c"
HEADER = REPO / "drivers/PongPower/K60PmicRail.h"

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("all", "reproduced-current-behavior", "compliance"), default="all")
    parser.add_argument("--cc", default=os.environ.get("CC", "cc"))
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()
    if not args.output.is_absolute() or args.timeout <= 0:
        parser.error("--output must be absolute and --timeout must be positive")
    out = args.output.resolve()
    if out.exists() and any(out.iterdir()):
        parser.error("output directory must be new or empty; historical evidence is not overwritten")
    out.mkdir(parents=True, exist_ok=True)
    commands = []
    before = {str(p.relative_to(REPO)): sha(p) for p in (CANONICAL, HEADER)}
    summary = {"mode": args.mode, "classification": "canonical-source-host-only-not-power-evidence",
               "source_sha256_before": before, "cases": [], "limitations": [
                   "No physical MMIO, PAS or SCM; map/parser event counts only, not volatile loads",
                   "No repaired sampler model or production source patch",
                   "Individual compliance controls do not certify the full design",
                   "Current record API cannot expose a command list or all raw status fields"]}
    infrastructure = False
    def execute(argv, name, timeout=None):
        nonlocal infrastructure
        command = [str(x) for x in argv]
        record = {"command": command, "name": name}
        commands.append(record)
        started = time.monotonic()
        try:
            process = subprocess.run(command, cwd=REPO, capture_output=True, text=True,
                                     timeout=timeout or args.timeout)
            record.update(returncode=process.returncode, stdout=process.stdout, stderr=process.stderr)
        except (OSError, subprocess.TimeoutExpired) as error:
            infrastructure = True
            record.update(returncode=None, error=str(error), stdout="", stderr="")
        record["elapsed_seconds"] = round(time.monotonic() - started, 4)
        (out / (name + ".log")).write_text(
            "$ " + shlex.join(command) + "\n" + record.get("stdout", "") +
            record.get("stderr", "") + "\nreturncode=" + str(record["returncode"]) +
            (" error=" + record["error"] if "error" in record else "") + "\n", encoding="utf-8")
        return record
    version = execute([args.cc, "--version"], "compiler-version")
    if version["returncode"] != 0:
        infrastructure = True
    git = execute(["git", "rev-parse", "HEAD"], "source-revision")
    if git["returncode"] != 0:
        infrastructure = True
    summary["source_revision"] = git.get("stdout", "").strip()
    flags = ["-std=c11", "-Wall", "-Wextra", "-Werror", "-I", str(HEADER.parent)]
    builds = {
        "helper": [args.cc, *flags, "-O1", str(FIXTURES / "helper.c"), str(CANONICAL), "-o", str(out / "helper")],
        "entry": [args.cc, *flags, "-O0", "-pthread", "-DKERNEL=1", "-I", str(FIXTURES / "fake"),
                  str(FIXTURES / "entry.c"), str(CANONICAL), "-o", str(out / "entry")],
    }
    for binary, command in builds.items():
        build = execute(command, "compile-" + binary, timeout=120)
        if build["returncode"] != 0:
            infrastructure = True
            continue
        listed = execute([out / binary, "--list"], "list-" + binary)
        names = listed.get("stdout", "").splitlines()
        if listed["returncode"] != 0 or not names or len(names) != len(set(names)):
            infrastructure = True
            continue
        modes = ("reproduced-current-behavior", "compliance") if args.mode == "all" else (args.mode,)
        for mode in modes:
            for name in names:
                if not name or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in name):
                    infrastructure = True
                    continue
                record = execute([out / binary, mode, name], binary + "-" + mode + "-" + name)
                rc = record["returncode"]
                status = "PASS" if rc == 0 else "FAIL" if rc == 1 else "INFRASTRUCTURE_ERROR"
                if status == "INFRASTRUCTURE_ERROR": infrastructure = True
                case = {"binary": binary, "mode": mode, "case": name, "returncode": rc,
                        "status": status, "log": record["name"] + ".log"}
                summary["cases"].append(case)
                print("CASE", binary, mode, name, status, "rc=" + str(rc), flush=True)
    after = {str(p.relative_to(REPO)): sha(p) for p in (CANONICAL, HEADER)}
    summary["source_sha256_after"] = after
    summary["canonical_unchanged"] = before == after
    if before != after: infrastructure = True
    counts = {}
    for mode in ("reproduced-current-behavior", "compliance"):
        selected = [c for c in summary["cases"] if c["mode"] == mode]
        if not selected: continue
        counts[mode] = {"cases": len(selected), "pass": sum(c["status"] == "PASS" for c in selected),
                        "fail": sum(c["status"] == "FAIL" for c in selected),
                        "infrastructure_errors": sum(c["status"] == "INFRASTRUCTURE_ERROR" for c in selected)}
        print("SUMMARY", mode, json.dumps(counts[mode], sort_keys=True), flush=True)
    summary["counts"] = counts
    failed = any(c["status"] != "PASS" for c in summary["cases"])
    rc = 2 if infrastructure else 1 if failed else 0
    summary["returncode"] = rc
    summary["compliance"] = ("INFRASTRUCTURE_ERROR" if infrastructure else
                              "FAIL" if counts.get("compliance", {}).get("fail", 0) else
                              "CASE_CHECKS_ONLY_NOT_CERTIFICATION" if "compliance" in counts else "NOT_RUN")
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (out / "commands.json").write_text(json.dumps(commands, indent=2) + "\n", encoding="utf-8")
    manifest = []
    for path in sorted(out.rglob("*")):
        if path.is_file(): manifest.append(sha(path) + "  " + str(path.relative_to(out)))
    for path in sorted(FIXTURES.rglob("*")):
        if path.is_file(): manifest.append(sha(path) + "  SOURCE:" + str(path.relative_to(REPO)))
    manifest.append(sha(Path(__file__)) + "  SOURCE:" + str(Path(__file__).relative_to(REPO)))
    (out / "sha256.txt").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    print("RESULT canonical_unchanged=" + str(before == after) + " compliance=" + summary["compliance"] +
          " returncode=" + str(rc), flush=True)
    return rc

if __name__ == "__main__":
    sys.exit(main())
