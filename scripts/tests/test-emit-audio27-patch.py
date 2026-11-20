#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Host tests for emit-audio27-patch.py.

The patch the 27 series carries has to be the bytes the applier's block
produces; otherwise the record digest and the patch drift apart with nobody
noticing. Each case builds a throwaway XNU-looking tree with the bsd_init anchor
and runs the emitter against it.
"""
import hashlib
import io
import pathlib
import shutil
import subprocess
import sys
import tempfile

NL = chr(10)
REPO = pathlib.Path(__file__).resolve().parents[2]
EMIT = REPO / "scripts" / "emit-audio27-patch.py"
WIRING = REPO / "scripts" / "apply-audio27-wiring.py"
SEED = (
    "/*\n"
    " * Copyright (c) 2000-2026 Apple Inc. All rights reserved.\n"
    " */\n"
    "\n"
    "int\n"
    "bsd_init(void)\n"
    "{\n"
    "\t/* Initialize the file systems. */\n"
    '\tbsd_init_kprintf("calling vfsinit\\n");\n'
    "\tvfsinit();\n"
    "\treturn 0;\n"
    "}\n"
)


def make_tree(root):
    (root / "bsd/kern").mkdir(parents=True)
    (root / "bsd/kern/bsd_init.c").write_text(SEED)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c",
                    "user.name=t", "commit", "-qm", "seed"], check=True)


def run(root, *args):
    done = subprocess.run([sys.executable, str(EMIT), str(root), "--wiring",
                           str(WIRING)] + list(args), capture_output=True, text=True)
    return done.returncode, done.stdout, done.stderr


def case_emits_and_applies(root):
    make_tree(root)
    code, out, err = run(root, "--check")
    assert code == 0, err
    assert "APPLY CHECK OK" in err, err
    assert out.startswith("diff --git a/bsd/kern/bsd_init.c b/bsd/kern/bsd_init.c"), out
    assert "+\t\textern int pong_audio_amp_probe(void) __attribute__((weak));" in out, out
    assert "@@ " in out and " bsd_init(void)" in out, "the hunk needs its function hint"
    digest = hashlib.sha256(out.encode()).hexdigest()
    assert "sha256 " + digest in err, err


def case_digest_pin(root):
    make_tree(root)
    code, out, _ = run(root)
    assert code == 0
    digest = hashlib.sha256(out.encode()).hexdigest()
    assert run(root, "--expect", digest)[0] == 0
    code, _, err = run(root, "--expect", "0" * 64)
    assert code == 1, "a changed digest has to be refused"
    assert "digest changed" in err, err


def case_missing_anchor(root):
    make_tree(root)
    path = root / "bsd/kern/bsd_init.c"
    path.write_text(SEED.replace('bsd_init_kprintf("calling vfsinit\\n");', "return 0;"))
    code, _, err = run(root)
    assert code == 1, err
    assert "anchor" in err, err


def case_wired_tree_still_emits(root):
    make_tree(root)
    _, pristine, _ = run(root)
    code, _, err = run(root, "--check")
    assert code == 0, err
    # wire it the way the applier does, in place, then emit again
    (root / "bsd/dev").mkdir(parents=True, exist_ok=True)
    (root / "bsd/conf").mkdir(parents=True, exist_ok=True)
    (root / "bsd/conf/files").write_text("bsd/dev/unix_startup.c\t\t\tstandard\n")
    done = subprocess.run([sys.executable, str(WIRING), str(root), "--hook-init",
                           "--anchor", "bsd/dev/unix_startup.c\t\t\tstandard"],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    code, wired, err = run(root)
    assert code == 0, err
    assert "stripped form" in err, err
    if wired != pristine:
        import difflib
        delta = "".join(difflib.unified_diff(pristine.splitlines(1), wired.splitlines(1),
                                             "pristine", "a wired tree"))
        raise AssertionError("a wired tree must emit the same bytes\n" + delta)


def case_no_bsd_init(root):
    (root / "bsd").mkdir(parents=True)
    code, _, err = run(root)
    assert code == 1, err
    assert "no bsd/kern/bsd_init.c" in err, err


def case_series_hooked_tree_is_skipped(root):
    make_tree(root)
    path = root / "bsd/kern/bsd_init.c"
    # what 0531 puts in bsd_init: a one-line comment and a one-line call, no block
    call = NL.join([
        "\t/* K60 audio amplifier probe; see patches/audio/0001:3508-3522. */",
        "\textern int pong_audio_amp_probe(void) __attribute__((weak));",
        "\tif (pong_audio_amp_probe != NULL) { (void)pong_audio_amp_probe(); }",
    ]) + NL
    path.write_text(SEED.replace("\tvfsinit();", call + "\tvfsinit();"))
    code, _, err = run(root)
    assert code == 3, (code, err)
    assert "nothing to emit" in err, err


CASES = (
    ("a fixture tree emits a patch git accepts", case_emits_and_applies),
    ("the digest can be pinned", case_digest_pin),
    ("a missing anchor is named", case_missing_anchor),
    ("a wired tree emits the same bytes", case_wired_tree_still_emits),
    ("a tree without bsd_init is refused", case_no_bsd_init),
    ("a tree the series hooked is skipped", case_series_hooked_tree_is_skipped),
)


def main():
    failed = 0
    for name, case in CASES:
        root = pathlib.Path(tempfile.mkdtemp(prefix="audio-emit-"))
        try:
            case(root)
        except AssertionError as error:
            failed += 1
            print("FAIL %s: %s" % (name, error))
        else:
            print("ok   %s" % name)
        finally:
            shutil.rmtree(root, ignore_errors=True)
    if failed:
        print("FAILED: %d case(s)" % failed)
        return 1
    print("TESTS OK %d cases" % len(CASES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
