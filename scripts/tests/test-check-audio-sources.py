#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Host test for scripts/check-audio-sources.py.

The gate exists because a 27-line drift in drivers/PongAudioAmp.c left every
other gate green for a day: the stub compile type-checked the stale copy, so
the speaker switch drive cc added was in the patch and not in the file the
iOS 27 tree would have copied. These cases pin that the comparison actually
fails on drift, on a missing file, and that the known external files stay out
of the report.
"""
import importlib.util
import os
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(HERE), "check-audio-sources.py")

spec = importlib.util.spec_from_file_location("check_audio_sources", TOOL)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

fails = 0


def expect(cond, what):
    global fails
    if not cond:
        print("FAIL " + what)
        fails += 1


def write(directory, name, text):
    path = os.path.join(directory, name)
    with open(path, "w") as handle:
        handle.write(text)
    return path


def fixture():
    src = tempfile.mkdtemp(prefix="audio-src-")
    dst = tempfile.mkdtemp(prefix="audio-dst-")
    return src, dst


def case_identical():
    src, dst = fixture()
    write(src, "PongAudioAmp.c", "a\nb\nc\n")
    write(dst, "PongAudioAmp.c", "a\nb\nc\n")
    checked, problems = mod.compare({"PongAudioAmp.c": os.path.join(src, "PongAudioAmp.c")}, dst)
    expect(not problems, "an identical file must not be reported")
    expect(checked == [("PongAudioAmp.c", 3)], "an identical file is counted with its line count")


def case_drift():
    src, dst = fixture()
    write(src, "PongAudioAmp.c", "a\nb\nc\n")
    write(dst, "PongAudioAmp.c", "a\nb\n")
    checked, problems = mod.compare({"PongAudioAmp.c": os.path.join(src, "PongAudioAmp.c")}, dst)
    expect(not checked, "a drifted file must not be counted as checked")
    expect(len(problems) == 1, "a drifted file produces one problem")
    expect("3 lines" in problems[0] and "2" in problems[0],
           "the problem names both line counts: " + (problems[0] if problems else "none"))


def case_missing():
    src, dst = fixture()
    write(src, "PongAudioPlan.h", "x\n")
    checked, problems = mod.compare({"PongAudioPlan.h": os.path.join(src, "PongAudioPlan.h")}, dst)
    expect(len(problems) == 1, "a missing copy produces one problem")
    expect("does not carry" in problems[0], "the problem says the copy is missing")


def case_skip():
    src, dst = fixture()
    write(src, "aw882xx.c", "codec\n")
    write(dst, "aw882xx.c", "stale\n")
    checked, problems = mod.compare({"aw882xx.c": os.path.join(src, "aw882xx.c")}, dst)
    expect(not problems and not checked, "the codec lane's file stays out of the report")
    expect("aw882xx.c" in mod.SKIP, "the skip list names the codec driver")
    expect("pong_audio.c" in mod.SKIP, "the skip list names the frozen graph")
    expect("K60PmicGlinkAudio.h" in mod.SKIP, "the skip list names the power header")


def case_chain_shape():
    names = [name for _sub, name in mod.CHAIN]
    expect(names[0].startswith("0503"), "the chain starts at 0503")
    expect(names[-1].startswith("0003"), "the chain ends at 0003")
    expect(len(names) == 5, "the chain has five patches")


case_identical()
case_drift()
case_missing()
case_skip()
case_chain_shape()

if fails:
    print("FAILED %d case(s)" % fails)
    raise SystemExit(1)
print("TESTS OK")
