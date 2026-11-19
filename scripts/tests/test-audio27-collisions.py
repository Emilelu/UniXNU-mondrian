#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Host tests for scripts/check-audio27-collisions.py.

Four properties: a tree without the names is green, a tree carrying one of them
is red and says which, the hook our applier writes is not counted as a clash
(but a foreign definition beside it still is), and something that is not a tree
is refused instead of reported green.
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE.parent / "check-audio27-collisions.py"


def tree(content=None):
    root = pathlib.Path(tempfile.mkdtemp(prefix="k60-coll-"))
    (root / "bsd/kern").mkdir(parents=True, exist_ok=True)
    (root / "bsd/kern/vfs_syscalls.c").write_text("int vfs_syscall(void) { return 0; }\n")
    if content:
        (root / "osfmk").mkdir(parents=True, exist_ok=True)
        (root / "osfmk/k60_clash.c").write_text(content)
    return root


def run(root):
    done = subprocess.run([sys.executable, str(SCRIPT), str(root)],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          universal_newlines=True)
    return done.returncode, done.stdout


def case_clean():
    root = tree()
    try:
        code, out = run(root)
        assert code == 0, out
        assert "COLLISION OK: 11 exported symbols" in out, out
        return "a tree without the names is green"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def case_clash():
    root = tree("int pong_geni_poll(void) { return 0; }\n")
    try:
        code, out = run(root)
        assert code == 1, out
        assert "COLLISION:" in out and "pong_geni_poll" in out, out
        assert "osfmk/k60_clash.c:1" in out, out
        return "a planted clash is named with its line"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def case_not_a_tree():
    root = pathlib.Path(tempfile.mkdtemp(prefix="k60-coll-"))
    try:
        code, out = run(root)
        assert code == 1, out
        assert "that is not an XNU tree" in out, out
        return "an empty directory is refused, not passed"
    finally:
        shutil.rmtree(root, ignore_errors=True)


HOOK = """#if 1
	/* K60 audio amplifier probe (drivers/PongAudio): the amplifiers answer a
	 * chip-id read over AP-owned GENI I2C without the DSP. Inert unless the
	 * image is booted with pong_audio_probe=1. */
	{
		extern int pong_audio_amp_probe(void);
		(void)pong_audio_amp_probe();
	}
#endif
"""


def case_hook_is_not_a_clash():
    root = tree()
    hooked = root / "bsd/kern/bsd_init.c"
    hooked.write_text(HOOK)
    try:
        code, out = run(root)
        assert code == 0, "the wiring's own call site is not a collision: " + out
        assert "skipping the wiring hook: bsd/kern/bsd_init.c" in out, out
        # a foreign definition beside the hook still has to fail
        (root / "osfmk").mkdir(parents=True, exist_ok=True)
        (root / "osfmk/k60_clash.c").write_text("int pong_audio_amp_probe(void) { return 0; }\n")
        code, out = run(root)
        assert code == 1, out
        assert "pong_audio_amp_probe" in out and "osfmk/k60_clash.c:1" in out, out
        return "the hook is exempt, a second definition is not"
    finally:
        shutil.rmtree(root, ignore_errors=True)


CASES = [case_clean, case_clash, case_hook_is_not_a_clash, case_not_a_tree]


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
