#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Host cases for check-audio27-series.py: an unbooked series, a copy that
matches the emitter, a copy that drifted, and a copy nobody lists."""
import importlib.util
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
CHECK = REPO / "scripts/check-audio27-series.py"
EMITTER = REPO / "scripts/emit-audio27-patch.py"
WIRING = REPO / "scripts/apply-audio27-wiring.py"
NAME = "0531-k60-audio-amp-probe-call.patch"
cases = 0


def load(path):
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(*command):
    done = subprocess.run(list(command), stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True)
    return done.returncode, done.stdout


def tree(work):
    """A 27-shaped tree: bsd_init.c with the anchor line the emitter wants."""
    wiring = load(WIRING)
    root = work / "xnu"
    (root / "bsd/kern").mkdir(parents=True, exist_ok=True)
    text = ("\nint\nbsd_init(void)\n{\n\n" + wiring.INIT_ANCHOR
            + "\tvfsinit();\n\treturn 0;\n}\n")
    (root / wiring.INIT_FILE).write_text(text)
    return root


def emitted(root, work):
    out = work / "emitted.patch"
    code, text = run(sys.executable, str(EMITTER), str(root), "--out", str(out))
    assert code == 0, text
    return out.read_bytes()


def main():
    global cases
    work = pathlib.Path(tempfile.mkdtemp(prefix="audio27-series-"))
    root = tree(work)
    good = emitted(root, work)

    code, out = run(sys.executable, str(CHECK), str(root),
                    "--series", str(work / "absent"))
    assert code == 3, out
    assert "is not on this machine" in out, out
    cases += 1
    print("  ok   a series directory that is not here is not a failure")

    empty = work / "empty"
    empty.mkdir()
    code, out = run(sys.executable, str(CHECK), str(root), "--series", str(empty))
    assert code == 3, out
    assert "no 0531 audio patch" in out, out
    cases += 1
    print("  ok   a series that has not booked the patch says so")

    booked = work / "booked"
    booked.mkdir()
    (booked / NAME).write_bytes(good)
    (booked / "series").write_text("# 27 series\n0530-k60-spi-availability.patch\n"
                                   + NAME + "\n")
    code, out = run(sys.executable, str(CHECK), str(root), "--series", str(booked))
    assert code == 0, out
    assert "SERIES OK " + NAME in out and "matches the emitter" in out, out
    cases += 1
    print("  ok   the booked copy matches the emitter")

    drifted = work / "drifted"
    drifted.mkdir()
    (drifted / NAME).write_bytes(good.replace(b"__attribute__((weak))", b"__attribute__((weak, unused))", 1))
    (drifted / "series").write_text(NAME + "\n")
    code, out = run(sys.executable, str(CHECK), str(root), "--series", str(drifted))
    assert code == 1, out
    assert "inserts different code" in out and "SERIES FAILED" in out, out
    cases += 1
    print("  ok   a drifted series copy is named by the code it inserts")

    commented = work / "commented"
    commented.mkdir()
    (commented / NAME).write_bytes(good.replace(b"K60 audio amplifier probe", b"K60 audio amp probe", 1))
    (commented / "series").write_text(NAME + chr(10))
    code, out = run(sys.executable, str(CHECK), str(root), "--series", str(commented))
    assert code == 0, out
    assert "SERIES NOTE" in out and "inserts the emitter" in out, out
    cases += 1
    print("  ok   a comment-only difference is a note, not a failure")

    unlisted = work / "unlisted"
    unlisted.mkdir()
    (unlisted / NAME).write_bytes(good)
    (unlisted / "series").write_text("0530-k60-spi-availability.patch\n")
    code, out = run(sys.executable, str(CHECK), str(root), "--series", str(unlisted))
    assert code == 1, out
    assert "does not list it" in out and "no comment says why" in out, out
    cases += 1
    print("  ok   a patch nobody lists, unremarked, is a failure")

    held = work / "held"
    held.mkdir()
    (held / NAME).write_bytes(good)
    (held / "series").write_text(
        "# " + NAME + " is deliberately NOT listed: the kernel link cannot" + chr(10) +
        "# resolve its call site yet." + chr(10) +
        "0530-k60-spi-availability.patch" + chr(10))
    code, out = run(sys.executable, str(CHECK), str(root), "--series", str(held))
    assert code == 0, out
    assert "SERIES HOLD: " + NAME in out, out
    assert "the series file says why" in out, out
    assert "held, not listed" in out, out
    cases += 1
    print("  ok   a hold the series explains is a state, not a failure")


    far = work / "far"
    far.mkdir()
    (far / "0500-far.patch").write_text(
        "--- a/bsd/kern/bsd_init.c" + chr(10) +
        "+++ b/bsd/kern/bsd_init.c" + chr(10) +
        "@@ -1,2 +1,3 @@" + chr(10) +
        " int" + chr(10) +
        "+int far_away;" + chr(10) +
        " bsd_init(void)" + chr(10))
    (far / NAME).write_bytes(good)
    (far / "series").write_text("0500-far.patch" + chr(10) + NAME + chr(10))
    code, out = run(sys.executable, str(CHECK), str(root), "--series", str(far))
    assert code == 0, out
    assert "SERIES ORDER OK: 1 earlier patch(es)" in out, out
    cases += 1
    print("  ok   an earlier patch on another line is not a conflict")

    near = work / "near"
    near.mkdir()
    (near / "0500-near.patch").write_text(
        "--- a/bsd/kern/bsd_init.c" + chr(10) +
        "+++ b/bsd/kern/bsd_init.c" + chr(10) +
        "@@ -5,3 +5,4 @@" + chr(10) +
        " " + chr(10) +
        "+\tint near_the_call = 0;" + chr(10) +
        " \tbsd_init_kprintf(\"calling vfsinit\\n\");" + chr(10) +
        " \tvfsinit();" + chr(10))
    (near / NAME).write_bytes(good)
    (near / "series").write_text("0500-near.patch" + chr(10) + NAME + chr(10))
    code, out = run(sys.executable, str(CHECK), str(root), "--series", str(near))
    assert code == 1, out
    assert "SERIES FAILED: 0500-near.patch edits bsd/kern/bsd_init.c" in out, out
    cases += 1
    print("  ok   an earlier patch on the call site is a failure")
    print("TESTS OK %d cases" % cases)


if __name__ == "__main__":
    main()
