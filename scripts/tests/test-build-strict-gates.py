#!/usr/bin/env python3
"""The strict builder must refuse to build when the eight-step gate is red.

Why this test exists: build-strict.sh used to invoke `unixnu build kernel`
directly. static_check / unit_test / artifact_check are fields of
docs/research/EIGHT-STEPS.toml and only scripts/eight-step-gate.py evaluates
them, so a build could succeed with the evidence missing and nobody noticed.
The builder now runs the gate first; this test pins that order and proves the
failure path really stops before the kernel build.

Run: python3 scripts/tests/test-build-strict-gates.py
"""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "build-strict.sh"
FAILS = []


def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + (("  " + detail) if detail else ""))
    if not ok:
        FAILS.append(name)


def source():
    return SCRIPT.read_text()


def case_gate_runs_before_kernel():
    text = source()
    gate = text.find("eight-step-gate.py")
    kernel = text.find("build kernel")
    check("gate is invoked", gate > 0)
    check("gate runs before the kernel build", 0 < gate < kernel,
          "gate@%d kernel@%d" % (gate, kernel))
    check("a red gate aborts the build", "eight-step gate refused this build" in text)
    check("gate log is kept", "eight-step.log" in text)


def case_red_gate_stops_the_build():
    """Build a throwaway repo whose gate exits 1 and watch the builder stop."""
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="k60-strict-"))
    try:
        repo = tmp / "repo"
        (repo / "scripts").mkdir(parents=True)
        (repo / "dts").mkdir()
        (repo / "patches" / "xnu").mkdir(parents=True)
        shutil.copy(SCRIPT, repo / "scripts" / "build-strict.sh")
        (repo / "board.toml").write_text("# stub\n")
        (repo / "dts" / "mondrian.dts").write_text("// stub\n")
        (repo / "patches" / "xnu" / "series").write_text("")
        # A gate that always fails, but records that it ran.
        (repo / "scripts" / "eight-step-gate.py").write_text(
            "import pathlib,sys\n"
            "pathlib.Path(%r).write_text('ran\\n')\n"
            "print('结论: ❌ synthetic red gate')\n"
            "sys.exit(1)\n" % str(tmp / "gate-ran.txt"))

        build = tmp / "build"
        build.mkdir()
        (build / "unixnu").write_text(
            "#!/bin/sh\necho \"$@\" >> %s\n" % (tmp / "unixnu-called.txt"))
        (build / "unixnu").chmod(0o755)

        fd = tmp / "keep.fd"
        fd.write_bytes(b"_FVH" + b"\0" * 60)

        env = dict(os.environ)
        env.pop("UNIXNU_SKIP_GATES", None)
        env["K60_BUILD_TREE"] = str(build)
        env["K60_DEVICE_INPUT"] = str(tmp / "device")
        env["K60_ARTIFACTS"] = str(tmp / "art")
        env["K60_OUT"] = str(tmp / "out")
        (tmp / "device").mkdir()
        (tmp / "art").mkdir()

        r = subprocess.run(["bash", str(repo / "scripts" / "build-strict.sh"),
                            "redgate", "--fd", str(fd)],
                           capture_output=True, text=True, env=env)
        check("builder exits non-zero on a red gate", r.returncode != 0,
              "rc=%d" % r.returncode)
        check("the gate actually ran", (tmp / "gate-ran.txt").exists())
        check("no kernel build was attempted", not (tmp / "unixnu-called.txt").exists())
        check("the message names the eight-step gate",
              "eight-step gate refused this build" in (r.stderr + r.stdout),
              (r.stderr or r.stdout).strip().splitlines()[-1:] and
              (r.stderr or r.stdout).strip().splitlines()[-1] or "")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def case_skip_gates_still_refused():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="k60-strict-"))
    try:
        fd = tmp / "keep.fd"
        fd.write_bytes(b"_FVH" + b"\0" * 60)
        env = dict(os.environ)
        env["UNIXNU_SKIP_GATES"] = "1"
        r = subprocess.run(["bash", str(SCRIPT), "skip", "--fd", str(fd)],
                           capture_output=True, text=True, env=env)
        check("UNIXNU_SKIP_GATES is refused", r.returncode != 0 and
              "UNIXNU_SKIP_GATES is set" in (r.stderr + r.stdout))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    for case in (case_gate_runs_before_kernel, case_red_gate_stops_the_build,
                 case_skip_gates_still_refused):
        print(case.__name__)
        case()
    print()
    if FAILS:
        print("TESTS FAILED: %d" % len(FAILS))
        return 1
    print("TESTS OK 3 cases (0 failure(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
