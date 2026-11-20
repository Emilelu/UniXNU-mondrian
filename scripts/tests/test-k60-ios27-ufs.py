#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Self-test for the native UFS wiring check in scripts/check-ios27-device.py (P-267).

The gate's own failure mode is a manufactured pass: an archive path that appears
in a script which never runs, or a producer that writes somewhere else.  Every
case below starts from fixture device repositories that differ only in the
wiring, so a green result can only come from following the wiring - the profile,
the builder the picker selects, the producer that builder runs, and the archive
that producer writes.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "check-ios27-device.py"

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def load_gate():
    spec = importlib.util.spec_from_file_location("check_ios27_device", GATE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


GATE_MODULE = load_gate()
LINK = GATE_MODULE.FIXTURE_LINK
CALL = GATE_MODULE.FIXTURE_CALL
PRODUCER = GATE_MODULE.FIXTURE_PRODUCER


def board(profile="ipados-27.0.1-24A446", defconfig="mondrian_ios27_defconfig",
          remove=(), source=True, fragments=()):
    kernel = 'pong_native_driver_source = "{tree}"' if source else "# no driver source"
    removed = ", ".join('"%s"' % item for item in remove)
    fragment_line = ""
    if fragments:
        fragment_line = "config_fragments = [%s]" % ", ".join('"%s"' % item for item in fragments)
    return """schema_version = 2

[board]
os_profile = "%s"

[kernel]
defconfig = "mondrian_defconfig"
%s
%s

[os_overrides."%s"]
remove = [%s]

[os_overrides."%s".kernel]
defconfig = "%s"
""" % (profile, kernel, fragment_line, profile, removed, profile, defconfig)


def device(tmp, switch="n", builder=LINK, producer=PRODUCER, board_text=None,
           defconfig="mondrian_ios27_defconfig", builder_name="build-xnu-generic.sh",
           configs=(), scripts=()):
    root = Path(tmp)
    for name in ("configs", "scripts"):
        (root / name).mkdir(parents=True, exist_ok=True)
    (root / "board.toml").write_text(board_text or board(), encoding="utf-8")
    body = "CONFIG_XNU_NATIVE_UFS=%s\n" % switch if switch else ""
    (root / "configs" / defconfig).write_text(body, encoding="utf-8")
    for name, text in configs:
        (root / "configs" / name).write_text(text, encoding="utf-8")
    (root / "scripts" / "pick-xnu-builder.sh").write_text(GATE_MODULE.FIXTURE_PICKER, encoding="utf-8")
    (root / "scripts" / "build-xnu-4k-baseline.sh").write_text(GATE_MODULE.FIXTURE_ENTRY, encoding="utf-8")
    (root / "scripts" / builder_name).write_text(builder, encoding="utf-8")
    for name, text in scripts:
        (root / "scripts" / name).write_text(text, encoding="utf-8")
    if producer is not None:
        (root / "scripts" / "build-pong-ufs-probe-macos.py").write_text(producer, encoding="utf-8")
    return root


@case
def a_switch_that_is_off_is_pending_not_drift():
    gate = load_gate()
    with tempfile.TemporaryDirectory() as tmp:
        root = device(tmp, switch="n")
        status, why = gate.ufs_archive(str(root))
    assert status == "pending", status
    assert "CONFIG_XNU_NATIVE_UFS=n" in why, why
    assert "nothing writes the archive" in why, why


@case
def a_pending_answer_names_what_enabling_would_still_miss():
    """The reason travels with the pending state; a bare tick would hide it."""
    gate = load_gate()
    with tempfile.TemporaryDirectory() as tmp:
        status, why = gate.ufs_archive(str(device(tmp, switch="n")))
    assert status == "pending", status
    assert "enabling it would not be enough" in why, why


@case
def enabling_the_switch_without_a_producer_is_pending():
    gate = load_gate()
    with tempfile.TemporaryDirectory() as tmp:
        status, why = gate.ufs_archive(str(device(tmp, switch="y")))
    assert status == "pending", status
    assert "nothing writes the archive" in why, why


@case
def a_dormant_libtool_line_is_not_a_producer():
    """The false acceptance this check replaced: path plus libtool, never run."""
    gate = load_gate()
    dormant = LINK + "\n# libtool -static -o $ROOT/build/native-ufs/libNativeUfs.a transport.o\n"
    with tempfile.TemporaryDirectory() as tmp:
        status, why = gate.ufs_archive(str(device(tmp, switch="y", builder=dormant)))
    assert status == "pending", status
    assert "nothing writes the archive" in why, why


@case
def a_producer_that_writes_another_archive_is_pending():
    gate = load_gate()
    with tempfile.TemporaryDirectory() as tmp:
        root = device(tmp, switch="y", builder=CALL)
        (root / "scripts" / "build-pong-ufs-probe-macos.py").write_text(
            PRODUCER.replace("libNativeUfs.a", "libShengUfs.a"), encoding="utf-8")
        status, why = gate.ufs_archive(str(root))
    assert status == "pending", status
    assert "build/native-ufs/libShengUfs.a" in why, why
    assert "libNativeUfs.a" in why, why


@case
def a_producer_the_builder_runs_is_ok():
    gate = load_gate()
    with tempfile.TemporaryDirectory() as tmp:
        status, why = gate.ufs_archive(str(device(tmp, switch="y", builder=CALL)))
    assert status == "ok", why
    assert "writes build/native-ufs/libNativeUfs.a" in why, why


@case
def a_producer_guarded_off_is_not_a_producer():
    """Reachability, not presence: a call inside 'switch is not 1' never runs."""
    gate = load_gate()
    off = '#!/bin/sh\nif [ "$XNU_NATIVE_UFS" != 1 ]; then\n' + \
        '  python3 "$PONG_NATIVE_DRIVER_SOURCE/scripts/build-pong-ufs-probe-macos.py" --tree "$ROOT"\nfi\n' + LINK
    with tempfile.TemporaryDirectory() as tmp:
        status, why = gate.ufs_archive(str(device(tmp, switch="y", builder=off)))
    assert status == "pending", status
    assert "nothing writes the archive" in why, why


@case
def an_output_outside_the_tree_is_not_a_pass():
    gate = load_gate()
    absolute = PRODUCER.replace("tree = args.tree.resolve()", "tree = Path('/opt/pong/tree')")
    with tempfile.TemporaryDirectory() as tmp:
        status, why = gate.ufs_archive(str(device(tmp, switch="y", builder=CALL, producer=absolute)))
    assert status == "pending", status
    assert "not under the build tree" in why, why


@case
def the_profile_must_supply_the_driver_source_the_call_needs():
    gate = load_gate()
    with tempfile.TemporaryDirectory() as tmp:
        root = device(tmp, switch="y", builder=CALL,
                      board_text=board(remove=["kernel.pong_native_driver_source"]))
        status, why = gate.ufs_archive(str(root))
    assert status == "pending", status
    assert "PONG_NATIVE_DRIVER_SOURCE" in why, why
    assert "kernel.pong_native_driver_source" in why, why


@case
def the_defconfig_comes_from_the_selected_override():
    gate = load_gate()
    with tempfile.TemporaryDirectory() as tmp:
        root = device(tmp, switch="y", builder=CALL, configs=(("mondrian_defconfig",
                                                               "CONFIG_XNU_NATIVE_UFS=n\n"),))
        status, why = gate.ufs_archive(str(root))
        base = (root / "configs" / "mondrian_defconfig").read_text(encoding="utf-8")
    assert status == "ok", why
    assert "mondrian_ios27_defconfig" in why, why
    assert base.strip() == "CONFIG_XNU_NATIVE_UFS=n", base


@case
def the_defconfig_wins_over_a_fragment():
    gate = load_gate()
    with tempfile.TemporaryDirectory() as tmp:
        root = device(tmp, switch="n", builder=CALL,
                      board_text=board(fragments=("device:configs/ufs.config",)),
                      configs=(("ufs.config", "CONFIG_XNU_NATIVE_UFS=y\n"),))
        status, why = gate.ufs_archive(str(root))
    assert status == "pending" and "CONFIG_XNU_NATIVE_UFS=n" in why, why


@case
def an_override_under_another_name_falls_back_to_the_base():
    """The framework keys os_overrides by the profile name it resolved."""
    gate = load_gate()
    text = board().replace('os_profile = "ipados-27.0.1-24A446"',
                           'os_profile = "ios-27.0.1-24A446"')
    with tempfile.TemporaryDirectory() as tmp:
        root = device(tmp, switch="n", builder=CALL, board_text=text, defconfig="mondrian_defconfig")
        status, why = gate.ufs_archive(str(root))
    assert status == "pending", status
    assert "no os_overrides table has that name" in why, why


@case
def the_builder_comes_from_pick_xnu_builder():
    gate = load_gate()
    with tempfile.TemporaryDirectory() as tmp:
        root = device(tmp, switch="y", builder=CALL, builder_name="build-xnu-4k-baseline.sh",
                      board_text=board(profile="ipados-16.6.1-20G81", defconfig="mondrian_16_defconfig"),
                      defconfig="mondrian_16_defconfig",
                      scripts=(("build-xnu-generic.sh", LINK),))
        status, why = gate.ufs_archive(str(root))
    assert status == "ok", why
    assert "build-xnu-4k-baseline.sh" in why, why


@case
def an_unknown_switch_is_pending_even_when_the_builder_is_wired():
    with tempfile.TemporaryDirectory() as tmp:
        status, why = GATE_MODULE.ufs_archive(str(device(tmp, switch="", builder=CALL)))
    assert status == "pending" and "not proven enabled" in why, why


@case
def a_force_load_not_handed_to_make_is_pending():
    builder = CALL.replace('  EXTRA_MAKE_ARGS+=("LD_KERNEL_ARCHIVES=$KERNEL_EXTRA_ARCHIVES")\n', '')
    with tempfile.TemporaryDirectory() as tmp:
        status, why = GATE_MODULE.ufs_archive(str(device(tmp, switch="y", builder=builder)))
    assert status == "pending" and "handed to make" in why, why


@case
def a_producer_guard_with_an_unknown_test_is_pending():
    builder = CALL.replace('&& [ -n "$PONG_NATIVE_DRIVER_SOURCE" ]', '&& test -f "$UNPROVEN_FILE"')
    with tempfile.TemporaryDirectory() as tmp:
        status, why = GATE_MODULE.ufs_archive(str(device(tmp, switch="y", builder=builder)))
    assert status == "pending" and "producer guard" in why, why


@case
def checker_has_one_top_level_main_and_one_entry_guard():
    tree = ast.parse(GATE.read_text(encoding="utf-8"))
    mains = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main"]
    guards = [node for node in tree.body if isinstance(node, ast.If)
              and ast.unparse(node.test) == "__name__ == '__main__'"]
    assert len(mains) == len(guards) == 1, (len(mains), len(guards))


def main() -> int:
    failures = 0
    for fn in CASES:
        try:
            fn()
            print("ok   %s" % fn.__name__)
        except AssertionError as exc:
            failures += 1
            print("FAIL %s: %s" % (fn.__name__, exc))
        except Exception as exc:  # noqa: BLE001 - a broken gate is a failure, not a crash
            failures += 1
            print("FAIL %s: %s: %s" % (fn.__name__, type(exc).__name__, exc))
    print("TESTS OK %d case(s) (%d failure(s))" % (len(CASES) - failures, failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
