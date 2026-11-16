#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Self-test for scripts/check-define-scope.py (P-213).

The gate answers one question: can the object that contains a `#if defined(XNU_x)`
guard actually see `-DXNU_x`? Its own failure mode is modelling the shell badly --
the first version read only the literal text of an assignment and therefore
reported a define that is accumulated into `PERSONALITY_CFLAGS` as reaching one
object. Case 4 is that regression: it must stay green.

Every case builds a throwaway repo, so the verdicts are checked against text this
file controls, not against whatever the real tree happens to contain today.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "check-define-scope.py"

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def load_gate():
    spec = importlib.util.spec_from_file_location("check_define_scope", GATE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_repo(root: Path, build_script: str, patches: dict[str, str]) -> Path:
    """Lay out the two files the gate reads: the build script and the series."""
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "patches" / "xnu").mkdir(parents=True, exist_ok=True)
    (root / "scripts" / "build-xnu-4k-baseline.sh").write_text(build_script, encoding="utf-8")
    names = []
    for index, (name, body) in enumerate(patches.items(), 1):
        (root / "patches" / "xnu" / name).write_text(body, encoding="utf-8")
        names.append(name)
    (root / "patches" / "xnu" / "series").write_text("\n".join(names) + "\n", encoding="utf-8")
    return root


def patch_for(path: str, guard: str) -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        f"@@ -1,2 +1,4 @@\n"
        f" int anchor;\n"
        f"+{guard}\n"
        f"+int guarded;\n"
        f"+#endif\n"
    )


@case
def a_global_define_reaches_every_object():
    gate = load_gate()
    with tempfile.TemporaryDirectory() as tmp:
        repo = make_repo(
            Path(tmp),
            'EXTRA_CFLAGS="-DXNU_ANYWHERE=1"\n',
            {"0001-guard.patch": patch_for("bsd/kern/bsd_init.c", "#if defined(XNU_ANYWHERE)")},
        )
        problems, unknowns, guards = gate.check(repo)
    assert not problems, problems
    assert guards == 1, guards
    assert not unknowns, unknowns


@case
def an_object_scoped_define_reaches_that_object():
    gate = load_gate()
    with tempfile.TemporaryDirectory() as tmp:
        repo = make_repo(
            Path(tmp),
            'EXTRA_MAKE_ARGS+=("kern_exec.o_CFLAGS_ADD=-DXNU_NATIVE_RAM_BLOCK=1")\n',
            {"0001-guard.patch": patch_for("bsd/kern/kern_exec.c", "#if XNU_NATIVE_RAM_BLOCK")},
        )
        problems, unknowns, _guards = gate.check(repo)
    assert not problems, problems
    assert not unknowns, unknowns


@case
def a_guard_in_another_object_fails():
    gate = load_gate()
    with tempfile.TemporaryDirectory() as tmp:
        repo = make_repo(
            Path(tmp),
            'EXTRA_MAKE_ARGS+=("kern_exec.o_CFLAGS_ADD=-DXNU_NATIVE_RAM_BLOCK=1")\n',
            {"0001-guard.patch": patch_for("iokit/bsddev/IOKitBSDInit.cpp", "#if defined(XNU_NATIVE_RAM_BLOCK)")},
        )
        problems, _unknowns, guards = gate.check(repo)
    assert guards == 1, guards
    assert problems, "a guard in a different object must fail"
    joined = " ".join(problems)
    assert "IOKitBSDInit.cpo" in joined, joined
    assert "kern_exec.o" in joined, joined
    assert "P-208" in joined, joined


