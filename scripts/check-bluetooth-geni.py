#!/usr/bin/env python3
"""Drive the real GENI engine source against a register model.

The board adapter in bsd/dev/qbt_k60.c cannot run on a host: it maps MMIO,
owns the Apps SMMU and talks to the GIC.  The engine below it,
bsd/dev/qbt/qbt_geni.c, only reaches the hardware through struct
qbt_geni_ops, so the porting page's platform check can be done here: this
script extracts the engine sources from the 0500 patch, compiles them with
the fixture register model and runs every scenario.

It proves the sequence, the register writes and the baud arithmetic.  It
does not prove the part: hardware_verified stays false, as on the reference
board.

Usage:
  scripts/check-bluetooth-geni.py
  scripts/check-bluetooth-geni.py --patch patches/xnu/0500-k60-bt-qbt-new-files.patch
  scripts/check-bluetooth-geni.py --tree <xnu work tree> --out out/geni-report
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATCH = ROOT / "patches" / "xnu" / "0500-k60-bt-qbt-new-files.patch"
FIXTURE = ROOT / "scripts" / "tests" / "fixtures" / "bt-geni-model.c"
SOURCES = ("qbt_geni.c", "qbt_geni.h", "qbt_geni_regs.h")
SCENARIOS = ("prepare", "rate", "start", "write", "receive", "fault",
             "quiesce", "flow")
CFLAGS = ["-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
          "-fsanitize=address,undefined"]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def extract_from_patch(patch, out):
    """Pull the engine sources out of a unified diff that adds them."""
    wanted = set(SOURCES)
    current, buffer = None, []
    written = {}

    def flush():
        if current in wanted:
            target = out / current
            target.write_text("\n".join(buffer) + "\n", encoding="utf-8")
            written[current] = target

    for line in Path(patch).read_text(encoding="utf-8").splitlines():
        if line.startswith("+++ b/bsd/dev/qbt/"):
            flush()
            current = line.rsplit("/", 1)[-1]
            buffer = []
        elif line.startswith("diff --git"):
            flush()
            current, buffer = None, []
        elif current is not None and line.startswith("+") and not line.startswith("+++"):
            buffer.append(line[1:])
    flush()
    return written


def collect_from_tree(tree, out):
    written = {}
    for name in SOURCES:
        source = Path(tree) / "bsd" / "dev" / "qbt" / name
        if not source.is_file():
            raise SystemExit("missing source: %s" % source)
        shutil.copyfile(source, out / name)
        written[name] = out / name
    return written


def pick_compiler():
    for name in ("clang", "gcc"):
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit("no C compiler on PATH")


def compile_model(compiler, work, binary):
    command = [compiler, *CFLAGS, "-I" + str(work), str(FIXTURE),
               str(work / "qbt_geni.c"), "-o", str(binary)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise SystemExit("compile failed:\n%s%s" % (result.stdout, result.stderr))
    return command


def run_model(binary, scenario):
    result = subprocess.run([str(binary), scenario], capture_output=True, text=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--patch", default=str(DEFAULT_PATCH))
    source.add_argument("--tree")
    parser.add_argument("--out")
    parser.add_argument("--scenario", default="all", choices=("all",) + SCENARIOS)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args(argv)

    work = Path(tempfile.mkdtemp(prefix="k60-geni-"))
    try:
        if args.tree:
            sources = collect_from_tree(args.tree, work)
            origin = {"tree": str(args.tree)}
        else:
            if not Path(args.patch).is_file():
                raise SystemExit("missing patch: %s" % args.patch)
            sources = extract_from_patch(args.patch, work)
            origin = {"patch": str(args.patch), "patch_sha256": sha256(args.patch)}
        missing = [name for name in SOURCES if name not in sources]
        if missing:
            raise SystemExit("the source set is incomplete: " + ", ".join(missing))

        compiler = pick_compiler()
        binary = work / "geni-model"
        command = compile_model(compiler, work, binary)

        scenarios = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
        runs = {}
        failures = 0
        for name in scenarios:
            result = run_model(binary, name)
            runs[name] = result
            if result.returncode:
                failures += 1
                print("FAIL %s: %s" % (name, (result.stdout + result.stderr).strip()[-400:]))
        if args.scenario == "all":
            whole = run_model(binary, "all")
            runs["all"] = whole
            if whole.returncode:
                failures += 1
                print("FAIL all: " + (whole.stdout + whole.stderr).strip()[-400:])

        output = runs.get("all", next(iter(runs.values()))).stdout
        for line in output.splitlines():
            if line.startswith(("PASS", "FAIL", "registers_simulated", "model:")):
                print(line)
        if not args.scenario == "all":
            print(output.strip().splitlines()[-1] if output.strip() else "")

        registers = 0
        assertions = 0
        for line in output.splitlines():
            if line.startswith("registers_simulated="):
                registers = int(line.split("=", 1)[1])
            if line.startswith("model: OK ("):
                assertions = int(line.split("(")[1].split()[0])

        passed = failures == 0 and assertions > 0 and registers > 0
        report = {
            "passed": passed,
            "registers_simulated": registers,
            "assertions": assertions,
            "hardware_verified": False,
            "origin": origin,
            "inputs": {name: sha256(sources[name]) for name in SOURCES},
            "fixture_sha256": sha256(FIXTURE),
            "compiler": compiler,
            "compile_command": command,
            "scenarios": {name: {"returncode": run.returncode,
                                 "output": run.stdout + run.stderr}
                          for name, run in runs.items()},
        }
        if args.out:
            out = Path(args.out)
            out.mkdir(parents=True, exist_ok=True)
            (out / "report.json").write_text(json.dumps(report, indent=2) + "\n",
                                             encoding="utf-8")
            (out / "output.txt").write_text(output, encoding="utf-8")
        if not passed:
            print("bluetooth-geni-check: FAILED")
            return 1
        print("bluetooth-geni-check: OK (%d assertion(s), %d register(s))"
              % (assertions, registers))
        return 0
    finally:
        if args.keep:
            print("work tree kept at " + str(work))
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
