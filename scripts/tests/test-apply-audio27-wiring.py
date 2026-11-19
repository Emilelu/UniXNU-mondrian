#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Host tests for apply-audio27-wiring.py.

Each case builds a throwaway repository - seeded under .cache/xnu-work, or with
the sources in place the way an iOS 27 output tree keeps them - runs the
applier against it, and reads the two verdicts the script prints: how many
sources are in bsd/dev and whether conf/files names them. Nothing touches a
real tree.
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[2]
APPLIER = REPO / "scripts/apply-audio27-wiring.py"
ANCHOR_27 = "bsd/dev/vfs_syscalls.c\t\t\tstandard"
ANCHOR_16 = "bsd/dev/pong_buttons.c\t\t\tstandard"
KERNEL_SET = 9


def make_tree(root, inplace=False):
    work = root if inplace else root / ".cache/xnu-work"
    (work / "bsd/dev").mkdir(parents=True, exist_ok=True)
    (work / "bsd/conf").mkdir(parents=True, exist_ok=True)
    conf = work / "bsd/conf/files"
    conf.write_text(ANCHOR_27 + "\n")
    return conf


def run(*args):
    done = subprocess.run([sys.executable, str(APPLIER)] + [str(a) for a in args],
                          cwd=str(REPO), stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, universal_newlines=True)
    return done.returncode, done.stdout


def audio_files(tree, inplace=False):
    dev = (tree if inplace else tree / ".cache/xnu-work") / "bsd/dev"
    return sorted(p.name for p in dev.iterdir() if p.name.startswith("PongAudio"))


def listed(conf):
    return conf.read_text().count("PongAudio")


def case_unnamed_anchor(root):
    conf = make_tree(root)
    code, out = run(root)
    assert code == 1, "a 27 tree cannot apply without an anchor: " + out
    assert "pass --anchor" in out, out
    assert listed(conf) == 0, "nothing may be listed after a failed anchor"
    assert len(audio_files(root)) == KERNEL_SET, audio_files(root)


def case_named_anchor(root):
    conf = make_tree(root)
    code, out = run(root, "--anchor", ANCHOR_27)
    assert code == 0, out
    assert "OK sources=%d conf=2" % KERNEL_SET in out, out
    assert "anchor line" in out, "the anchor has to be echoed: " + out
    assert listed(conf) == 2, conf.read_text()
    assert "PongAudioAmp.c" in conf.read_text()
    assert "PongAudioGeniI2c.c" in conf.read_text()
    assert "PongAudioAmp.o_CFLAGS_ADD=-DXNU_PONG_AUDIO" in out, \
        "the third edit has to be printed, not guessed"
    # second run: idempotent
    code, out = run(root, "--anchor", ANCHOR_27)
    assert code == 0, out
    assert "added 0, refreshed 0" in out, out
    assert listed(conf) == 2, "a second run must not list the entries twice"
    # check mode agrees once applied
    code, out = run(root, "--check")
    assert code == 0, out
    assert "both entries listed" in out, out


def case_check_writes_nothing(root):
    make_tree(root)
    code, out = run(root, "--check")
    assert code == 1, "check mode reports the gap as a failure: " + out
    assert "not in the tree" in out, out
    assert audio_files(root) == [], "check mode must not copy"


def case_stale_header(root):
    conf = make_tree(root)
    code, out = run(root, "--anchor", ANCHOR_27)
    assert code == 0, out
    stale = root / ".cache/xnu-work/bsd/dev/PongAudioPlan.h"
    stale.write_text(stale.read_text() + "\n/* stale copy */\n")
    code, out = run(root, "--anchor", ANCHOR_27)
    assert code == 0, out
    assert "refreshed 1" in out, out
    assert stale.read_bytes() == (REPO / "drivers/PongAudio/PongAudioPlan.h").read_bytes()


def case_no_seed(root):
    code, out = run(root)
    assert code == 1, "an unseeded tree is not an XNU tree: " + out
    assert "not seeded" in out, out


def case_inplace_tree(root):
    conf = make_tree(root, inplace=True)
    code, out = run(root, "--anchor", ANCHOR_27)
    assert code == 0, out
    assert "OK sources=%d conf=2" % KERNEL_SET in out, out
    assert "anchor line" in out, "the anchor has to be echoed: " + out
    assert listed(conf) == 2, conf.read_text()
    assert len(audio_files(root, inplace=True)) == KERNEL_SET


def case_afe_stays_out(root):
    make_tree(root)
    code, out = run(root, "--anchor", ANCHOR_27)
    assert code == 0, out
    names = audio_files(root)
    assert "PongAudioAfe.h" not in names, \
        "the 16 series AFE endpoint is frozen and travels only with host tests"
    assert "K60PmicGlinkAudio.h" not in names, \
        "the glink writer belongs to the power line"


CASES = [
    ("a 27 tree without the button driver fails loudly", case_unnamed_anchor),
    ("a named anchor lists both entries, once", case_named_anchor),
    ("check mode writes nothing", case_check_writes_nothing),
    ("a stale header is refreshed", case_stale_header),
    ("an unseeded tree is refused", case_no_seed),
    ("the frozen headers stay out", case_afe_stays_out),
    ("an in-place 27 tree is wired the same way", case_inplace_tree),
]


def main():
    failures = 0
    for name, case in CASES:
        root = pathlib.Path(tempfile.mkdtemp(prefix="audio-wiring-"))
        try:
            case(root)
        except AssertionError as exc:
            failures += 1
            print("FAIL %s\n     %s" % (name, exc))
        else:
            print("ok   %s" % name)
        finally:
            shutil.rmtree(root, ignore_errors=True)
    if failures:
        print("TESTS FAILED: %d of %d cases" % (failures, len(CASES)))
        return 1
    print("TESTS OK %d cases" % len(CASES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
