#!/usr/bin/env python3
"""Cover scripts/check-ios27-power-preflight.py with fixture trees.

Every case builds a throwaway device repo (carry manifest + one module) and a
throwaway 27 checkout, because the checker is only useful if each verdict can be
reproduced without the real iOS 27 tree.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts" / "check-ios27-power-preflight.py"

# read the lists out of the checker itself: a copy here would drift silently (P-259)
_SPEC = importlib.util.spec_from_file_location("ios27_preflight", TOOL)
_CHECKER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_CHECKER)
JUDGES = _CHECKER.JUDGES
TABLES = _CHECKER.TABLES
WORK = ROOT / "build" / "ios27-preflight-tests"

checks = 0
failures = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global checks, failures
    checks += 1
    if not ok:
        failures += 1
        print(f"FAIL {name}" + (f": {detail}" if detail else ""))


def sha(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


MODULE_C = "/* pure module */\nint k60_probe(void) { return 1; }\n"


def hunk(*rows: str) -> str:
    """A unified hunk carrying just these rows, with honest old/new counts."""
    old = sum(not row.startswith("+") for row in rows)
    new = sum(not row.startswith("-") for row in rows)
    return f"@@ -1,{old} +1,{new} @@\n" + "\n".join(rows) + "\n"


def sleep_patch(*rows: str) -> str:
    return "--- a/x\n+++ b/x\n" + hunk(*rows)


PONG = "+#if defined(PONG)"
SWITCH = "+#if K60_PLATFORM_SLEEP_REPORT"
SWITCH_DEF = ("+#ifndef K60_PLATFORM_SLEEP_REPORT",
              "+#define K60_PLATFORM_SLEEP_REPORT 1",
              "+#endif")
DECL = '+extern "C" void armcpu_sleep_report(void) __attribute__((weak));'
CALL = "+    k60_platform_sleep_report();"
END = "+#endif"
CLEAN_SLEEP_PATCH = sleep_patch(*SWITCH_DEF, SWITCH, DECL, END, SWITCH, CALL, END)


BATT_H = r"""enum {
K60BmStatus,
K60BmCapacity,
K60BmFields
};
"""
BATT_C = r"""static const struct { uint8_t opcode, property; } fields[K60BmFields] = {
    {OP_BATTERY, 0}, {OP_BATTERY, 4}
};
"""

def make_device(base: Path, *, contract: bool = False, console: bool = False,
                wire: bool = False) -> Path:
    device = base / "device"
    (device / "docs" / "research" / "power").mkdir(parents=True)
    (device / "drivers" / "PongPower").mkdir(parents=True)
    (device / "scripts").mkdir()
    (device / "drivers" / "PongPower" / "K60Probe.c").write_text(MODULE_C, encoding="utf-8", newline="\n")
    manifest = (
        "version = 1\n\n[[module]]\nname = \"K60Probe\"\nsuite = \"probe\"\n"
        "checks = 3\ntest = \"scripts/tests/test-k60-probe.c\"\nfiles = [\n"
        f'  {{ path = "drivers/PongPower/K60Probe.c", sha256 = "{sha(device / "drivers" / "PongPower" / "K60Probe.c")}" }},\n]\n'
    )
    (device / "docs" / "research" / "power" / "CARRY.toml").write_text(manifest, encoding="utf-8", newline="\n")
    for judge in JUDGES:
        (device / "scripts" / judge).write_text("# judge\n", encoding="utf-8", newline="\n")
    for rel in TABLES:
        if rel.name == "CARRY.toml":
            continue  # already written above with a real manifest
        (device / rel).parent.mkdir(parents=True, exist_ok=True)
        (device / rel).write_text("# table\n", encoding="utf-8", newline="\n")
    if console:
        shutil.copyfile(ROOT / "scripts" / "check-console-contract.py",
                        device / "scripts" / "check-console-contract.py")
    if wire:
        shutil.copyfile(ROOT / "scripts" / "check-battmgr-wire.py",
                        device / "scripts" / "check-battmgr-wire.py")
        (device / "drivers" / "PongPower" / "K60Battmgr.h").write_text(BATT_H, encoding="utf-8", newline="\n")
        (device / "drivers" / "PongPower" / "K60Battmgr.c").write_text(BATT_C, encoding="utf-8", newline="\n")
    if contract:
        shutil.copyfile(ROOT / "scripts" / "check-hw-contracts.py",
                        device / "scripts" / "check-hw-contracts.py")
        row = ('[[contract]]\nid = "probe-line"\nlane = "power"\nwhat = "the probe entry point"\n'
               'source = "drivers/PongPower/K60Probe.h:2"\nexpect = "K60_PROBE 1u"\n'
               'dependence = "none"\nios27 = "nothing"\n')
        (device / "docs" / "research" / "power" / "HW-CONTRACTS.toml").write_text(
            row, encoding="utf-8", newline="\n")
    return device


def make_tree(base: Path, *, console: str | None = None, module: bool = True,
              patch: str = CLEAN_SLEEP_PATCH, builder: str = "generic", judges: bool = True,
              tables: bool = True, picker: bool = True,
              contract_body: str | None = None,
              wire_body: str | None = None) -> Path:
    tree = base / "ios27"
    for rel in ("drivers/PongPower", "patches/xnu", "scripts"):
        (tree / rel).mkdir(parents=True)
    (tree / "board.toml").write_text('[machine]\nos_profile = "ios27"\n', encoding="utf-8", newline="\n")
    if module:
        (tree / "drivers" / "PongPower" / "K60Probe.c").write_text(
            MODULE_C, encoding="utf-8", newline="\n")
    (tree / "drivers" / "PongPower" / "K60Probe.h").write_text(
        contract_body or "/* contract */\n#define K60_PROBE 1u\n",
        encoding="utf-8", newline="\n")
    (tree / "patches" / "xnu" / "0629-k60-sleep-trace.patch").write_text(patch, encoding="utf-8", newline="\n")
    (tree / "patches" / "xnu" / "series").write_text("0629-k60-sleep-trace.patch\n", encoding="utf-8", newline="\n")
    for name in ("build-xnu-4k-baseline.sh", "build-xnu-generic.sh"):
        (tree / "scripts" / name).write_text("#!/bin/sh\n", encoding="utf-8", newline="\n")
    if picker:
        target = "build-xnu-generic.sh" if builder == "generic" else "build-xnu-4k-baseline.sh"
        (tree / "scripts" / "pick-xnu-builder.sh").write_text(
            f'#!/bin/sh\necho "$(dirname "$0")/{target}"\n', encoding="utf-8", newline="\n")
    if judges:
        for judge in JUDGES:
            (tree / "scripts" / judge).write_text("# judge\n", encoding="utf-8", newline="\n")
    if console is not None:
        # the real driver and the real judge, so the pair gate reads both sides in the tree
        (tree / "drivers" / "PongPower" / "K60Battery.cpp").write_text(
            console, encoding="utf-8", newline="\n")
        for judge in ("judge-battery.py", "judge-k60-battery-mirror.py",
                      "judge-k60-sleep-console.py", "judge-k60-mode1-console.py"):
            shutil.copyfile(ROOT / "scripts" / judge, tree / "scripts" / judge)
        # the real trace patch: the console pairs read the lines it prints, and a synthetic
        # patch would report every trace pair as a line nothing prints
        shutil.copyfile(ROOT / "patches" / "xnu" / "0629-k60-sleep-trace.patch",
                        tree / "patches" / "xnu" / "0629-k60-sleep-trace.patch")
    if wire_body is not None:
        (tree / "drivers" / "PongPower" / "K60Battmgr.h").write_text(BATT_H, encoding="utf-8", newline="\n")
        (tree / "drivers" / "PongPower" / "K60Battmgr.c").write_text(wire_body, encoding="utf-8", newline="\n")
    if tables:
        for rel in TABLES:
            (tree / rel).parent.mkdir(parents=True, exist_ok=True)
            (tree / rel).write_text("# table\n", encoding="utf-8", newline="\n")
    return tree


def run(device: Path, tree: Path) -> tuple[int, str]:
    env = dict(os.environ, K60_REPO=str(device), PYTHONIOENCODING="utf-8")
    done = subprocess.run([sys.executable, str(TOOL), "--tree", str(tree)],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, cwd=ROOT)
    return done.returncode, done.stdout + done.stderr


def case(name: str, *, expect_rc: int, expect: str = "", device_ok: bool = True,
         tree_exists: bool = True, contract: bool = False, console: bool = False,
         wire: bool = False, wire_body: str | None = None,
         console_body: str | None = None,
         **kwargs) -> None:
    base = WORK / name.replace(" ", "-")
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    device = make_device(base, contract=contract, console=console, wire=wire) if device_ok else base
    tree_kwargs = dict(kwargs)
    if console_body is not None:
        tree_kwargs["console"] = console_body
    if wire_body is not None:
        tree_kwargs["wire_body"] = wire_body
    tree = make_tree(base, **tree_kwargs) if tree_exists else base / "ios27-absent"
    rc, out = run(device, tree)
    check(name, rc == expect_rc, f"rc={rc} want {expect_rc}\n{out}")
    if expect:
        check(name + ": reason", expect in out, f"missing {expect!r}\n{out}")


WORK.mkdir(parents=True, exist_ok=True)

case("clean tree", expect_rc=0, expect="ios27-power-preflight: PASS")
case("contract row computed", expect_rc=0, expect="1 same in the 27 tree", contract=True)
case("contract drift reported", expect_rc=0,
     expect="the 27 line still has to change probe-line", contract=True,
     contract_body="/* contract */\n#define K60_PROBE 2u\n")
DRIVER = (ROOT / "drivers" / "PongPower" / "K60Battery.cpp").read_text(encoding="utf-8")
case("console pairs computed", expect_rc=0, expect="all match the drivers that print them",
     console=True, console_body=DRIVER)
case("console rename warned", expect_rc=0, expect="would no longer parse", console=True,
     console_body=DRIVER.replace("charge=%u/%umAh", "charge-now=%u/%umAh"))
case("wire table computed", expect_rc=0,
     expect="2 wire field(s) sent in the same order", wire=True, wire_body=BATT_C)
case("wire reorder warned", expect_rc=0, expect="the wire index moved", wire=True,
     wire_body=BATT_C.replace("{OP_BATTERY, 4}", "{OP_BATTERY, 5}"))
case("missing module", expect_rc=1, expect="missing drivers/PongPower/K60Probe.c", module=False)
blocked_sleep = "❌ sleep-report-guard"
clean_sleep = "✅ sleep-report-guard"
warn_sleep = "⚠️  sleep-report-guard"
case("pong report call", expect_rc=1, expect=blocked_sleep,
     patch=sleep_patch(PONG, CALL, END))
case("pong report declaration", expect_rc=1, expect=blocked_sleep,
     patch=sleep_patch(PONG, DECL, END))
case("macro plus stale declaration guard", expect_rc=1, expect=blocked_sleep,
     patch=sleep_patch(*SWITCH_DEF, "+#ifdef PONG", DECL, END, SWITCH, CALL, END))
case("macro plus stale call guard", expect_rc=1, expect=blocked_sleep,
     patch=sleep_patch(*SWITCH_DEF, SWITCH, DECL, END, PONG, CALL, END))
case("unrelated pong block", expect_rc=0, expect=clean_sleep,
     patch=sleep_patch(*SWITCH_DEF, PONG, "+    pong_trace();", END, SWITCH, CALL, END))
case("removed pong guard skipped", expect_rc=0, expect=clean_sleep,
     patch=sleep_patch(*SWITCH_DEF, "-#if defined(PONG)", SWITCH, DECL, END, SWITCH, CALL, END))
case("removed report call skipped", expect_rc=0, expect=clean_sleep,
     patch=sleep_patch(PONG, "-    armcpu_sleep_report();", "+    pong_trace();", END, *SWITCH_DEF))
case("report in negative pong branch", expect_rc=0, expect=warn_sleep,
     patch=sleep_patch(PONG, "+    pong_trace();", "+#else", CALL, END))
case("report in positive pong elif", expect_rc=1, expect=blocked_sleep,
     patch=sleep_patch("+#if OTHER_BOARD", "+    other_trace();", "+#elif defined(PONG)", CALL, END))
case("separate hunks stay separate", expect_rc=0, expect=clean_sleep,
     patch="--- a/x\n+++ b/x\n" + hunk(PONG, "+    pong_trace();")
           + hunk(*SWITCH_DEF, SWITCH, CALL, END))
case("no driver macro", expect_rc=0, expect="keep the driver-level switch",
     patch=sleep_patch(CALL))
case("sixteen builder", expect_rc=1, expect="Unsupported CURRENT_MACHINE_CONFIG PONG", builder="pong")
case("no picker", expect_rc=1, expect="3cc8cbc9", picker=False)
case("missing judges", expect_rc=1, expect="judge-k60-handoff-console.py", judges=False)
case("missing tree", expect_rc=2, expect="is not a directory", tree_exists=False)
case("missing tables", expect_rc=1, expect="rewires against prose", tables=False)
case("no manifest", expect_rc=2, expect="no carry manifest", device_ok=False)

# A drifted module must be caught even when the file exists.
base = WORK / "drift"
if base.exists():
    shutil.rmtree(base)
base.mkdir(parents=True)
device = make_device(base)
tree = make_tree(base)
(tree / "drivers" / "PongPower" / "K60Probe.c").write_text("/* edited */\n", encoding="utf-8", newline="\n")
rc, out = run(device, tree)
check("drifted module", rc == 1 and "drifted drivers/PongPower/K60Probe.c" in out, out)

# A judge missing from both trees is a warning, not a blocker: the 27 tree may
# legitimately not carry a judge that does not exist yet on the 16 line.
base = WORK / "warn-only"
if base.exists():
    shutil.rmtree(base)
base.mkdir(parents=True)
device = make_device(base)
tree = make_tree(base, judges=False)
(device / "scripts" / "judge-k60-sleep-console.py").unlink()
rc, out = run(device, tree)
check("absent judge warns", rc == 0 and "⚠" in out, out)

print(f"TESTS OK {checks} checks ({failures} failure(s))" if not failures
      else f"TESTS OK {checks} checks ({failures} failure(s))")
sys.exit(1 if failures else 0)
