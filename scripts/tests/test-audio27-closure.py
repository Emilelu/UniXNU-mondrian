#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Host tests for scripts/check-audio27-closure.py.

Four properties: the repository's own drivers/PongAudio is green, a header the
source reaches with angle brackets (the applier's quoted-include reading cannot
see it) is named and red, a header that only another header includes is still
copied (that is the case the applier had to learn), and a source the compiler
refuses is reported as refusal rather than as a missing header.
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
SCRIPT = HERE.parent / "check-audio27-closure.py"
HEADERS = ("PongAudioAcf.h", "PongAudioAmpProfile.h", "PongAudioAmpReplay.h",
           "PongAudioGeniI2c.h", "PongAudioPlan.h", "PongAudioRegs.h",
           "PongAudioTlmm.h")


def fixture(extra_header=None, patch=None):
    root = pathlib.Path(tempfile.mkdtemp(prefix="k60-closure-"))
    (root / "drivers/PongAudio").mkdir(parents=True)
    (root / "scripts/tests/portability").mkdir(parents=True)
    for name in ("PongAudioAmp.c", "PongAudioGeniI2c.c"):
        shutil.copy(REPO / "drivers/PongAudio" / name, root / "drivers/PongAudio" / name)
    for name in HEADERS:
        shutil.copy(REPO / "drivers/PongAudio" / name, root / "drivers/PongAudio" / name)
    for name in ("sys/types.h", "sys/systm.h", "kern/clock.h", "pexpert/pexpert.h",
                 "pexpert/arm64/board_config.h", "ml_io_map.h"):
        source = REPO / "scripts/tests/portability" / name
        (root / "scripts/tests/portability" / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(source, root / "scripts/tests/portability" / name)
    shutil.copy(REPO / "scripts/apply-audio27-wiring.py", root / "scripts/apply-audio27-wiring.py")
    if extra_header:
        (root / "drivers/PongAudio" / extra_header).write_text("#define K60_EXTRA 1" + chr(10))
    if patch:
        target, text = patch
        (root / "drivers/PongAudio" / target).write_text(text)
    return root


def run(root):
    done = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(root)],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          universal_newlines=True)
    return done.returncode, done.stdout


def case_repository_is_green():
    code, out = run(REPO)
    assert code == 0, out
    assert "CLOSURE OK: 7 headers" in out, out
    return "the repository's own driver set is green"


def case_angle_include_is_red():
    amp = (REPO / "drivers/PongAudio/PongAudioAmp.c").read_text()
    amp = amp.replace('#include "PongAudioRegs.h"',
                      '#include "PongAudioRegs.h"' + chr(10) + '#include <PongAudioExtra.h>')
    root = fixture(extra_header="PongAudioExtra.h", patch=("PongAudioAmp.c", amp))
    try:
        code, out = run(root)
        assert code == 1, out
        assert "PongAudioExtra.h" in out, out
        assert "CLOSURE FAILED" in out, out
        return "an angle-bracket include the applier cannot see is named"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def case_header_chain_is_copied():
    tlmm = (REPO / "drivers/PongAudio/PongAudioTlmm.h").read_text()
    tlmm = '#include "PongAudioChain.h"' + chr(10) + tlmm
    root = fixture(extra_header="PongAudioChain.h", patch=("PongAudioTlmm.h", tlmm))
    try:
        code, out = run(root)
        assert code == 0, out
        assert "CLOSURE OK: 8 headers" in out, out
        return "a header reached only through another header is copied"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def case_compiler_refusal_is_reported():
    root = fixture(patch=("PongAudioAmp.c",
                          '#include "k60_no_such_header.h"' + chr(10)))
    try:
        code, out = run(root)
        assert code != 0, out
        assert "the compiler refused the glue" in out, out
        return "a source the compiler refuses is reported as refusal"
    finally:
        shutil.rmtree(root, ignore_errors=True)


CASES = [case_repository_is_green, case_angle_include_is_red,
         case_header_chain_is_copied, case_compiler_refusal_is_reported]


def main():
    failures = 0
    for case in CASES:
        try:
            print("  ok   %s" % case())
        except AssertionError as exc:
            failures += 1
            print("  FAIL %s: %s" % (case.__name__, exc))
    if failures:
        print("FAILED: %d case(s)" % failures)
        return 1
    print("TESTS OK %d cases" % len(CASES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
