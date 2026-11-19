#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Host tests for scripts/add-audio-conffiles.py.

The script exists because a silent anchor miss is indistinguishable from a
successful run without reading conf/files. These cases hold it to the four
outcomes that matter: it lists both entries, it is idempotent, it takes an
anchor the caller names, and it fails loudly - with the count printed - when
the anchor or a source is absent.
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE.parent / "add-audio-conffiles.py"
ANCHOR = "bsd/dev/pong_buttons.c\t\t\tstandard"
SOURCES = ["bsd/dev/PongAudioGeniI2c.c", "bsd/dev/PongAudioAmp.c"]


def make_tree(conf_body, sources=SOURCES):
    root = pathlib.Path(tempfile.mkdtemp(prefix="k60-conf-"))
    work = root / ".cache/xnu-work"
    (work / "bsd/conf").mkdir(parents=True)
    if conf_body is not None:
        (work / "bsd/conf/files").write_text(conf_body)
    for name in sources:
        path = work / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("/* the driver */\n")
    return root


def run(tree, check=False, anchor=None):
    argv = [sys.executable, str(SCRIPT)]
    if check:
        argv.append("--check")
    if anchor is not None:
        argv.extend(["--anchor", anchor])
    argv.append(str(tree))
    proc = subprocess.run(argv, capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def conf_text(tree):
    return (pathlib.Path(tree) / ".cache/xnu-work/bsd/conf/files").read_text()


def case_append():
    tree = make_tree("bsd/dev/pong_buttons.c\t\t\tstandard\n")
    rc, out = run(tree)
    assert rc == 0, out
    text = conf_text(tree)
    for name in SOURCES:
        assert name in text, out
    assert text.count(ANCHOR) == 1, "the anchor line must survive once"
    assert "pong_audio lines 0 -> 2" in out, out
    shutil.rmtree(tree)
    return "append: 0 -> 2 lines, anchor kept"


def case_idempotent():
    tree = make_tree("bsd/dev/pong_buttons.c\t\t\tstandard\n")
    run(tree)
    rc, out = run(tree)
    assert rc == 0, out
    assert "pong_audio lines 2 -> 2" in out, out
    shutil.rmtree(tree)
    return "idempotent: second run writes nothing"


def case_anchor_missing():
    body = "bsd/dev/some_other_driver.c\t\t\tstandard\n"
    tree = make_tree(body)
    rc, out = run(tree)
    assert rc == 1, out
    assert "anchor" in out and "0 -> 0" in out, out
    assert "--anchor" in out, "the message must say how to fix it: " + out
    assert conf_text(tree) == body, "nothing may be written without the anchor"
    shutil.rmtree(tree)
    return "anchor missing: exit 1, count printed, --anchor suggested, no write"


def case_custom_anchor():
    body = "bsd/dev/pong_audio_probe.c\t\t\tstandard\n"
    tree = make_tree(body)
    rc, out = run(tree)  # the default anchor is absent from this tree
    assert rc == 1, out
    anchor = body.strip()
    rc, out = run(tree, anchor=anchor)
    assert rc == 0, out
    text = conf_text(tree)
    for name in SOURCES:
        assert name in text, out
    assert text.startswith(body), "the entries go after the line the caller named: " + text
    assert "pong_audio lines 0 -> 2" in out, out
    shutil.rmtree(tree)
    return "custom anchor: a tree without the button driver still lists both"


def case_source_missing():
    tree = make_tree("bsd/dev/pong_buttons.c\t\t\tstandard\n",
                     sources=["bsd/dev/PongAudioGeniI2c.c"])
    rc, out = run(tree)
    assert rc == 1, out
    assert "PongAudioAmp.c" in out, out
    assert "PongAudioAmp.c" not in conf_text(tree), conf_text(tree)
    shutil.rmtree(tree)
    return "source missing: exit 1, no partial listing"


def case_check_mode():
    tree = make_tree("bsd/dev/pong_buttons.c\t\t\tstandard\n")
    rc, out = run(tree, check=True)
    assert rc == 1, "check mode must fail while the entries are unlisted: " + out
    assert SOURCES[0] not in conf_text(tree), "check mode must not write"
    run(tree)
    rc, out = run(tree, check=True)
    assert rc == 0, out
    shutil.rmtree(tree)
    return "check mode: 1 before, 0 after"


def case_unseeded_tree():
    root = pathlib.Path(tempfile.mkdtemp(prefix="k60-conf-"))
    rc, out = run(root)
    assert rc == 1, out
    assert "not seeded" in out, out
    shutil.rmtree(root)
    return "unseeded tree: exit 1"


CASES = [case_append, case_idempotent, case_anchor_missing, case_custom_anchor,
         case_source_missing, case_check_mode, case_unseeded_tree]


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
