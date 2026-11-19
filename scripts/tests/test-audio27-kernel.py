#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Host cases for check-audio27-kernel.py: a real object in both macro states."""
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
DRIVER = REPO / "drivers/PongAudio"
CHECK = REPO / "scripts/check-audio27-kernel.py"
cases = 0


def run(*command, cwd=None):
    done = subprocess.run(list(command), cwd=cwd, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True)
    return done.returncode, done.stdout


def build(work, macro):
    """The glue as an object, with the one arm64 barrier removed for the host."""
    source = work / "glue.c"
    text = (DRIVER / "PongAudioAmp.c").read_text()
    text = text.replace('__asm__ volatile("dsb sy" ::: "memory");', "")
    source.write_text(text)
    obj = work / ("glue-%s.o" % macro)
    flags = ["-DXNU_PONG_AUDIO"] if macro == "on" else []
    code, out = run("cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                    "-I", str(REPO / "scripts/tests/portability"),
                    "-I", str(DRIVER), *flags, "-c", "-o", str(obj), str(source))
    assert code == 0, out
    return obj


def main():
    global cases
    work = pathlib.Path(tempfile.mkdtemp(prefix="audio27-"))
    try:
        on = build(work, "on")
        code, out = run(sys.executable, str(CHECK), str(on))
        assert code == 0, out
        assert "AUDIO27 OK" in out, out
        assert "strings 3/3" in out, out
        assert "symbols 3/3" in out, out
        print("  ok   an object with the macro on passes")

        off = build(work, "off")
        code, out = run(sys.executable, str(CHECK), str(off))
        assert code == 1, out
        assert "strings absent: boot argument" in out, out
        assert "AUDIO27 OK" not in out, out
        print("  ok   the same source without the macro fails")

        plain = work / "plain.txt"
        plain.write_text("nothing to see here\n")
        code, out = run(sys.executable, str(CHECK), str(plain))
        assert code == 1 and "AUDIO27 FAILED" in out, out
        print("  ok   a file with no audio in it fails")

        code, out = run(sys.executable, str(CHECK), str(work / "absent.o"))
        assert code == 1 and "no such file" in out, out
        print("  ok   a missing file is refused")

        code, out = run(sys.executable, str(CHECK))
        assert code == 2 and "usage" in out, out
        print("  ok   no argument prints usage")
        cases = 5
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("TESTS OK %d cases" % cases)
    return 0


if __name__ == "__main__":
    sys.exit(main())
