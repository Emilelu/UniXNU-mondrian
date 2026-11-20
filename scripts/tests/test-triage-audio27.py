#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Host cases for triage-audio27.py: the three verdicts, and the three reasons a
capture can hold no PongAudio lines (no image given, image without the wiring,
image with the wiring but no boot argument)."""
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
TRIAGE = REPO / "scripts/triage-audio27.py"
cases = 0

START = "PongAudio: amp probe start (read pass first, then a replay pass, x2 amplifiers)"
BUS = "PongAudio: amp gcc gpll0 locked"
ID0 = "PongAudio: amp0 addr=0x34 id=0x2113 chip=AW88261"
ID1 = "PongAudio: amp1 addr=0x35 id=0x2113 chip=AW88261"
DONE = "PongAudio: amp probe done found=2/2 failed=0 timeouts=0 recovered=0"
STOP = "PongAudio: amp probe stop: GPLL0 not locked"


def run(*command):
    done = subprocess.run(list(command), stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True)
    return done.returncode, done.stdout


def capture(work, name, lines):
    root = work / name
    root.mkdir(parents=True, exist_ok=True)
    (root / "console.log").write_text(chr(10).join(lines) + chr(10))
    return root


def image(work, name, text):
    path = work / name
    path.write_text(text + chr(10))
    return path


def expect(code, out, want_code, needle):
    assert code == want_code, (code, out)
    assert needle in out, out


def main():
    global cases
    work = pathlib.Path(tempfile.mkdtemp(prefix="triage27-"))
    good = capture(work, "good", [START, BUS, ID0, ID1, DONE])
    code, out = run(sys.executable, str(TRIAGE), str(good))
    expect(code, out, 0, "run the replay pass")
    cases += 1
    print("  ok   a successful probe points at the replay pass")

    stopped = capture(work, "stopped", [START, STOP])
    code, out = run(sys.executable, str(TRIAGE), str(stopped))
    expect(code, out, 1, "the last PongAudio line before the stop")
    cases += 1
    print("  ok   a probe that stopped points at its last line")

    empty = capture(work, "empty", ["AppleARMPE: boot"])
    code, out = run(sys.executable, str(TRIAGE), str(empty))
    expect(code, out, 2, "pass --kernel")
    cases += 1
    print("  ok   no image given means it will not guess")

    wired = image(work, "wired.txt", "pong_audio_probe amp probe start amp probe done found=")
    code, out = run(sys.executable, str(TRIAGE), str(empty), "--kernel", str(wired))
    expect(code, out, 2, "the capture ended before bsd_init")
    cases += 1
    print("  ok   a wired image with a quiet capture means the boot stopped early")

    stale = image(work, "stale.txt", "nothing here")
    code, out = run(sys.executable, str(TRIAGE), str(empty), "--kernel", str(stale))
    expect(code, out, 2, "predates the audio wiring")
    cases += 1
    print("  ok   an image without the strings is named as predating the wiring")

    noboot = image(work, "noboot.txt", "amp probe start amp probe done found=")
    code, out = run(sys.executable, str(TRIAGE), str(empty), "--kernel", str(noboot))
    expect(code, out, 2, "add pong_audio_probe=1")
    cases += 1
    print("  ok   an image missing only the boot argument says so")

    print("TESTS OK %d cases" % cases)


if __name__ == "__main__":
    main()
