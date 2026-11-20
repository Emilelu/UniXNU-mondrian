#!/usr/bin/env python3
"""Exercise scripts/check-audio27-fptrs.py against a copy of the real driver.

Each case copies drivers/PongAudio and patch 0531 into a temporary tree, breaks
one rule, and asks the checker about it. The first case is the tree as it is,
so a pass also says the shipped seam still satisfies the rules.

Usage: test-audio27-fptrs.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHECKER = REPO / "scripts" / "check-audio27-fptrs.py"
DRIVER = REPO / "drivers" / "PongAudio"
PATCH = REPO / "patches" / "xnu-12377" / "0531-k60-audio-amp-probe-call.patch"


def patch_source():
    """The patch this tree carries, or the one a gates checkout carries.

    The ADSP tree keeps the driver sources but not the xnu-12377 series, so the
    call site lives in the gates checkout there. A tree that does carry the
    series directory must carry the patch itself.
    """
    if PATCH.is_file():
        return PATCH
    if (REPO / "patches" / "xnu-12377").is_dir():
        return None
    candidates = [os.environ.get("AUDIO27_WEAK_PATCH")]
    gates = os.environ.get("K60_GATES")
    if gates:
        candidates.append(str(Path(gates) / "patches" / "xnu-12377" / PATCH.name))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


SOURCE = patch_source()


def fixture():
    root = Path(tempfile.mkdtemp(prefix="fptrs-"))
    target = root / "drivers" / "PongAudio"
    target.mkdir(parents=True)
    for path in sorted(DRIVER.iterdir()):
        if path.is_file():
            shutil.copy2(path, target / path.name)
    patch = root / "patches" / "xnu-12377"
    patch.mkdir(parents=True)
    shutil.copy2(SOURCE, patch / PATCH.name)
    return root


def edit(root, name, old, new):
    path = root / "drivers" / "PongAudio" / name
    text = path.read_text(encoding="utf-8")
    assert old in text, "%s does not contain %r" % (name, old)
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def run(root, *extra):
    args = [sys.executable, str(CHECKER)]
    if root is not None:
        args += ["--repo", str(root)]
    args += list(extra)
    done = subprocess.run(args, capture_output=True, text=True)
    return done.returncode, done.stdout + done.stderr


def case_good():
    root = fixture()
    code, out = run(root)
    return (code == 0 and "FPTRS OK: 4 tables, 10 callbacks in 5 pairs" in out
            and "weak call is int (void)" in out), out


def case_slew_field_gone():
    root = fixture()
    edit(root, "PongCodecLpi.h", "void *slew_ctx;", "void *slew_block;")
    code, out = run(root)
    return code == 1 and "slew_ctx" in out, out


def case_write_loses_value():
    root = fixture()
    edit(root, "PongCodecLpi.h",
         "void (*slew_write)(void *ctx, uint32_t reg, uint32_t value);",
         "void (*slew_write)(void *ctx, uint32_t reg);")
    code, out = run(root)
    return code == 1 and "not (void *ctx, uint32_t reg, value)" in out, out


def case_call_uses_wrong_context():
    root = fixture()
    edit(root, "PongCodecLpi.c", "l->io.slew_read(l->io.slew_ctx, 0u)",
         "l->io.slew_read(l->io.ctx, 0u)")
    code, out = run(root)
    return code == 1 and "not its own slew_ctx" in out, out


def case_fifth_table():
    root = fixture()
    path = root / "drivers" / "PongAudio" / "PongCodecSwr.h"
    text = path.read_text(encoding="utf-8")
    path.write_text(text + "\ntypedef struct {\n\tuint32_t (*fetch)(void *ctx, uint32_t reg);\n"
                          "\tvoid *ctx;\n} PongExtraIo;\n", encoding="utf-8")
    code, out = run(root)
    return code == 1 and "outside the four tables" in out, out


def case_weak_takes_argument():
    root = fixture()
    path = root / "patches" / "xnu-12377" / PATCH.name
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("int pong_audio_amp_probe(void)",
                                 "int pong_audio_amp_probe(int)", 1), encoding="utf-8")
    code, out = run(root)
    return code == 1 and "the weak declaration takes" in out, out


def case_weak_unguarded():
    root = fixture()
    path = root / "patches" / "xnu-12377" / PATCH.name
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("if (pong_audio_amp_probe != NULL) {", ""), encoding="utf-8")
    code, out = run(root)
    return code == 1 and "not guarded" in out, out


def case_read_returns_void():
    root = fixture()
    edit(root, "PongCodecSwr.h", "uint32_t (*read)(void *ctx, uint32_t reg);",
         "void (*read)(void *ctx, uint32_t reg);")
    code, out = run(root)
    return code == 1 and "pair returns" in out, out


def case_dead_member():
    root = fixture()
    edit(root, "PongCodecLpi.c", "l->io.slew_write(", "l->io.slew_store(")
    code, out = run(root)
    return code == 1 and "never called" in out, out


def case_missing_tree():
    code, out = run(Path(tempfile.mkdtemp(prefix="fptrs-empty-")))
    return code == 1 and "has no drivers/PongAudio" in out, out


def case_help():
    code, out = run(None, "--help")
    return code == 0 and "function-pointer tables" in out, out


def case_producer_loses_value():
    root = fixture()
    edit(root, "PongAudioAmp.c", "se_wr(void *ctx, uint32_t reg, uint32_t value)",
         "se_wr(void *ctx, uint32_t reg)")
    code, out = run(root)
    return (code == 1 and "defines se_wr as void (void *ctx, uint32_t reg), but"
            " PongGeniIo.write is void (*)(void *ctx, uint32_t reg, uint32_t value)" in out), out


def case_copy_from_other_field():
    root = fixture()
    edit(root, "PongCodecLpi.c", "l->io.slew_write = io != 0 ? io->slew_write : 0;",
         "l->io.slew_write = io != 0 ? io->write : 0;")
    code, out = run(root)
    return code == 1 and "from a different field" in out, out


def case_callback_zeroed():
    root = fixture()
    edit(root, "PongAudioAmp.c", "io.read = se_rd;", "io.read = 0;")
    code, out = run(root)
    return code == 1 and "neither a function" in out, out


def case_copy_from_wrong_type():
    root = fixture()
    edit(root, "PongCodecSwr.c", "s->io = *io;", "s->io = *hw;")
    code, out = run(root)
    return code == 1 and "not into a PongSwrIo" in out, out


def case_member_never_filled():
    root = fixture()
    edit(root, "PongCodecLpi.c", "\tl->io.slew_read = io != 0 ? io->slew_read : 0;\n", "")
    code, out = run(root)
    return code == 1 and "PongCodecLpiIo.slew_read is never assigned" in out, out


CASES = [
    ("good", case_good),
    ("slew_field_gone", case_slew_field_gone),
    ("write_loses_value", case_write_loses_value),
    ("call_uses_wrong_context", case_call_uses_wrong_context),
    ("fifth_table", case_fifth_table),
    ("weak_takes_argument", case_weak_takes_argument),
    ("weak_unguarded", case_weak_unguarded),
    ("read_returns_void", case_read_returns_void),
    ("dead_member", case_dead_member),
    ("missing_tree", case_missing_tree),
    ("help", case_help),
    ("producer_loses_value", case_producer_loses_value),
    ("copy_from_other_field", case_copy_from_other_field),
    ("callback_zeroed", case_callback_zeroed),
    ("copy_from_wrong_type", case_copy_from_wrong_type),
    ("member_never_filled", case_member_never_filled),
]


def main(argv):
    if any(a in ("-h", "--help") for a in argv[1:]):
        print((__doc__ or "").strip())
        return 0
    if SOURCE is None:
        print("TESTS SKIPPED: no 0531 patch in this tree, no AUDIO27_WEAK_PATCH"
              " and no K60_GATES")
        return 0
    failures = 0
    for name, case in CASES:
        ok, out = case()
        if not ok:
            failures += 1
            print("FAIL %s\n%s" % (name, out.strip()))
    if failures:
        print("TESTS FAILED: %d of %d cases" % (failures, len(CASES)))
        return 1
    print("TESTS OK %d cases" % len(CASES))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
