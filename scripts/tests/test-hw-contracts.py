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
import subprocess
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
{extra}
"""


def build(root: pathlib.Path, rows: str, body: str = "#define X 1u\n",
          extra: dict[str, str] | None = None, tree: dict[str, str] | None = None,
          tree27: bool = True) -> pathlib.Path:
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    (root / "drv").mkdir(parents=True)
    (root / "drv" / "a.h").write_text(body, encoding="utf-8", newline="\n")
    for name, text in (extra or {}).items():
        target = root / "drv" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    # The 27 copy is a real directory here, so a row's same27 claim is re-opened
    # exactly the way it is on the device tree (P-259: two copies drift).
    side = root / "tree27"
    side.mkdir(parents=True, exist_ok=True)
    (side / "drv").mkdir(parents=True, exist_ok=True)
    (side / "drv" / "a.h").write_text(body, encoding="utf-8", newline="\n")
    for name, text in (tree or {}).items():
        target = side / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    manifest = root / "docs" / "research" / "power" / "HW-CONTRACTS.toml"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    header = f"tree27 = \"{side.as_posix()}\"\n\n" if tree27 else ""
    manifest.write_text(header + rows, encoding="utf-8", newline="\n")
    return manifest


def row(**kw) -> str:
    return fmt(**kw)


class _Defaults(dict):
    def __missing__(self, key):
        return ""


def fmt(**kw) -> str:
    """One [[contract]] row with the same27 fields the gate now demands."""
    base = dict(id="x", lane="power", source="drv/a.h:1", expect="X 1u",
                dependence="none", ios27="nothing", extra="",
                same27="same", copy27="drv/a.h:1", why27="")
    base.update(kw)
    lines = ['same27 = "%s"' % base["same27"]]
    if base["copy27"]:
        lines.append('copy27 = "%s"' % base["copy27"])
    if base["why27"]:
        lines.append('why27 = "%s"' % base["why27"])
    if base["extra"]:
        lines.append(base["extra"])
    base["extra"] = "\n".join(lines)
    return ROW.format_map(_Defaults(base))

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
        rows += fmt(id="mirrored", lane="power", source="drv/a.h:1", expect="X 1u",
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

    def lanes_and(extra, name):
        rows = "".join(row(id=f"s{i}", lane=lane) for i, lane in enumerate(sorted(module.LANES)))
        return build(WORK / name, rows + extra)

    fw_row = fmt(id="fw", lane="power", source="drv/a.h:1", expect="X 1u",
                        dependence="firmware", ios27="nothing")

    bare = lanes_and(fw_row, "fw-bare")
    problems = module.verify(WORK / "fw-bare", bare)
    check("a firmware row without a second source is refused",
          any("no independent second source" in p for p in problems), str(problems))

    cited = lanes_and(fw_row + 'second = [{ source = "drv/b.h:1", expect = "X 1u" }]', "fw-ok")
    (WORK / "fw-ok" / "drv" / "b.h").write_text("#define X 1u", encoding="utf-8", newline="")
    problems = module.verify(WORK / "fw-ok", cited)
    check("a firmware row with a satisfied second source verifies", problems == [], str(problems))

    (WORK / "fw-ok" / "drv" / "b.h").write_text("#define X 2u", encoding="utf-8", newline="")
    problems = module.verify(WORK / "fw-ok", cited)
    check("a second source that drifted is refused",
          any("second source drv/b.h:1 does not contain" in p for p in problems), str(problems))

    blob_row = lanes_and(fw_row + 'second = [{ bytes = "drv/blob.bin", offset = 4, hex = "deadbeef" }]', "fw-bin")
    (WORK / "fw-bin" / "drv" / "blob.bin").write_bytes(b"\x00\x00\x00\x00\xde\xad\xbe\xef\x00")
    problems = module.verify(WORK / "fw-bin", blob_row)
    check("a byte-range second source verifies", problems == [], str(problems))

    (WORK / "fw-bin" / "drv" / "blob.bin").write_bytes(b"\x00\x00\x00\x00\xde\xad\xbe\xee\x00")
    problems = module.verify(WORK / "fw-bin", blob_row)
    check("a byte-range second source that moved is refused",
          any("the row records deadbeef" in p for p in problems), str(problems))

    thin = lanes_and(fw_row + 'second_unavailable = { tried = ["one"], why = "the vendor image is not here" }', "fw-thin")
    problems = module.verify(WORK / "fw-thin", thin)
    check("an unsupported row with one tried source is refused",
          any("at least two are required" in p for p in problems), str(problems))

    doc = lanes_and(fw_row + 'second_unavailable = { tried = ["the vendor image is not here", "grep of the two sibling trees returned nothing"], why = "the ladder lives in the vendor thermal-engine config, which is not in this workspace" }', "fw-doc")
    problems = module.verify(WORK / "fw-doc", doc)
    check("a documented absence satisfies a firmware row", problems == [], str(problems))

    both = lanes_and(fw_row + 'second = [{ source = "drv/a.h:1", expect = "X 1u" }]' + chr(10) +
                     'second_unavailable = { tried = ["a", "b"], why = "c" }', "fw-both")
    problems = module.verify(WORK / "fw-both", both)
    check("a row that both cites and disclaims is refused",
          any("mutually exclusive" in p for p in problems), str(problems))

    stray = lanes_and(fw_row + 'second = [{ source = "external:nope/x.h:1", expect = "X 1u" }]', "fw-root")
    problems = module.verify(WORK / "fw-root", stray)
    check("an undeclared external root is refused",
          any("external root 'nope'" in p for p in problems), str(problems))
    check("a windows path is translated for this host",
          str(module.hostpath("E:/k60-work/x")).replace("\\", "/").endswith("k60-work/x"),
          str(module.hostpath("E:/k60-work/x")))

    # The same27 claim is the one this gate was extended for: "27 is the same as 16"
    # is two copies of one fact, and the gate re-opens the copy instead of trusting it.
    drifted = build(WORK / "same-drift", row(), tree={"drv/a.h": "#define X 2u\n"})
    problems = module.verify(WORK / "same-drift", drifted)
    check("a same27 row whose 27 copy moved is refused",
          any("the copies drifted" in p for p in problems), str(problems))

    flipped = build(WORK / "same-flipped", row(same27="drift", why27="27 has no such line"))
    problems = module.verify(WORK / "same-flipped", flipped)
    check("a drift claim the 27 copy contradicts is refused",
          any("flip it to same" in p for p in problems), str(problems))

    silent = build(WORK / "same-silent", row(same27="unchecked"))
    problems = module.verify(WORK / "same-silent", silent)
    check("an unchecked row has to say why",
          any("needs why27" in p for p in problems), str(problems))

    honest = build(WORK / "same-honest", row(same27="unchecked", copy27="",
                                            why27="27 has no such file yet"))
    problems = module.verify(WORK / "same-honest", honest)
    check("a documented unchecked row passes",
          not [p for p in problems if "why27" in p or "same27" in p or "copy27" in p],
          str(problems))

    bare27 = build(WORK / "same-no-tree", row(), tree27=False)
    problems = module.verify(WORK / "same-no-tree", bare27)
    check("a same claim without tree27 is refused",
          any("needs tree27" in p for p in problems), str(problems))
    # P-276: a row can name the preflight verdict that backs it, but the name has to be
    # one the tool actually computes. A typo would otherwise read as "the preflight agrees".
    pf = build(WORK / "preflight-ok", row(extra='preflight = ["check_alpha"]'))
    tool = WORK / "preflight-ok" / "scripts" / "check-ios27-power-preflight.py"
    tool.parent.mkdir(parents=True, exist_ok=True)
    tool.write_text("def check_alpha():\n    return 'PASS', 'ok'\n", encoding="utf-8", newline="\n")
    problems = module.verify(WORK / "preflight-ok", pf)
    check("a row naming a real preflight verdict passes",
          not [p for p in problems if "preflight" in p], str(problems))

    missing = build(WORK / "preflight-gone", row(extra='preflight = ["check_alpha"]'))
    problems = module.verify(WORK / "preflight-gone", missing)
    check("a preflight claim with no tool is refused",
          any("is missing, so preflight check_alpha" in p for p in problems), str(problems))

    typo = build(WORK / "preflight-typo", row(extra='preflight = ["check_missing"]'))
    tools_dir = WORK / "preflight-typo" / "scripts"
    tools_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(tool, tools_dir / "check-ios27-power-preflight.py")
    problems = module.verify(WORK / "preflight-typo", typo)
    check("a row naming a preflight function that does not exist is refused",
          any("has no check_missing" in p for p in problems), str(problems))
    # --against opens the row's own path in the other tree, so the same27 column cannot
    # stay hand-written prose: the run has to agree with it, and a claim it contradicts
    # is red whether the claim is "same", "drift" or "unchecked".
    one = {"id": "x", "source": "drv/a.h:1", "expect": "X 1u", "same27": "same"}
    check("a computed row reports the text it found",
          module.computed27(one, WORK / "good") == ("same", "drv/a.h:1"),
          str(module.computed27(one, WORK / "good")))

    # A row whose 27 side is a different file/line must be computed there, not at our
    # source line: the two copies of one patch may sit at different offsets (P-259).
    (WORK / "copy27" / "drv").mkdir(parents=True, exist_ok=True)
    (WORK / "copy27" / "drv" / "c.h").write_text("/* a */\nX 1u\n", encoding="utf-8", newline="\n")
    copied = {"id": "x", "source": "drv/a.h:1", "expect": "X 1u", "same27": "same",
              "copy27": "drv/c.h:2"}
    check("computed27 opens the line copy27 names",
          module.computed27(copied, WORK / "copy27") == ("same", "drv/c.h:2"),
          str(module.computed27(copied, WORK / "copy27")))
    (WORK / "copy27" / "drv" / "c.h").write_text("/* a */\nX 2u\n", encoding="utf-8", newline="\n")
    check("computed27 reports drift at the copy27 line",
          module.computed27(copied, WORK / "copy27")[0] == "drift"
          and "drv/c.h:2 does not contain" in module.computed27(copied, WORK / "copy27")[1],
          str(module.computed27(copied, WORK / "copy27")))

    problems, report = module.against_problems({"contract": [one]}, WORK / "same-drift" / "tree27")
    check("a claim the other tree contradicts is refused",
          any("the tree says drift" in p for p in problems), str(problems))
    check("the computed verdict is printed for every row",
          any(line.startswith("drift") for line in report), str(report))

    gone = dict(one, same27="drift")
    problems, _ = module.against_problems({"contract": [gone]}, WORK / "no-such-tree")
    check("a drift claim on a file the tree lacks is refused",
          any("unchecked with a reason" in p for p in problems), str(problems))

    closed = dict(one, same27="unchecked")
    problems, _ = module.against_problems({"contract": [closed]}, WORK / "good")
    check("an unchecked claim the tree already satisfies is refused",
          any("say same" in p for p in problems), str(problems))

    moved = {"id": "x", "source": "drv/a.h:9", "expect": "X 1u", "same27": "unchecked"}
    verdict, detail = module.computed27(moved, WORK / "good")
    check("a row citing a line past the end is called moved",
          verdict == "moved" and "cites 9" in detail, f"{verdict} {detail}")

    cli = subprocess.run([sys.executable, str(REPO / "scripts" / "check-hw-contracts.py"),
                          "--against", str(WORK / "same-drift" / "tree27"),
                          "--manifest", str(drifted)],
                         capture_output=True, text=True, encoding="utf-8", errors="replace",
                         env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
    check("--against exits 1 and names the claim that disagrees",
          cli.returncode == 1 and "the tree says drift" in cli.stderr,
          f"rc {cli.returncode} {cli.stderr.strip()[-200:]}")

    # The work order turns the computed verdicts into something a lane can act on, and it
    # is generated for the same reason the checklist is: a hand-edited work order stops
    # matching the tree it describes (P-259).
    wo = build(WORK / "workorder", "".join([
        row(id="keep"),
        row(id="diff", source="drv/d.h:1", expect="X 1u", same27="drift", copy27="drv/d.h:1",
            why27="the 27 copy holds a placeholder instead of the macro",
            extra='where = "drv/d.h:1"\nwhy_here = "must stay before the tracepoint"'),
        row(id="gone", source="drv/b.h:1", expect="Y 2u", same27="unchecked", copy27="",
            why27="the file has not travelled yet"),
    ]), extra={"b.h": "#define Y 2u\n", "d.h": "#define X 1u\n"},
        tree={"drv/d.h": "/* placeholder */\n"})
    text = module.render_workorder(WORK / "workorder", wo)
    check("the work order shows a drifted row with our line and the 27 line",
          "### diff" in text and "#define X 1u" in text and "placeholder" in text,
          text[:300])
    check("the work order says where the line goes and why",
          "源码位置" in text and "drv/d.h:1" in text
          and "为什么放在这里" in text and "must stay before the tracepoint" in text,
          text[:300])
    check("the work order names a file the 27 tree lacks",
          "### gone" in text and "drv/b.h" in text, text[:300])
    check("the work order does not list rows the 27 copy already matches",
          "### keep" not in text, text[:300])

    target = WORK / "workorder" / module.WORKORDER
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")
    check("a work order that matches the tree is accepted",
          module.workorder_problems(WORK / "workorder", wo) == [],
          str(module.workorder_problems(WORK / "workorder", wo)))
    target.write_text("hand edited\n", encoding="utf-8", newline="\n")
    check("a hand-edited work order is refused",
          any("is stale" in problem for problem in module.workorder_problems(WORK / "workorder", wo)),
          str(module.workorder_problems(WORK / "workorder", wo)))
    check("a missing work order is reported",
          any("is missing" in problem for problem in module.workorder_problems(WORK / "good", good)),
          str(module.workorder_problems(WORK / "good", good)))
    no27 = build(WORK / "no27wo", row(), tree27=False)
    check("without a 27 tree the work order is not policed",
          module.workorder_problems(WORK / "no27wo", no27) == [],
          str(module.workorder_problems(WORK / "no27wo", no27)))

    written = WORK / "wo-cli" / "WO.md"
    cli = subprocess.run([sys.executable, str(REPO / "scripts" / "check-hw-contracts.py"),
                          "--workorder", str(written), "--manifest", str(wo)],
                         capture_output=True, text=True, encoding="utf-8", errors="replace",
                         env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
    check("--workorder writes the list it computed",
          cli.returncode == 0 and written.is_file()
          and "### diff" in written.read_text(encoding="utf-8"),
          f"rc {cli.returncode} {cli.stderr.strip()[-200:]}")

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