@case
def an_accumulated_variable_is_followed():
    """P-213: PERSONALITY_CFLAGS accumulates the define, then one object gets it."""
    gate = load_gate()
    with tempfile.TemporaryDirectory() as tmp:
        script = (
            'PERSONALITY_CFLAGS="-DXNU_NATIVE_RAM_BLOCK=1"\n'
            'PERSONALITY_CFLAGS="$PERSONALITY_CFLAGS -DXNU_OTHER=1"\n'
            'EXTRA_MAKE_ARGS+=("KernelConfigTables.cpo_CFLAGS_ADD=$PERSONALITY_CFLAGS")\n'
        )
        repo = make_repo(
            Path(tmp),
            script,
            {
                "0001-a.patch": patch_for("bsd/kern/kern_exec.c", "#if defined(XNU_NATIVE_RAM_BLOCK)"),
                "0002-b.patch": patch_for("bsd/kern/kern_exec.c", "#if defined(XNU_OTHER)"),
            },
        )
        problems, unknowns, guards = gate.check(repo)
    assert guards == 2, guards
    assert not unknowns, unknowns
    # Both guards sit in kern_exec.c, whose object is kern_exec.o; the defines
    # reach KernelConfigTables.cpo only, so these two ARE real problems. The
    # regression this case pins is different: the gate must resolve the variable
    # instead of claiming the define is assigned by nobody.
    assert len(problems) == 2, problems
    assert all("KernelConfigTables.cpo" in p for p in problems), problems


@case
def an_accumulated_variable_reaches_its_own_object():
    gate = load_gate()
    with tempfile.TemporaryDirectory() as tmp:
        script = (
            'PERSONALITY_CFLAGS="-DXNU_NATIVE_RAM_BLOCK=1"\n'
            'PERSONALITY_CFLAGS="$PERSONALITY_CFLAGS -DXNU_OTHER=1"\n'
            'EXTRA_MAKE_ARGS+=("KernelConfigTables.cpo_CFLAGS_ADD=$PERSONALITY_CFLAGS")\n'
        )
        repo = make_repo(
            Path(tmp),
            script,
            {"0001-a.patch": patch_for("osfmk/kern/KernelConfigTables.cpp", "#if defined(XNU_NATIVE_RAM_BLOCK)")},
        )
        problems, unknowns, _guards = gate.check(repo)
    assert not problems, problems
    assert not unknowns, unknowns


@case
def a_trailing_comment_defines_nothing():
    gate = load_gate()
    with tempfile.TemporaryDirectory() as tmp:
        repo = make_repo(
            Path(tmp),
            'EXTRA_CFLAGS="-Wno-thing"  # -DXNU_COMMENTED=1\n',
            {"0001-guard.patch": patch_for("bsd/kern/bsd_init.c", "#if defined(XNU_COMMENTED)")},
        )
        problems, unknowns, guards = gate.check(repo)
    assert guards == 1, guards
    assert not problems, problems
    assert unknowns and "XNU_COMMENTED" in unknowns[0], unknowns


@case
def an_unknown_define_is_skipped_not_failed():
    gate = load_gate()
    with tempfile.TemporaryDirectory() as tmp:
        repo = make_repo(
            Path(tmp),
            'EXTRA_CFLAGS="-Wno-thing"\n',
            {"0001-guard.patch": patch_for("bsd/kern/bsd_init.c", "#if defined(XNU_FROM_A_CONFIG_HEADER)")},
        )
        problems, unknowns, _guards = gate.check(repo)
    assert not problems, problems
    assert unknowns and "XNU_FROM_A_CONFIG_HEADER" in unknowns[0], unknowns


@case
def a_cpp_guard_maps_to_a_cpo_object():
    gate = load_gate()
    with tempfile.TemporaryDirectory() as tmp:
        repo = make_repo(
            Path(tmp),
            'EXTRA_MAKE_ARGS+=("ArmDTPlatform.cpo_CFLAGS_ADD=-DXNU_PONG_WIFI=1")\n',
            {"0001-guard.patch": patch_for("drivers/ArmDTPlatform/ArmDTPlatform.cpp", "#if XNU_PONG_WIFI")},
        )
        problems, unknowns, _guards = gate.check(repo)
    assert not problems, problems
    assert not unknowns, unknowns


@case
def the_real_repository_is_self_consistent():
    gate = load_gate()
    problems, _unknowns, guards = gate.check(ROOT)
    assert guards > 50, f"expected the real series to carry many guards, saw {guards}"
    assert not problems, problems


def main() -> int:
    failures = 0
    for fn in CASES:
        try:
            fn()
            print(f"ok   {fn.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001 - a broken gate is a failure, not a crash
            failures += 1
            print(f"FAIL {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"TESTS OK {len(CASES) - failures} case(s) ({failures} failure(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
