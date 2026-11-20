#!/usr/bin/env python3
"""Host cases for check-audio27-bootargs.py."""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
GATE = os.path.join(REPO, "scripts", "check-audio27-bootargs.py")
DRIVER = "drivers/PongAudio/PongAudioAmp.c"
ALLOW = "scripts/check-image-args.py"
JUDGE = "scripts/judge-audio-capture.py"
TRIAGE = "scripts/triage-audio27.py"
WIRING = "docs/research/audio/IOS27-WIRING.md"
ARGS_DOC = "docs/engineering/BOOT-ARGS.md"
NAME = "pong_audio_probe"

DRIVER_BODY = chr(10).join([
    "int",
    "pong_audio_amp_probe(void)",
    "{",
    "	uint32_t mode = 0;",
    '	if (!PE_parse_boot_argn("' + NAME + '", &mode, sizeof mode) || mode != 1u) {',
    "		return 0;",
    "	}",
    "	return 1;",
    "}",
    "",
])
ALLOW_BODY = chr(10).join([
    "ALLOWED_ADDITIONS = {",
    '    "' + NAME + '", "pong_rail_probe",',
    "}",
    "",
])
JUDGE_BODY = "HINT = 'the boot command line has " + NAME + "=1'" + chr(10)
TRIAGE_BODY = "HINT = 'add " + NAME + "=1 to the boot command line'" + chr(10)
WIRING_BODY = chr(10).join([
    "| 项 | 值 |",
    "|---|---|",
    "| 启动参数 | \x60" + NAME + "\x60（探针唯一的入口开关） |",
    "",
])
DOC_BODY = "### \x60" + NAME + "\x60" + chr(10) + chr(10) + "| 项 | 值 |" + chr(10)


def tree(root, **changes):
    bodies = {
        DRIVER: DRIVER_BODY,
        ALLOW: ALLOW_BODY,
        JUDGE: JUDGE_BODY,
        TRIAGE: TRIAGE_BODY,
        WIRING: WIRING_BODY,
        ARGS_DOC: DOC_BODY,
    }
    bodies.update(changes)
    for name, body in bodies.items():
        if body is None:
            continue
        path = os.path.join(root, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as handle:
            handle.write(body)
    return root


def run(root, gates=None):
    env = dict(os.environ)
    if gates is None:
        env.pop("K60_GATES", None)
    else:
        env["K60_GATES"] = gates
    done = subprocess.run([sys.executable, GATE, root], stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, env=env)
    return done.returncode, done.stdout.decode("utf-8", "replace")


def case_agree(root):
    code, out = run(tree(root))
    assert code == 0, out
    assert "BOOTARGS OK 1 call(s) name " + NAME + "=1" in out, out


def case_allow_list_drops_it(root):
    allow = ALLOW_BODY.replace('    "' + NAME + '", ', "    ")
    code, out = run(tree(root, **{ALLOW: allow}))
    assert code == 1, out
    assert "is absent from ALLOWED_ADDITIONS" in out, out
    assert "drops the flag the driver reads" in out, out


def case_judge_hint_drifts(root):
    code, out = run(tree(root, **{JUDGE: "HINT = 'pong_audio=1'" + chr(10)}))
    assert code == 1, out
    assert "no '" + NAME + "=1' in scripts/judge-audio-capture.py" in out, out


def case_wiring_row_missing(root):
    code, out = run(tree(root, **{WIRING: "| 启动参数 | 见别处 |" + chr(10)}))
    assert code == 1, out
    assert "has no 启动参数 row naming " + NAME in out, out


def case_value_not_compared(root):
    driver = DRIVER_BODY.replace(" || mode != 1u", "")
    code, out = run(tree(root, **{DRIVER: driver}))
    assert code == 1, out
    assert "no mode comparison decides the value" in out, out


def case_doc_absent_is_a_note(root):
    code, out = run(tree(root, **{ARGS_DOC: None}))
    assert code == 0, out
    assert "BOOTARGS NOTE: docs/engineering/BOOT-ARGS.md is not on this machine" in out, out


def case_doc_stale(root):
    code, out = run(tree(root, **{ARGS_DOC: "### \x60someone_else\x60" + chr(10)}))
    assert code == 1, out
    assert "does not name " + NAME in out, out


def case_no_driver_call(root):
    code, out = run(tree(root, **{DRIVER: "int x(void) { return 0; }" + chr(10)}))
    assert code == 1, out
    assert "calls PE_parse_boot_argn nowhere" in out, out


CASES = [
    ("all six places agree", case_agree),
    ("the allow list drops the name", case_allow_list_drops_it),
    ("the judge hint drifts", case_judge_hint_drifts),
    ("the wiring page loses its row", case_wiring_row_missing),
    ("the driver stops comparing the value", case_value_not_compared),
    ("the boot-arg doc is absent", case_doc_absent_is_a_note),
    ("the boot-arg doc is stale", case_doc_stale),
    ("the driver parses no argument", case_no_driver_call),
]


def main():
    failed = 0
    for label, case in CASES:
        work = tempfile.mkdtemp(prefix="bootargs-")
        try:
            case(work)
            print("ok   " + label)
        except AssertionError as error:
            failed += 1
            print("FAIL " + label)
            print(str(error))
        finally:
            shutil.rmtree(work, ignore_errors=True)
    if failed:
        print("TESTS FAILED: %d of %d cases" % (failed, len(CASES)))
        return 1
    print("TESTS OK %d cases" % len(CASES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
