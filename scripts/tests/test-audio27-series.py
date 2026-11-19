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
    (drifted / NAME).write_bytes(good.replace(b"pong_audio_probe=1", b"pong_audio_probe=0", 1))
    (drifted / "series").write_text(NAME + "\n")
    code, out = run(sys.executable, str(CHECK), str(root), "--series", str(drifted))
    assert code == 1, out
    assert "differs from the emitter" in out and "SERIES FAILED" in out, out
    cases += 1
    print("  ok   a drifted series copy is named")

    unlisted = work / "unlisted"
    unlisted.mkdir()
    (unlisted / NAME).write_bytes(good)
    (unlisted / "series").write_text("0530-k60-spi-availability.patch\n")
    code, out = run(sys.executable, str(CHECK), str(root), "--series", str(unlisted))
    assert code == 1, out
    assert "does not list it" in out, out
    cases += 1
    print("  ok   a patch nobody lists is a failure")

    print("TESTS OK %d cases" % cases)


if __name__ == "__main__":
    main()
