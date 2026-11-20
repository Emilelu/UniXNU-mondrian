#!/usr/bin/env python3
"""Fixtures for scripts/check-battmgr-wire.py.

The gate joins three materials that fail independently: the driver's fields[]
table, the decompilation table in 04-PROP-MAP.md, and (when a module is given)
the vendor .rodata maps. Each fixture breaks exactly one of them.
"""
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts" / "check-battmgr-wire.py"
FIXTURES = ROOT / "build" / ("battmgr-wire-tests-%d" % os.getpid())
VENDOR = pathlib.Path(os.environ.get("K60_VENDOR_KO", "/mnt/e/k60-work/firmware/qti_battery_charger_main_m81.ko"))
WINDOWS_VENDOR = pathlib.Path("E:/k60-work/firmware/qti_battery_charger_main_m81.ko")

HEADER = """enum {
K60BmStatus, K60BmCapacity,
K60BmFields
};
"""
DRIVER = """static const struct { uint8_t opcode, property; } fields[K60BmFields] = {
    {OP_BATTERY, 0}, {OP_BATTERY, 4}
};
"""
DOC = """## 8. table

| idx | value |
| --- | --- |
| 0 | 0x00 |
| 4 | 0x2e |
"""
MANIFEST = """schema = 1

[[field]]
name = "Status"
opcode = "OP_BATTERY"
index = 0
map_value = "0x00"
documented_at = "docs/research/charger/04-PROP-MAP.md:5"

[[field]]
name = "Capacity"
opcode = "OP_BATTERY"
index = 4
map_value = "0x2e"
documented_at = "docs/research/charger/04-PROP-MAP.md:6"
"""

failures = 0
checks = 0


def check(name, ok, detail=""):
    global failures, checks
    checks += 1
    if not ok:
        failures += 1
        print("FAIL %s%s" % (name, (": " + detail) if detail else ""))
    else:
        print("ok   %s" % name)


def build():
    if FIXTURES.exists():
        shutil.rmtree(FIXTURES, ignore_errors=True)
    (FIXTURES / "drivers/PongPower").mkdir(parents=True)
    (FIXTURES / "docs/research/charger").mkdir(parents=True)
    (FIXTURES / "drivers/PongPower/K60Battmgr.h").write_text(HEADER, encoding="utf-8", newline="\n")
    (FIXTURES / "drivers/PongPower/K60Battmgr.c").write_text(DRIVER, encoding="utf-8", newline="\n")
    (FIXTURES / "docs/research/charger/04-PROP-MAP.md").write_text(DOC, encoding="utf-8", newline="\n")
    (FIXTURES / "wire.toml").write_text(MANIFEST, encoding="utf-8", newline="\n")


def run(root, extra=(), manifest=None):
    path = manifest if manifest is not None else (root / "wire.toml")
    command = [sys.executable, str(TOOL), "--root", str(root), "--manifest", str(path), *extra]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", env=env)
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def patch(rel, old, new):
    path = FIXTURES / rel
    text = path.read_text(encoding="utf-8")
    assert old in text, "%s does not carry %r" % (rel, old)
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


def vendor_module():
    return VENDOR if VENDOR.exists() else (WINDOWS_VENDOR if WINDOWS_VENDOR.exists() else None)


