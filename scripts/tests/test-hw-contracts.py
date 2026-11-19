#!/usr/bin/env python3
"""Fixture tests for scripts/check-hw-contracts.py.

The gate exists so a document cannot keep pointing at a constant that moved.
These cases prove it refuses a moved constant, a missing file, an out-of-range
line, a duplicate id and an uncovered lane - the five ways the real manifest can
rot - and that a healthy row passes with nothing but exit 0.
"""
from __future__ import annotations

import importlib.util
import pathlib
import shutil
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
WORK = REPO / "build" / f"hw-contract-tests-{__import__('os').getpid()}"
failures = 0
checks = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global failures, checks
    checks += 1
    if condition:
        print(f"ok   {name}")
    else:
        failures += 1
        print(f"FAIL {name}{': ' + detail if detail else ''}")


def load():
    spec = importlib.util.spec_from_file_location("check_hw_contracts", REPO / "scripts" / "check-hw-contracts.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROW = """
[[contract]]
id = "{id}"
lane = "{lane}"
what = "a number"
source = "{source}"
expect = "{expect}"
dependence = "{dependence}"
ios27 = "{ios27}"
"""


def build(root: pathlib.Path, rows: str, body: str = "#define X 1u\n",
          extra: dict[str, str] | None = None) -> pathlib.Path:
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    (root / "drv").mkdir(parents=True)
    (root / "drv" / "a.h").write_text(body, encoding="utf-8", newline="\n")
    for name, text in (extra or {}).items():
        target = root / "drv" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    manifest = root / "docs" / "research" / "power" / "HW-CONTRACTS.toml"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(rows, encoding="utf-8", newline="\n")
    return manifest


def row(**kw) -> str:
    base = dict(id="x", lane="power", source="drv/a.h:1", expect="X 1u",
                dependence="none", ios27="nothing")
    base.update(kw)
    return ROW.format(**base)


def main() -> int:
    module = load()
    if WORK.exists():
        shutil.rmtree(WORK, ignore_errors=True)

    healthy = "".join(row(id=f"g{i}", lane=lane) for i, lane in enumerate(sorted(module.LANES)))
    good = build(WORK / "good", healthy)
    check("a healthy manifest verifies", module.verify(WORK / "good", good) == [], str(module.verify(WORK / "good", good)))

    absent = build(WORK / "absent", row(source="drv/missing.h:1"))
    problems = module.verify(WORK / "absent", absent)
    check("a missing source file is refused", any("does not exist" in p for p in problems), str(problems))

    far = build(WORK / "far", row(source="drv/a.h:9"))
    problems = module.verify(WORK / "far", far)
    check("an out-of-range line is refused", any("cites 9" in p for p in problems), str(problems))

    moved = build(WORK / "moved", row(expect="X 2u"))
    problems = module.verify(WORK / "moved", moved)
    check("a constant that moved is refused", any("does not contain" in p for p in problems), str(problems))

    duplicated = build(WORK / "dup", row() + row())
    problems = module.verify(WORK / "dup", duplicated)
    check("a duplicate id is refused", any("duplicate id" in p for p in problems), str(problems))

    bad_dep = build(WORK / "dep", row(dependence="sometimes"))
    problems = module.verify(WORK / "dep", bad_dep)
    check("an unknown dependence is refused", any("dependence" in p for p in problems), str(problems))

    empty_ios27 = build(WORK / "empty", row(ios27=""))
    problems = module.verify(WORK / "empty", empty_ios27)
    check("an empty ios27 action is refused", any("ios27 is empty" in p for p in problems), str(problems))

    one_lane = build(WORK / "lane", row())
    problems = module.verify(WORK / "lane", one_lane)
    check("an uncovered lane is refused", any("no row covers the" in p for p in problems), str(problems))

    rows = "".join(row(id=f"c{i}", lane=lane) for i, lane in enumerate(sorted(module.LANES)))
    whole = build(WORK / "whole", rows)
    check("all five lanes satisfied verifies", module.verify(WORK / "whole", whole) == [], str(module.verify(WORK / "whole", whole)))

    missing = WORK / "nope.toml"
    problems = module.verify(WORK / "good", missing)
    check("a missing manifest is reported", problems and "missing" in problems[0], str(problems))

    broken = WORK / "broken.toml"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_text("[[contract]\n", encoding="utf-8", newline="\n")
    problems = module.verify(WORK / "good", broken)
    check("an unparseable manifest is reported", problems and "does not parse" in problems[0], str(problems))

    def five(mirror: str, extra: dict[str, str] | None = None) -> pathlib.Path:
        rows = "".join(row(id=f"m{i}", lane=lane) for i, lane in enumerate(sorted(module.LANES)))
        rows += ROW.format(id="mirrored", lane="power", source="drv/a.h:1", expect="X 1u",
                           dependence="none", ios27="nothing") + f'mirror = "{mirror}"\n'
        return build(WORK / "mirror", rows, extra=extra)

    ok = five("drv/b.h:1", {"b.h": "#define X 1u\n"})
    problems = module.verify(WORK / "mirror", ok)
    check("a satisfied mirror verifies", problems == [], str(problems))

    drifted = five("drv/b.h:1", {"b.h": "#define X 2u\n"})
    problems = module.verify(WORK / "mirror", drifted)
    check("a mirror that drifted is refused", any("the second copy drifted" in p for p in problems), str(problems))

    absent_mirror = five("drv/c.h:1")
    problems = module.verify(WORK / "mirror", absent_mirror)
    check("a missing mirror file is refused", any("mirror drv/c.h does not exist" in p for p in problems), str(problems))

    shapeless = five("drv/b.h")
    problems = module.verify(WORK / "mirror", shapeless)
    check("a mirror without a line is refused", any("is not path:line" in p for p in problems), str(problems))

    real = REPO / "docs" / "research" / "power" / "HW-CONTRACTS.toml"
    if real.is_file():
        problems = module.verify(REPO, real)
        check("the repository manifest verifies", problems == [], str(problems[:3]))
        problems = module.checklist_problems(REPO, real)
        check("the generated checklist matches its table", problems == [], str(problems))
        stale = build(WORK / "stale", healthy)
        (WORK / "stale" / module.CHECKLIST).parent.mkdir(parents=True, exist_ok=True)
        (WORK / "stale" / module.CHECKLIST).write_text("hand edited\n", encoding="utf-8", newline="\n")
        problems = module.checklist_problems(WORK / "stale", stale)
        check("a hand-edited checklist is refused", any("is stale" in p for p in problems), str(problems))
        problems = module.checklist_problems(WORK / "good", good)
        check("a missing checklist is reported", any("is missing" in p for p in problems), str(problems))

    print()
    if failures:
        print(f"TESTS FAILED {failures} of {checks} checks")
        return 1
    print(f"TESTS OK {checks} checks (0 failure(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
