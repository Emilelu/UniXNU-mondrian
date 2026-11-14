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
        (repo / "scripts" / "check-build-env.py").write_text("import sys\nsys.exit(0)\n")
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


def case_env_reaches_the_gate():
    """The registry runs as a child; it must see the tree being built.

    2026-11-14: build-strict.sh read K60_DEVICE_INPUT/K60_OUT but never
    exported them. unixnu then ran check-rules.py against the default mirror,
    computed a different series fingerprint, and refused the build with
    iron-4/hard-33 for a difference that did not exist.
    """
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="k60-strict-"))
    try:
        repo = tmp / "repo"
        (repo / "scripts").mkdir(parents=True)
        (repo / "dts").mkdir()
        (repo / "patches" / "xnu").mkdir(parents=True)
        shutil.copy(SCRIPT, repo / "scripts" / "build-strict.sh")
        (repo / "scripts" / "check-build-env.py").write_text("import sys\nsys.exit(0)\n")
        (repo / "board.toml").write_text("# stub\n")
        (repo / "dts" / "mondrian.dts").write_text("// stub\n")
        (repo / "patches" / "xnu" / "series").write_text("")
        (repo / "scripts" / "eight-step-gate.py").write_text(
            "import os,pathlib,sys\n"
            "pathlib.Path(%r).write_text("
            "os.environ.get('K60_DEVICE_INPUT','') + '|' + "
            "os.environ.get('K60_OUT','') + '|' + "
            "os.environ.get('K60_REPO',''))\n"
            "sys.exit(1)\n" % str(tmp / "env.txt"))

        build = tmp / "build"
        build.mkdir()
        (build / "unixnu").write_text("#!/bin/sh\nexit 0\n")
        (build / "unixnu").chmod(0o755)
        fd = tmp / "keep.fd"
        fd.write_bytes(b"_FVH" + b"\0" * 60)

        device = tmp / "mydevice"
        out = tmp / "myout"
        device.mkdir()
        out.mkdir()
        (tmp / "art").mkdir()

        env = dict(os.environ)
        env.pop("UNIXNU_SKIP_GATES", None)
        env["K60_BUILD_TREE"] = str(build)
        env["K60_DEVICE_INPUT"] = str(device)
        env["K60_OUT"] = str(out)
        env["K60_ARTIFACTS"] = str(tmp / "art")

        subprocess.run(["bash", str(repo / "scripts" / "build-strict.sh"),
                        "envcase", "--fd", str(fd)],
                       capture_output=True, text=True, env=env)
        seen = (tmp / "env.txt").read_text().split("|")
        check("K60_DEVICE_INPUT reaches the gate", seen[0] == str(device),
              "%r" % seen[0])
        check("K60_OUT reaches the gate", len(seen) > 1 and seen[1] == str(out),
              "%r" % (seen[1] if len(seen) > 1 else ""))
        check("K60_REPO reaches the gate", len(seen) > 2 and seen[2] == str(repo),
              "%r" % (seen[2] if len(seen) > 2 else ""))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def case_kernel_arg_reaches_the_payload():
    """--kernel-arg must be handed to `build payload`, which writes the TOML.

    2026-11-14: rail-20261114n and rail-20261114p were built from the same tree
    with and without --kernel-arg pong_rail_probe=1, and both images carried 29
    arguments / 575 bytes.  build-strict.sh forwarded KARGS only to bootimg; the
    argument line the firmware passes comes from the payload TOML, which
    `unixnu build payload` writes.
    """
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="k60-strict-"))
    try:
        repo = tmp / "repo"
        (repo / "scripts").mkdir(parents=True)
        (repo / "dts").mkdir()
        (repo / "patches" / "xnu").mkdir(parents=True)
        shutil.copy(SCRIPT, repo / "scripts" / "build-strict.sh")
        (repo / "scripts" / "check-build-env.py").write_text("import sys\nsys.exit(0)\n")
        (repo / "board.toml").write_text("# stub\n")
        (repo / "dts" / "mondrian.dts").write_text("// stub\n")
        (repo / "patches" / "xnu" / "series").write_text("")
        (repo / "scripts" / "eight-step-gate.py").write_text("import sys\nsys.exit(0)\n")

        build = tmp / "build"
        build.mkdir()
        # Records every invocation, creates the kernel for `build kernel`, and
        # fails at `build payload` so the test can read what it was given.
        (build / "unixnu").write_text(
            "#!/bin/sh\n"
            "echo \"$@\" >> %s\n"
            "case \"$1 $2\" in\n"
            "  'build kernel')\n"
            "    mkdir -p \"$K60_OUT/mondrian/ipados-16.6.1-20G81/mondrian/kernel\"\n"
            "    echo kernel > \"$K60_OUT/mondrian/ipados-16.6.1-20G81/mondrian/kernel/kernel.macho\"\n"
            "    exit 0 ;;\n"
            "  'build payload') exit 1 ;;\n"
            "esac\n"
            "exit 0\n" % (tmp / "calls.txt"))
        (build / "unixnu").chmod(0o755)

        fd = tmp / "keep.fd"
        fd.write_bytes(b"_FVH" + b"\0" * 60)
        (tmp / "device").mkdir()
        (tmp / "art").mkdir()
        out = tmp / "out"
        (out / "mondrian" / "ipados-16.6.1-20G81" / "mondrian").mkdir(parents=True)

        env = dict(os.environ)
        env.pop("UNIXNU_SKIP_GATES", None)
        env["K60_BUILD_TREE"] = str(build)
        env["K60_DEVICE_INPUT"] = str(tmp / "device")
        env["K60_ARTIFACTS"] = str(tmp / "art")
        env["K60_OUT"] = str(out)

        subprocess.run(["bash", str(repo / "scripts" / "build-strict.sh"),
                        "argcase", "--fd", str(fd),
                        "--kernel-arg", "pong_rail_probe=1"],
                       capture_output=True, text=True, env=env)

        calls = (tmp / "calls.txt").read_text().splitlines()
        payload = [c for c in calls if c.startswith("build payload")]
        check("the payload step was reached", bool(payload),
              "%d call(s)" % len(calls))
        check("--kernel-arg reaches the payload step",
              bool(payload) and "--kernel-arg pong_rail_probe=1" in payload[0],
              payload[0] if payload else "")
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
                 case_env_reaches_the_gate, case_kernel_arg_reaches_the_payload,
                 case_skip_gates_still_refused):
        print(case.__name__)
        case()
    print()
    if FAILS:
        print("TESTS FAILED: %d" % len(FAILS))
        return 1
    print("TESTS OK 5 cases (0 failure(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