def main():
    build()
    rc, out = run(FIXTURES)
    check("a consistent table passes", rc == 0, out.strip()[-200:])
    check("the missing module is a note, not a failure", "no vendor module given" in out)

    patch("drivers/PongPower/K60Battmgr.c", "{OP_BATTERY, 4}", "{OP_BATTERY, 5}")
    rc, out = run(FIXTURES)
    check("a moved driver index is refused", rc == 1 and "driver sends 5" in out, out.strip()[-200:])
    build()

    patch("wire.toml", 'map_value = "0x2e"', 'map_value = "0x2d"')
    rc, out = run(FIXTURES)
    check("a wrong map value is refused", rc == 1 and "says 0x2e" in out, out.strip()[-200:])
    build()

    patch("docs/research/charger/04-PROP-MAP.md", "| 4 | 0x2e |", "| 4 | 0x2f |")
    rc, out = run(FIXTURES)
    check("a drifted documentation row is refused", rc == 1 and "says 0x2f" in out, out.strip()[-200:])
    build()

    patch("drivers/PongPower/K60Battmgr.c", "{OP_BATTERY, 4}\n", "")
    rc, out = run(FIXTURES)
    check("a short driver table is unusable", rc == 2 and "1 pair(s) in fields[]" in out, out.strip()[-200:])
    build()

    patch("wire.toml", 'opcode = "OP_BATTERY"\nindex = 4', 'opcode = "OP_CAMERA"\nindex = 4')
    rc, out = run(FIXTURES)
    check("an unknown opcode is refused", rc == 1 and "unknown opcode" in out, out.strip()[-200:])
    build()

    (FIXTURES / "wire.toml").unlink()
    rc, out = run(FIXTURES)
    check("a missing manifest exits 2", rc == 2 and "cannot read the manifest" in out, out.strip()[-160:])
    build()

    rc, out = run(FIXTURES, ("--ko", str(FIXTURES / "nope.ko")))
    check("a missing module is a hard error", rc != 0, out.strip()[-160:])

    module = vendor_module()
    if module is None:
        print("note: no vendor module on this host; the .rodata case is skipped")
    else:
        patch("wire.toml", 'map_value = "0x2e"', 'map_value = "0x2d"')
        patch("docs/research/charger/04-PROP-MAP.md", "| 4 | 0x2e |", "| 4 | 0x2d |")
        rc, out = run(FIXTURES, ("--ko", str(module)))
        check("the module contradicts a table the sources agree on",
              rc == 1 and "the module has 0x2e" in out, out.strip()[-200:])
        build()

    # --against compares another checkout's fields[] table with ours, so a reorder in the
    # 27 copy is visible even though that copy's docs and vendor module are elsewhere.
    def make_copy(index4="4", extra=""):
        copy = FIXTURES / "copy27"
        if copy.exists():
            shutil.rmtree(copy, ignore_errors=True)
        (copy / "drivers/PongPower").mkdir(parents=True)
        header = HEADER
        driver = DRIVER.replace("{OP_BATTERY, 4}", "{OP_BATTERY, %s}" % index4)
        if extra:
            header = header.replace("K60BmFields", "%s, K60BmFields" % extra)
            driver = driver.replace("\n};", ", {OP_BATTERY, 9}\n};")
        (copy / "drivers/PongPower/K60Battmgr.h").write_text(header, encoding="utf-8", newline="\n")
        (copy / "drivers/PongPower/K60Battmgr.c").write_text(driver, encoding="utf-8", newline="\n")
        return copy

    copy = make_copy()
    rc, out = run(FIXTURES, ("--against", str(copy)))
    check("a copy that sends the same fields agrees",
          rc == 0 and "2 field(s) in the same order" in out, out.strip()[-200:])

    make_copy(index4="5")
    rc, out = run(FIXTURES, ("--against", str(FIXTURES / "copy27")))
    check("a copy whose wire index moved is refused",
          rc == 1 and "the wire index moved" in out, out.strip()[-200:])

    copy = make_copy()
    patch("copy27/drivers/PongPower/K60Battmgr.c", "{OP_BATTERY, 4}", "{OP_USB, 4}")
    rc, out = run(FIXTURES, ("--against", str(copy)))
    check("a copy whose opcode moved is refused",
          rc == 1 and "the opcode moved" in out, out.strip()[-200:])

    copy = make_copy()
    patch("copy27/drivers/PongPower/K60Battmgr.c", "{OP_BATTERY, 4}\n", "")
    patch("copy27/drivers/PongPower/K60Battmgr.h", "K60BmCapacity,", "")
    rc, out = run(FIXTURES, ("--against", str(copy)))
    check("a copy that does not send a field is refused",
          rc == 1 and "does not send Capacity at all" in out, out.strip()[-200:])

    make_copy(extra="K60BmExtra")
    rc, out = run(FIXTURES, ("--against", str(FIXTURES / "copy27")))
    check("a copy that sends a field we do not is refused",
          rc == 1 and "the copy sends Extra, we do not" in out, out.strip()[-200:])

    rc, out = run(FIXTURES, ("--against", str(FIXTURES / "no-such-tree")))
    check("an unreadable copy exits 2", rc == 2 and "cannot read" in out, out.strip()[-160:])

    for tree in (pathlib.Path("E:/hackios/xnekom-ios27"), pathlib.Path("/mnt/e/hackios/xnekom-ios27")):
        if tree.is_dir():
            rc, out = run(ROOT, ("--against", str(tree)))
            check("the 27 copy sends the same 19 fields", rc == 0 and "19 field(s)" in out, out.strip()[-200:])
            break
    else:
        print("note: no 27 checkout on this host; the live comparison is skipped")
    build()

    rc, out = run(ROOT, manifest=TOOL.parents[1] / "docs/research/charger/WIRE-PROPS.toml")
    check("the repository table passes", rc == 0, out.strip()[-300:])
    if module is not None:
        rc, out = run(ROOT, ("--ko", str(module)),
                      manifest=TOOL.parents[1] / "docs/research/charger/WIRE-PROPS.toml")
        check("the repository table matches the vendor module", rc == 0, out.strip()[-300:])
    else:
        print("note: the real module is not on this host; the live .rodata check is skipped")

    print("TESTS OK %d checks (%d failure(s))" % (checks, failures))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
