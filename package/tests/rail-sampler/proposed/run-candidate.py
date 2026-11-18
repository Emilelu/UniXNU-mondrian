#!/usr/bin/env python3
"""Host runner for the UNINTEGRATED candidate observation core.

This runner lives with the delivery it drives and is deliberately separate from
scripts/probe-k60-rail-sampler-host.py:
it reports only "candidate core contract verification". It never reproduces,
summarises, or greens the canonical sampler suite. The candidate core is a host
fixture under package/tests/rail-sampler/proposed/ and is not linked into any
production object, library, patch or kernel.

Exit codes: 0 = every listed candidate case passed; 1 = at least one case
failed; 2 = infrastructure error (build, listing, timeout, crash, usage).
No expected-failure mechanism exists: a failing case can never be normalised.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(os.environ.get("K60_REPO") or Path(__file__).resolve().parents[4])
FIXTURE = Path(__file__).resolve().parent
CORE = FIXTURE / "rail_obs.c"
HEADER = FIXTURE / "rail_obs.h"
ENTRY = FIXTURE / "entry.c"
CC = os.environ.get("CC", "cc")
LABEL_RE = re.compile(r"[a-z0-9][a-z0-9-]*")
TIMEOUT = float(os.environ.get("K60_CANDIDATE_TIMEOUT", "60"))

# Production files that must stay untouched and unreferenced by the candidate.
PRODUCTION = [
    "drivers/PongPower/K60PmicRail.c",
    "drivers/PongPower/K60PmicRail.h",
    "drivers/PongPower/K60AdspBoard.c",
    "patches/xnu/0613-k60-adsp-pas.patch",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fail_infra(msg: str) -> "NoReturn":
    print(f"CANDIDATE_CORE_RESULT: INFRA {msg}", file=sys.stderr)
    raise SystemExit(2)


def compile_one(out: Path, sources: list[Path], target: str, extra: list[str],
                link: bool = True) -> list[str]:
    cmd = [CC, "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror", *extra,
           "-I", str(FIXTURE)]
    if not link:
        cmd += ["-c"]
    cmd += [str(s) for s in sources]
    cmd += ["-o", str(out / target)]
    log = out / f"{target}.build.log"
    proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    log.write_text("$ " + " ".join(cmd) + "\n" + proc.stdout + proc.stderr,
                   encoding="utf-8")
    if proc.returncode != 0:
        print(proc.stdout + proc.stderr, file=sys.stderr)
        fail_infra(f"compilation failed for {target}; see {log}")
    return cmd


def scan_production_references() -> list[str]:
    hits: list[str] = []
    for path in sorted((REPO / "drivers").rglob("*")):
        if path.is_file() and path.suffix in {".c", ".h", ".cpp"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            if "rail_obs" in text or "k60_rail_observe_once" in text:
                hits.append(str(path.relative_to(REPO)))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", required=True,
                    help="absolute, new-or-empty output directory")
    ap.add_argument("--case", action="append", default=[],
                    help="run only this case label (repeatable); default all")
    ap.add_argument("--list", action="store_true", help="list cases and exit")
    args = ap.parse_args()

    if not (REPO / ".git").exists():
        fail_infra(f"not a repository: {REPO}")
    for path in (CORE, HEADER, ENTRY):
        if not path.is_file():
            fail_infra(f"missing candidate source: {path}")

    out = Path(args.output)
    if not out.is_absolute():
        fail_infra("--output must be absolute")
    if out.exists() and any(out.iterdir()):
        fail_infra(f"output directory is not empty: {out}")
    out.mkdir(parents=True, exist_ok=True)

    references = scan_production_references()
    if references:
        fail_infra("candidate symbols referenced by production sources: "
                   + ", ".join(references))

    hashes = {str(p.relative_to(REPO)): sha256(p) for p in (CORE, HEADER, ENTRY)}
    for rel in PRODUCTION:
        p = REPO / rel
        if not p.is_file():
            fail_infra(f"missing production file: {rel}")
        hashes[rel] = sha256(p)

    commands: list[list[str]] = []
    commands.append(compile_one(out, [CORE], "rail_obs.o", [], link=False))
    commands.append(compile_one(out, [ENTRY, CORE], "candidate-tests",
                                ["-DK60_RAIL_OBS_HOST_TEST", "-pthread"]))

    binary = out / "candidate-tests"
    try:
        listing = subprocess.run([str(binary), "--list"], cwd=str(REPO),
                                 capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        fail_infra(f"cannot list candidate cases: {exc}")
    if listing.returncode != 0:
        fail_infra(f"--list exited {listing.returncode}: {listing.stderr.strip()}")
    cases = [line.strip() for line in listing.stdout.splitlines() if line.strip()]
    if not cases:
        fail_infra("--list returned no cases")
    for line in cases:
        if not LABEL_RE.fullmatch(line):
            fail_infra(f"--list line is not a case label: {line!r}")
    if len(set(cases)) != len(cases):
        fail_infra("--list returned duplicate case labels")
    selected = args.case or cases
    unknown = [c for c in selected if c not in cases]
    if unknown:
        fail_infra("unknown case label(s): " + ", ".join(unknown))
    if args.list:
        for c in cases:
            print(c)
        return 0

    results = []
    started = time.time()
    for case in selected:
        cmd = [str(binary), "candidate", case]
        try:
            proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True,
                                  text=True, timeout=TIMEOUT)
            rc, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as exc:
            fail_infra(f"case {case} timed out after {TIMEOUT}s")
        except OSError as exc:
            fail_infra(f"cannot run case {case}: {exc}")
        (out / f"case-{case}.log").write_text(
            "$ " + " ".join(cmd) + "\n" + stdout + stderr, encoding="utf-8")
        if rc not in (0, 1):
            fail_infra(f"case {case} exited {rc} (infrastructure, not a test verdict)")
        results.append({"case": case, "rc": rc,
                        "verdict": "PASS" if rc == 0 else "FAIL"})
    elapsed = time.time() - started

    failed = [r for r in results if r["rc"] != 0]
    summary = {
        "kind": "candidate-core-contract-verification",
        "note": ("UNINTEGRATED host candidate; separate from the canonical "
                 "sampler reproduction suite and not evidence of compliance"),
        "repo": str(REPO),
        "command": {"compile_core": commands[0], "compile_entry": commands[1]},
        "hashes": hashes,
        "cases": results,
        "total": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "elapsed_seconds": round(elapsed, 3),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n",
                                      encoding="utf-8")
    (out / "sha256.txt").write_text(
        "".join(f"{v}  {k}\n" for k, v in hashes.items()), encoding="utf-8")

    for r in results:
        print(f"{r['verdict']} {r['case']}")
    label = "PASS" if not failed else "FAIL"
    print(f"CANDIDATE_CORE_RESULT: {label} {summary['passed']}/{summary['total']} "
          f"cases (candidate-only, not canonical compliance)")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
