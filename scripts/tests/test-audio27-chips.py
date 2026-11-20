#!/usr/bin/env python3
"""Host cases for check-audio27-chips.py."""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
GATE = os.path.join(REPO, "scripts", "check-audio27-chips.py")
JUDGE = "scripts/judge-audio-capture.py"
PLAN = "drivers/PongAudio/PongAudioPlan.h"
JUDGE_BODY = chr(10).join([
    "AMPS = (0, 1)",
    "KNOWN = {",
    '    0x2113: "AW88261", 0x2013: "AW88264",',
    "}",
    "",
])
PLAN_BODY = chr(10).join([
    "static inline const char *",
    "pong_audio_amp_name(uint16_t chip_id)",
    "{",
    "	switch (chip_id) {",
    '	case 0x2113: return "AW88261";',
    '	case 0x2013: return "AW88264";',
    '	default: return "unknown";',
    "	}",
    "}",
    "",
])


def tree(root, judge=JUDGE_BODY, plan=PLAN_BODY):
    for name, body in ((JUDGE, judge), (PLAN, plan)):
        if body is None:
            continue
        path = os.path.join(root, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as handle:
            handle.write(body)
    return root


def run(root):
    done = subprocess.run([sys.executable, GATE, root],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return done.returncode, done.stdout.decode("utf-8", "replace")


def case_agree(root):
    code, out = run(tree(root))
    assert code == 0, out
    assert "CHIPS OK 2 ids agree" in out, out


def case_driver_extra(root):
    plan = PLAN_BODY.replace('	case 0x2013: return "AW88264";',
                             '	case 0x2013: return "AW88264";' + chr(10) +
                             '	case 0x2308: return "AW88230";')
    code, out = run(tree(root, plan=plan))
    assert code == 1, out
    assert "0x2308 is absent in scripts/judge-audio-capture.py" in out, out


def case_renamed(root):
    plan = PLAN_BODY.replace('"AW88261"', '"AW88261A"')
    code, out = run(tree(root, plan=plan))
    assert code == 1, out
    assert "AW88261" in out and "AW88261A" in out, out


def case_no_judge(root):
    code, out = run(tree(root, judge=None))
    assert code == 1, out
    assert "is not on this branch" in out, out


def case_no_table(root):
    code, out = run(tree(root, judge="AMPS = (0, 1)" + chr(10)))
    assert code == 1, out
    assert "has no KNOWN = { table" in out, out


CASES = [case_agree, case_driver_extra, case_renamed, case_no_judge, case_no_table]


def main():
    failed = 0
    for case in CASES:
        root = tempfile.mkdtemp(prefix="chips-")
        try:
            case(root)
        except AssertionError as error:
            failed += 1
            print("FAIL " + case.__name__ + ": " + str(error))
        finally:
            shutil.rmtree(root, ignore_errors=True)
    if failed:
        print("TESTS FAILED: %d of %d" % (failed, len(CASES)))
        return 1
    print("TESTS OK %d cases" % len(CASES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
