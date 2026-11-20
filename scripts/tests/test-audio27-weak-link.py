#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Host cases for check-audio27-weak-link.py: a held series, a selected patch,
a switch that cannot remove an "#if 1" call site, and a link proof that needs
both PongAudioAmp.o and bsd_init.o.

The fixtures are text only.  Nothing here compiles, links or opens a built
object: the checker is a preflight for selection and link inputs, not a build.
"""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
CHECK = REPO / "scripts/check-audio27-weak-link.py"
NAME = "0531-k60-audio-amp-probe-call.patch"


def patch_source():
    """The patch this tree carries, or the one a gates checkout carries.

    The ADSP tree keeps the driver sources but not the xnu-12377 series, so the
    call site lives in the gates checkout there. A tree that does carry the
    series directory must carry the patch itself.
    """
    local = REPO / "patches/xnu-12377" / NAME
    if local.is_file():
        return local
    if (REPO / "patches/xnu-12377").is_dir():
        return None
    candidates = [os.environ.get("AUDIO27_WEAK_PATCH")]
    gates = os.environ.get("K60_GATES")
    if gates:
        candidates.append(str(pathlib.Path(gates) / "patches/xnu-12377" / NAME))
    for candidate in candidates:
        if candidate and pathlib.Path(candidate).is_file():
            return pathlib.Path(candidate)
    return None


REAL_PATCH = patch_source()
NOTE = "NOTE audio: switch off, the call site is not linked"
cases = 0


def run(*args):
    done = subprocess.run([sys.executable, str(CHECK)] + list(args),
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return done.returncode, done.stdout


def make_tree(work, series_lines=None, patch_text=None, bsd_init=None,
              conf_files=True, hook=True):
    root = work / "tree"
    (root / "patches/xnu-12377").mkdir(parents=True, exist_ok=True)
    (root / "bsd/conf").mkdir(parents=True, exist_ok=True)
    (root / "bsd/kern").mkdir(parents=True, exist_ok=True)
    if patch_text is not None:
        (root / "patches/xnu-12377" / NAME).write_text(patch_text)
    else:
        shutil.copyfile(REAL_PATCH, root / "patches/xnu-12377" / NAME)
    if series_lines is not None:
        (root / "patches/xnu-12377/series").write_text("\n".join(series_lines) + "\n")
    if conf_files:
        (root / "bsd/conf/files").write_text(
            "bsd/dev/PongAudioGeniI2c.c standard\n"
            "bsd/dev/PongAudioAmp.c standard\n")
    if hook:
        (root / "scripts").mkdir(parents=True, exist_ok=True)
        (root / "scripts/k60-conf-files-hook.py").write_text("#!/usr/bin/env python3\n")
    if bsd_init is not None:
        (root / "bsd/kern/bsd_init.c").write_text(bsd_init)
    return root


def make_nm(work, lines):
    path = work / "nm.txt"
    path.write_text("\n".join(lines) + "\n")
    return path


def make_filelist(work, objects):
    path = work / "link.filelist"
    path.write_text("\n".join(str(obj) for obj in objects) + "\n")
    return path


def positive_fixture(work):
    tree = make_tree(work, [NAME])
    objs = work / "objs"
    objs.mkdir()
    amp = objs / "PongAudioAmp.o"
    init = objs / "bsd_init.o"
    filelist = make_filelist(work, [amp, init])
    nm = make_nm(work, [
        "%s: 0000000000000000 T _pong_audio_amp_probe" % amp,
        "%s:                  U _pong_audio_amp_probe" % init,
        "%s:                  w l_pong_audio_amp_probe$auth_ptr$ia$42271" % init,
    ])
    return tree, filelist, nm


def main():
    global cases
    if REAL_PATCH is None:
        print("TESTS SKIPPED: no 0531 patch in this tree, no AUDIO27_WEAK_PATCH"
              " and no K60_GATES")
        return
    work = pathlib.Path(tempfile.mkdtemp(prefix="audio27-weak-"))
    try:
        # 1. The gates state: a HOLD comment, no 0531 entry.  This is the only
        # honest off proof, and it must print the exact line the lane greps.
        held = work / "held"
        held.mkdir()
        tree = make_tree(held, [
            "# 0531-k60-audio-amp-probe-call.patch is deliberately NOT listed:",
            "# the kernel link cannot resolve its call site yet.",
            "0530-k60-spi-availability.patch",
        ])
        code, out = run("--tree", str(tree))
        assert code == 0, out
        assert NOTE in out.splitlines(), out
        assert "WEAK-LINK HOLD: " in out and NAME in out, out
        assert "present, not selected" in out, out
        cases += 1
        print("  ok   an explained HOLD is rc0 and prints the exact NOTE")

        # 2. A real 0531 selection without link inputs is not a success, even
        # though the source declares the reference weak.
        selected = work / "selected"
        selected.mkdir()
        tree = make_tree(selected, [NAME])
        code, out = run("--tree", str(tree))
        assert code == 1, out
        assert "WEAK-LINK policy NOTE" in out, out
        assert "not a linker proof" in out, out
        assert "no --link-filelist supplied" in out, out
        assert "no --symbols supplied" in out, out
        assert "WEAK-LINK FAILED: 0531 is selected" in out, out
        assert "WEAK-LINK OK" not in out, out
        cases += 1
        print("  ok   a selected 0531 without link inputs is rc1")

        # 3. --switch off must not claim the call site disappears: the patch is
        # unconditional, and XNU_PONG_AUDIO never reaches bsd_init.c.
        code, out = run("--tree", str(tree), "--switch", "off")
        assert code == 1, out
        assert ("0531 is unconditional (#if 1), so switching XNU_PONG_AUDIO off "
                "does not remove the call site") in out, out
        assert NOTE not in out, out
        assert "WEAK-LINK OK" not in out, out
        cases += 1
        print("  ok   --switch off on #if 1 is rc1 and never says not linked")

        # 4. A patch without the weak attribute is an ordinary undefined symbol;
        # the policy NOTE must not appear, and the verdict is still rc1.
        never = work / "never-weak"
        never.mkdir()
        patch_text = (
            "--- a/bsd/kern/bsd_init.c\n"
            "+++ b/bsd/kern/bsd_init.c\n"
            "@@ -1,2 +1,7 @@\n"
            " int\n"
            " bsd_init(void)\n"
            " {\n"
            "+#if 1\n"
            "+\textern int pong_audio_amp_probe(void);\n"
            "+\t(void)pong_audio_amp_probe();\n"
            "+#endif\n"
            " \tvfsinit();\n")
        tree = make_tree(never, [NAME], patch_text=patch_text)
        code, out = run("--tree", str(tree))
        assert code == 1, out
        assert "never declares" in out and "ordinary" in out, out
        assert "policy NOTE" not in out, out
        assert "is not declared weak" in out, out
        cases += 1
        print("  ok   a non-weak patch is rc1 and is not called a policy exception")

        # 5. Positive: a T definition in PongAudioAmp.o and the U from bsd_init.o,
        # both objects in the link.filelist.
        plus = work / "plus"
        plus.mkdir()
        tree, filelist, nm = positive_fixture(plus)
        code, out = run("--tree", str(tree), "--link-filelist", str(filelist),
                        "--symbols", str(nm))
        assert code == 0, out
        assert "WEAK-LINK OK: 0531 is selected" in out, out
        assert "PongAudioAmp.o is selected" in out and "bsd_init.o is selected" in out, out
        assert "T _pong_audio_amp_probe is defined in a linked object" in out, out
        cases += 1
        print("  ok   a linked T definition and bsd_init.o reference are rc0")

        # 5b. A W in the driver object is a weak (return-zero) shell, not the
        # real entry point.  The checker must not turn a weak definition green.
        weak = work / "weak-def"
        weak.mkdir()
        tree = make_tree(weak, [NAME])
        objs = weak / "objs"
        objs.mkdir()
        amp = objs / "PongAudioAmp.o"
        init = objs / "bsd_init.o"
        filelist = make_filelist(weak, [amp, init])
        nm = make_nm(weak, [
            "%s: 0000000000000000 W _pong_audio_amp_probe" % amp,
            "%s:                  U _pong_audio_amp_probe" % init,
        ])
        code, out = run("--tree", str(tree), "--link-filelist", str(filelist),
                        "--symbols", str(nm))
        assert code == 1, out
        assert "weak definition(s) present" in out, out
        assert "none is a T/t function definition" in out, out
        assert "WEAK-LINK OK" not in out, out
        cases += 1
        print("  ok   a weak W definition in the driver object is rc1")

        # 6. A definition in an object the linker never receives is not proof.
        # Only bsd_init.o is in the filelist, so the T in stray/PongAudioAmp.o is
        # named as outside the link and the result stays rc1.
        stray = work / "stray"
        stray.mkdir()
        tree = make_tree(stray, [NAME])
        objs = stray / "objs"
        objs.mkdir()
        filelist = make_filelist(stray, [objs / "bsd_init.o"])
        nm = make_nm(stray, [
            "%s: 0000000000000000 T _pong_audio_amp_probe" % (stray / "elsewhere/PongAudioAmp.o"),
            "%s:                  U _pong_audio_amp_probe" % (objs / "bsd_init.o"),
        ])
        code, out = run("--tree", str(tree), "--link-filelist", str(filelist),
                        "--symbols", str(nm))
        assert code == 1, out
        assert "outside link.filelist" in out, out
        assert "PongAudioAmp.o is not in" in out, out
        assert "WEAK-LINK OK" not in out, out
        cases += 1
        print("  ok   a definition outside link.filelist is named and stays rc1")

        # 7. No source at all: do not guess a tree, and never turn silence into a
        # success.  The adsp checkout has no local 0531.
        code, out = run()
        assert code == 1, out
        assert "no 0531 selection surface" in out, out
        assert "WEAK-LINK OK" not in out, out
        cases += 1
        print("  ok   no source is rc1")

        # 8. An empty series is not a HOLD: there is neither an entry nor a
        # comment, so it is not the 27 series and nothing is measured.
        empty = work / "empty"
        empty.mkdir()
        (empty / "series").write_text("# no audio patches here\n")
        code, out = run("--series", str(empty))
        assert code == 1, out
        assert "no 0531 entry, patch file, or HOLD comment" in out, out
        assert NOTE not in out, out
        cases += 1
        print("  ok   an empty series is rc1, not an off proof")

        # 9. A tree can already carry the call even when the series is unlisted
        # (an applier or hand edit).  The off line would then be false, so it is
        # rc1 and names bsd_init.c.
        hooked = work / "hooked"
        hooked.mkdir()
        tree = make_tree(hooked, [
            "# 0531-k60-audio-amp-probe-call.patch is deliberately NOT listed: held",
            "0530-k60-spi-availability.patch",
        ], bsd_init="int bsd_init(void) {\n\tpong_audio_amp_probe();\n\treturn 0;\n}\n")
        code, out = run("--tree", str(tree))
        assert code == 1, out
        assert "already carries" in out and "bsd_init.c" in out, out
        assert NOTE not in out, out
        cases += 1
        print("  ok   an unlisted series over an already-hooked tree is rc1")

        # 10. Both objects are in the filelist, but the T is in a stub object.
        # A local definition is not the driver; this must not turn green.
        stub = work / "stub"
        stub.mkdir()
        tree = make_tree(stub, [NAME])
        objs = stub / "objs"
        objs.mkdir()
        filelist = make_filelist(stub, [objs / "PongAudioAmp.o", objs / "bsd_init.o", objs / "stub.o"])
        nm = make_nm(stub, [
            "%s: 0000000000000000 T _pong_audio_amp_probe" % (objs / "stub.o"),
            "%s:                  U _pong_audio_amp_probe" % (objs / "bsd_init.o"),
        ])
        code, out = run("--tree", str(tree), "--link-filelist", str(filelist),
                        "--symbols", str(nm))
        assert code == 1, out
        assert "not in PongAudioAmp.o" in out, out
        assert "WEAK-LINK OK" not in out, out
        cases += 1
        print("  ok   a T in a linked stub object is not the driver definition")

        # 11. Two selection sources that disagree are ambiguous.  Refuse
        # instead of silently picking one and proving the wrong tree.
        other = work / "other"
        other.mkdir()
        (other / "series").write_text("# 0531 held elsewhere\n")
        code, out = run("--tree", str(tree), "--series", str(other))
        assert code == 1, out
        assert "pass one selection source" in out, out
        cases += 1
        print("  ok   conflicting --tree and --series are rc1")

        # 12. A listed entry whose patch file is absent is a broken input, not a
        # weak-link state.
        missing = work / "missing"
        missing.mkdir()
        (missing / "series").write_text(NAME + "\n")
        code, out = run("--series", str(missing))
        assert code == 1, out
        assert "but no such patch file exists" in out, out
        assert "WEAK-LINK OK" not in out, out
        cases += 1
        print("  ok   a selected entry with no patch file is rc1")

        print("TESTS OK %d cases" % cases)
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
