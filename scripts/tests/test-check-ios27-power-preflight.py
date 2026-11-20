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


def make_device(base: Path) -> Path:
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
    return device


def make_tree(base: Path, *, module: bool = True, guard: bool = False,
              macro: bool = True, builder: str = "generic", judges: bool = True,
              tables: bool = True, picker: bool = True) -> Path:
    tree = base / "ios27"
    for rel in ("drivers/PongPower", "patches/xnu", "scripts"):
        (tree / rel).mkdir(parents=True)
    (tree / "board.toml").write_text('[machine]\nos_profile = "ios27"\n', encoding="utf-8", newline="\n")
    if module:
        (tree / "drivers" / "PongPower" / "K60Probe.c").write_text(MODULE_C, encoding="utf-8", newline="\n")
    patch = "--- a/x\n+++ b/x\n"
    if guard:
        patch += '@@ -1,0 +1,2 @@\n+#if defined(PONG)\n+    armcpu_sleep_report();\n'
    elif macro:
        body = ["+#ifndef K60_PLATFORM_SLEEP_REPORT", "+#define K60_PLATFORM_SLEEP_REPORT 1",
                "+#endif", "+#if K60_PLATFORM_SLEEP_REPORT", "+    k60_platform_sleep_report();",
                "+#endif"]
        patch += "@@ -1,0 +1,%d @@\n" % len(body) + "\n".join(body) + "\n"
    else:
        patch += '@@ -1,0 +1 @@\n+    k60_platform_sleep_report();\n'
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
         tree_exists: bool = True, **kwargs) -> None:
    base = WORK / name.replace(" ", "-")
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    device = make_device(base) if device_ok else base
    tree = make_tree(base, **kwargs) if tree_exists else base / "ios27-absent"
    rc, out = run(device, tree)
    check(name, rc == expect_rc, f"rc={rc} want {expect_rc}\n{out}")
    if expect:
        check(name + ": reason", expect in out, f"missing {expect!r}\n{out}")


WORK.mkdir(parents=True, exist_ok=True)

case("clean tree", expect_rc=0, expect="ios27-power-preflight: PASS")
case("missing module", expect_rc=1, expect="missing drivers/PongPower/K60Probe.c", module=False)
case("pong guard", expect_rc=1, expect="K60_PLATFORM_SLEEP_REPORT", guard=True)
case("no driver macro", expect_rc=0, expect="keep the driver-level switch", macro=False)
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
