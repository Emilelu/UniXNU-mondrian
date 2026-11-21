#!/usr/bin/env python3
"""Tests for scripts/check-audio27-hold.py.

The checker is dormant on today's lane, so most cases are fixtures: they make
the guard a switch, select 0531 and give (or withhold) the builder define.  A
fixture repo is cheaper and more honest than applying the patch to a real XNU
tree.  The first case still runs the real lane, because a fixture cannot prove
that the real series and patch are the ones we think they are.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GATE = ROOT / "scripts/check-audio27-hold.py"
SERIES_NAME = "0531-k60-audio-amp-probe-call.patch"
MACRO = "XNU_PONG_AUDIO_CALL"
CASES = 0


def run_gate(args, cwd=None):
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return subprocess.run(
        [sys.executable, "-B", str(GATE), *args],
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def check(proc, code, contains=(), missing=(), label=""):
    global CASES
    CASES += 1
    combined = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != code:
        raise AssertionError(
            f"{label}: expected rc {code}, got {proc.returncode}\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    for needle in contains:
        if needle not in combined:
            raise AssertionError(
                f"{label}: missing {needle!r}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
            )
    for needle in missing:
        if needle in combined:
            raise AssertionError(
                f"{label}: unexpectedly found {needle!r}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
            )


def patch_text(guard, include_call=True):
    lines = [
        "diff --git a/bsd/kern/bsd_init.c b/bsd/kern/bsd_init.c",
        "index 97827e4..6b0aae0 100644",
        "--- a/bsd/kern/bsd_init.c",
        "+++ b/bsd/kern/bsd_init.c",
    ]
    if include_call:
        lines.extend(
            [
                "@@ -795,2 +795,12 @@ bsd_init(void)",
                " \tbsd_init_kprintf(\"calling vfsinit\\n\");",
                f"+{guard}",
                "+\t{",
                "+\t\textern int pong_audio_amp_probe(void) __attribute__((weak));",
                "+",
                "+\t\tif (pong_audio_amp_probe != NULL) {",
                "+\t\t\t(void)pong_audio_amp_probe();",
                "+\t\t}",
                "+\t}",
                "+#endif",
                " \tvfsinit();",
            ]
        )
    else:
        lines.extend(
            [
                "@@ -795,2 +795,2 @@ bsd_init(void)",
                " \tbsd_init_kprintf(\"calling vfsinit\\n\");",
                " \tvfsinit();",
            ]
        )
    return "\n".join(lines) + "\n"


def source_text(guard, include_call=True):
    lines = [
        "void",
        "bsd_init(void)",
        "{",
        "\tbsd_init_kprintf(\"calling vfsinit\\n\");",
    ]
    if include_call:
        lines.extend(
            [
                guard,
                "\t{",
                "\t\textern int pong_audio_amp_probe(void) __attribute__((weak));",
                "",
                "\t\tif (pong_audio_amp_probe != NULL) {",
                "\t\t\t(void)pong_audio_amp_probe();",
                "\t\t}",
                "\t}",
                "#endif",
            ]
        )
    lines.extend(["\tvfsinit();", "}", ""])
    return "\n".join(lines)


def fixture(base, series_line, guard="#if 1", builder=None, tree_guard=None, include_call=True):
    repo = base / "repo"
    patch_dir = repo / "patches/xnu-12377"
    patch_dir.mkdir(parents=True, exist_ok=True)
    (patch_dir / "series").write_text(series_line, encoding="utf-8")
    (patch_dir / SERIES_NAME).write_text(patch_text(guard, include_call), encoding="utf-8")

    builder_path = None
    if builder is not None:
        scripts = repo / "scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        builder_path = scripts / "build-xnu-generic.sh"
        builder_path.write_text(builder + "\n", encoding="utf-8")

    tree = None
    if tree_guard is not None:
        tree = repo / "tree"
        source = tree / "bsd/kern/bsd_init.c"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(source_text(tree_guard, include_call), encoding="utf-8")
    return repo, builder_path, tree


def fixture_args(repo, builder_path=None, tree=None, extra=()):
    args = ["--repo", str(repo)]
    if builder_path is not None:
        args.extend(["--builder", str(builder_path)])
    if tree is not None:
        args.extend(["--tree", str(tree)])
    args.extend(extra)
    return args


def selected():
    return SERIES_NAME + "\n"


def held():
    return "# " + SERIES_NAME + " is held: the call-site guard is literal\n"


def main():
    # 1. The real lane: series:52 selects 0531, the patch guard is #if 1, and
    # that is a dormant result, not a green source-side criterion.
    proc = run_gate([])
    check(
        proc,
        0,
        contains=[
            "HOLD series: patches/xnu-12377/series:52 selects " + SERIES_NAME,
            'HOLD patch: patches/xnu-12377/' + SERIES_NAME + ':7 guard "#if 1" (bsd_init.c:796)',
            "HOLD call: patches/xnu-12377/" + SERIES_NAME + ":24 pong_audio_amp_probe() (bsd_init.c:813)",
            "HOLD dormant: the call-site guard is unconditional",
        ],
        label="real lane is dormant",
    )

    # 2. --strict turns the dormant result into a failure; this is the part
    # that will make the checker bite on the day the guard changes.
    proc = run_gate(["--strict"])
    check(
        proc,
        1,
        contains=["HOLD strict: the check is dormant, so --strict turns this into a failure"],
        missing=[],
        label="--strict fails dormant",
    )

    with tempfile.TemporaryDirectory(prefix="audio27-hold-") as tmp:
        base = Path(tmp)

        # 3. The condition-2 shape: selected, switch, and bsd_init.o gets the
        # same -D.  This is the only fixture that may print HOLD OK.
        repo, builder, _ = fixture(
            base / "ok",
            selected(),
            guard="#if defined(" + MACRO + ")",
            builder="bsd_init.o_CFLAGS_ADD=-D" + MACRO + "=1",
        )
        proc = run_gate(fixture_args(repo, builder))
        check(
            proc,
            0,
            contains=[
                "HOLD series:",
                "selects " + SERIES_NAME,
                "HOLD patch:",
                'guard "#if defined(' + MACRO + ')"',
                "HOLD build:",
                "gives bsd_init.o -D" + MACRO,
                "HOLD OK: 0531 is selected and bsd_init.c is guarded by a preprocessor switch",
                "HOLD source-side conditions 1-2 hold",
            ],
            missing=["HOLD dormant"],
            label="switch plus builder define is the active criterion",
        )

        # 4. Same guard, no builder define: condition 2 must fail, not pass
        # because the patch text looks controllable.
        repo, builder, _ = fixture(
            base / "missing-builder",
            selected(),
            guard="#if defined(" + MACRO + ")",
            builder="bsd_init.o_CFLAGS_ADD=-DXNU_SHENG_PMGR=1",
        )
        proc = run_gate(fixture_args(repo, builder))
        check(
            proc,
            1,
            contains=["HOLD FAILED:", "no builder gives bsd_init.o -D" + MACRO, "release condition 2"],
            label="switch without builder define fails",
        )

        # 5. A define on PongAudioAmp.o is not visible to bsd_init.c.
        repo, builder, _ = fixture(
            base / "wrong-object",
            selected(),
            guard="#if defined(" + MACRO + ")",
            builder="PongAudioAmp.o_CFLAGS_ADD=-D" + MACRO + "=1",
        )
        proc = run_gate(fixture_args(repo, builder))
        check(
            proc,
            1,
            contains=["HOLD FAILED:", "no bsd_init.o_CFLAGS_ADD with -D" + MACRO],
            label="define on another object does not count",
        )

        # 6. Selected but literal guard: still dormant; selecting the patch
        # does not make an unconditional call controllable.
        repo, builder, _ = fixture(
            base / "unconditional",
            selected(),
            guard="#if 1",
            builder="bsd_init.o_CFLAGS_ADD=-D" + MACRO + "=1",
        )
        proc = run_gate(fixture_args(repo, builder))
        check(
            proc,
            0,
            contains=["HOLD dormant: the call-site guard is unconditional", "release condition 2"],
            label="selected plus #if 1 stays dormant",
        )

        # 7. Held comment: the series has 0531 but does not select it.
        repo, builder, _ = fixture(
            base / "held",
            held(),
            guard="#if defined(" + MACRO + ")",
            builder="bsd_init.o_CFLAGS_ADD=-D" + MACRO + "=1",
        )
        proc = run_gate(fixture_args(repo, builder))
        check(
            proc,
            0,
            contains=["holds 0531", "HOLD dormant: 0531 is not selected by the series"],
            label="held comment is dormant",
        )

        # 8. No series entry and no comment: the gate does not duplicate
        # series accounting; it reports that the patch is not in a build.
        repo, builder, _ = fixture(
            base / "no-entry",
            "",
            guard="#if defined(" + MACRO + ")",
            builder="bsd_init.o_CFLAGS_ADD=-D" + MACRO + "=1",
        )
        proc = run_gate(fixture_args(repo, builder))
        check(
            proc,
            0,
            contains=["has no 0531 entry", "HOLD dormant: 0531 is not selected by the series"],
            label="no series entry is dormant",
        )

        # 9. #if 0 is dead code, not a switch.
        repo, builder, _ = fixture(
            base / "disabled",
            selected(),
            guard="#if 0",
            builder="bsd_init.o_CFLAGS_ADD=-D" + MACRO + "=1",
        )
        proc = run_gate(fixture_args(repo, builder))
        check(
            proc,
            0,
            contains=["HOLD dormant: the call is under #if 0"],
            label="#if 0 is dormant",
        )

        # 10. An expression we cannot classify is not a pass (P-279).
        repo, builder, _ = fixture(
            base / "unknown",
            selected(),
            guard="#if SOME_CONFIG",
            builder="bsd_init.o_CFLAGS_ADD=-D" + MACRO + "=1",
        )
        proc = run_gate(fixture_args(repo, builder))
        check(
            proc,
            2,
            contains=["HOLD cannot classify"],
            label="unknown guard exits 2",
        )

        # 11. Missing series is an input error, not a dormant pass.
        repo, builder, _ = fixture(
            base / "missing-series",
            selected(),
            guard="#if 1",
        )
        (repo / "patches/xnu-12377/series").unlink()
        proc = run_gate(fixture_args(repo, builder))
        check(proc, 2, contains=["cannot read series"], label="missing series exits 2")

        # 12. Missing 0531 patch is an input error.
        repo, builder, _ = fixture(base / "missing-patch", selected(), guard="#if 1")
        (repo / "patches/xnu-12377" / SERIES_NAME).unlink()
        proc = run_gate(fixture_args(repo, builder))
        check(proc, 2, contains=["no 0531*.patch"], label="missing patch exits 2")

        # 13. Source and patch agree: the checker reads the real source guard
        # and still reports the active criterion when the builder defines it.
        repo, builder, tree = fixture(
            base / "source-agree",
            selected(),
            guard="#if defined(" + MACRO + ")",
            builder="bsd_init.o_CFLAGS_ADD=-D" + MACRO + "=1",
            tree_guard="#if defined(" + MACRO + ")",
        )
        proc = run_gate(fixture_args(repo, builder, tree))
        check(
            proc,
            0,
            contains=["HOLD source: tree/bsd/kern/bsd_init.c:", "guard \"#if defined(" + MACRO + ")\"", "HOLD OK:"],
            label="source and patch agree",
        )

        # 14. Source drift: the tree carries a different guard than the patch.
        repo, builder, tree = fixture(
            base / "source-drift",
            selected(),
            guard="#if 1",
            builder="bsd_init.o_CFLAGS_ADD=-D" + MACRO + "=1",
            tree_guard="#if defined(" + MACRO + ")",
        )
        proc = run_gate(fixture_args(repo, builder, tree))
        check(
            proc,
            1,
            contains=["HOLD FAILED:", "the source guard and the patch guard disagree"],
            label="source and patch drift fails",
        )

        # 15. No call in the patch: nothing to hold; dormant.
        repo, builder, _ = fixture(
            base / "no-call",
            selected(),
            guard="#if 1",
            include_call=False,
        )
        proc = run_gate(fixture_args(repo, builder))
        check(
            proc,
            0,
            contains=["carries no pong_audio_amp_probe call", "HOLD dormant: the patch has no call to check"],
            label="no call is dormant",
        )

        # 16. Inverted switch: defining it compiles the call out, so it cannot
        # satisfy release condition 1.
        repo, builder, _ = fixture(
            base / "inverted",
            selected(),
            guard="#ifndef " + MACRO,
            builder="bsd_init.o_CFLAGS_ADD=-D" + MACRO + "=1",
        )
        proc = run_gate(fixture_args(repo, builder))
        check(
            proc,
            1,
            contains=["HOLD FAILED:", "guard is inverted"],
            label="inverted guard fails",
        )

    # 17. Help works without touching the repo.
    proc = run_gate(["--help"])
    check(
        proc,
        0,
        contains=["usage: check-audio27-hold.py", "--strict", "--tree"],
        label="help",
    )

    print(f"TESTS OK {CASES} cases")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f"TESTS FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
