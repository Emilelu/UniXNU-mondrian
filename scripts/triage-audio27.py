#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Turn one 27 capture into a next step.

The probe verdict already says whether the hardware answered. What it cannot
say is why it did not: a capture with no PongAudio lines looks the same whether
the image was built without the wiring or the boot stopped before bsd_init.
This script runs the product check on the same image and prints one sentence to
do next.

  python3 scripts/triage-audio27.py E:/k60-work/evidence/usblog-<ts>/ \
      --kernel out/.../kernel/kernel.macho

It reads; it never boots, writes or changes anything. Exit codes follow the
verdict it reports: 0 answered, 1 ran and stopped, 2 nothing to judge.
"""
import argparse
import importlib.util
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def product(kernel):
    """(ok, last line) from the product gate; (None, reason) when no image was given."""
    if not kernel:
        return None, "no kernel given"
    done = subprocess.run([sys.executable, str(HERE / "check-audio27-kernel.py"), str(kernel)],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    lines = [l for l in done.stdout.splitlines() if l.strip()]
    return done.returncode == 0, (lines[-1] if lines else "no output")


def next_step(code, ok, image):
    """One sentence, picked from the verdict and the image, never both guessed."""
    if code == 0:
        return ("the probe answered; run the replay pass on the same capture"
                " (--replay) to judge the ACF halves")
    if code == 1:
        return ("the probe ran and stopped; the last PongAudio line before the"
                " stop names the part that did not answer")
    if ok is None:
        return ("pass --kernel so this can tell an image without the wiring from"
                " a capture that ended before bsd_init")
    if not ok:
        if image.endswith("strings absent: boot argument"):
            return ("this image carries the audio but not the boot argument; add"
                    " pong_audio_probe=1 to the boot command line")
        if "strings absent:" in image:
            return ("this image predates the audio wiring; apply the series entry"
                    " and the per-object define, then build again")
        return ("the strings are there but the probe symbols are not: point"
                " --kernel at the unstripped kernel.macho instead")
    return ("the image carries the code, so the capture ended before bsd_init;"
            " compare its last line with the F4 expectation")


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", help="capture directory, not a file")
    parser.add_argument("--kernel", default=None, help="kernel.macho or boot.img of the same run")
    args = parser.parse_args(argv[1:])

    judge = load("judge", HERE / "judge-audio-capture.py")
    capture = pathlib.Path(args.evidence)
    lines, meta = judge.read_capture(str(capture)) if capture.is_dir() else ([], {})
    code, report = judge.judge(lines, meta)
    log = judge.find_log(str(capture)) if capture.is_dir() else None
    starts = sum(1 for l in lines if judge.MARK_START in l)
    print("audio27 triage: %s" % capture)
    print("  console     : %s" % (log if log else "no log in this directory"))
    print("  probe lines : start=%d" % starts)
    print("  verdict     : %d %s" % (code, [l for l in report if l.startswith("VERDICT")][-1]))
    ok, image = product(args.kernel)
    print("  image       : %s" % image)
    print("NEXT: %s." % next_step(code, ok, image))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
