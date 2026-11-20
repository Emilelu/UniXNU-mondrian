#!/usr/bin/env python3
"""Fixture tests for scripts/check-lane-conformance.py.

The gate exists so the per-lane table cannot quote a sentence the page never
carries, cite evidence that is not there, claim "verified" without naming the
line in that evidence which proves it, sit at "partial" without saying why, or
re-use one page sentence in two rows of the same lane.
These cases prove each of those refusals plus the healthy path, and that the
repository table itself still verifies against the page copy.
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import shutil
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
WORK = REPO / "build" / ("lane-conformance-tests-%d" % os.getpid())
checks = 0
failures = 0

PAGE = """# 电源

## 1. 确认目标接口

一句要求甲。
一句要求丁。
一句要求戊。

## 2. {#dsp} 实现 DSP 传输

一句要求乙。

## 3. {#battery} 实现电池状态上报

一句要求丙。
"""

ROW = """
[[row]]
id = "{id}"
lane = "{lane}"
section = "{section}"
anchor = "{anchor}"
requirement = "{requirement}"
evidence = "{evidence}"
evidence_line = "{evidence_line}"
status = "{status}"
why = "{why}"
"""


def check(name, condition, detail=""):
    global checks, failures
    checks += 1
    if condition:
        print("ok   %s" % name)
    else:
        failures += 1
        print("FAIL %s%s" % (name, ": " + detail if detail else ""))


def load():
    spec = importlib.util.spec_from_file_location(
        "check_lane_conformance", REPO / "scripts" / "check-lane-conformance.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def row(**kw):
    base = dict(id="x", lane="power", section="1", anchor="", requirement="一句要求甲。",
                evidence="drv/evidence.c", evidence_line="int x; /* fixture proof */",
                status="verified", why="")
    base.update(kw)
    return ROW.format(**base)


def build(name, rows, page=PAGE, with_evidence=True):
    root = WORK / name
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    page_dir = root / "page"
    page_dir.mkdir(parents=True)
    (page_dir / "power.md").write_text(page, encoding="utf-8", newline="")
    if with_evidence:
        target = root / "drv" / "evidence.c"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("int x; /* fixture proof */" + chr(10), encoding="utf-8", newline="")
    table = root / "table.toml"
    header = 'page_root = "%s"' % str(page_dir).replace("\\", "/") + chr(10) + 'page = "power.md"' + chr(10)
    table.write_text(header + rows, encoding="utf-8", newline="")
    return root, table


def lanes(extra="", **kw):
    sentences = ("一句要求甲。", "一句要求乙。", "一句要求丙。", "一句要求丁。", "一句要求戊。")
    rows = []
    for index, lane in enumerate(("adsp", "battery", "charger", "thermal", "power")):
        values = {"requirement": sentences[index]}
        values.update(kw)
        rows.append(row(id="r%d" % index, lane=lane, **values))
    return "".join(rows) + extra


def main():
    module = load()
    if WORK.exists():
        shutil.rmtree(WORK, ignore_errors=True)

    root, table = build("good", lanes())
    judged, problems = module.verify(root, table)
    check("a healthy table verifies", problems == [], str(problems))
    check("every row is judged", len(judged) == 5, str(len(judged)))
    rendered = module.render(judged)
    check("the render names the five rows", "合计 5 行" in rendered, rendered[:80])

    root, table = build("quote", lanes(row(lane="power", requirement="页面上没有这句。")))
    problems = module.verify(root, table)[1]
    check("a quote the page does not carry is refused",
          any("the page does not carry" in p for p in problems), str(problems))

    root, table = build("section", lanes(row(lane="power", section="9")))
    problems = module.verify(root, table)[1]
    check("a section the page does not have is refused",
          any("the page has no section" in p for p in problems), str(problems))

    root, table = build("anchor", lanes(row(lane="power", section="2", anchor="#dsp",
                                          requirement="一句要求乙。")))
    judged, problems = module.verify(root, table)
    check("an anchor the page carries verifies", problems == [], str(problems))

    root, table = build("noanchor", lanes(row(lane="power", section="2", anchor="#nope",
                                             requirement="一句要求乙。")))
    problems = module.verify(root, table)[1]
    check("an anchor the page does not carry is refused",
          any("the page has no anchor" in p for p in problems), str(problems))

    root, table = build("evidence", lanes(row(lane="power", evidence="drv/missing.c")))
    problems = module.verify(root, table)[1]
    check("missing evidence is refused",
          any("does not exist" in p for p in problems), str(problems))

    root, table = build("external", lanes(row(lane="power", evidence="external:E:/somewhere/x.bin",
                                                 status="partial", why="外部证据", evidence_line="")))
    problems = module.verify(root, table)[1]
    check("an external partial citation is not opened", problems == [], str(problems))

    root, table = build("external-verified", lanes(row(lane="power",
                                                       evidence="external:E:/somewhere/x.bin")))
    problems = module.verify(root, table)[1]
    check("a verified row cannot hide behind an external citation",
          any("external citation" in p for p in problems), str(problems))

    root, table = build("noproof", lanes(row(lane="power", evidence_line="")))
    problems = module.verify(root, table)[1]
    check("a verified row without an evidence line is refused",
          any("must name the line" in p for p in problems), str(problems))

    root, table = build("wrongproof", lanes(row(lane="power", evidence_line="int y; /* fixture proof */")))
    problems = module.verify(root, table)[1]
    check("an evidence line the file does not carry is refused",
          any("does not contain" in p for p in problems), str(problems))

    root, table = build("shortproof", lanes(row(lane="power", evidence_line="x")))
    problems = module.verify(root, table)[1]
    check("an evidence line too short to identify anything is refused",
          any("too short" in p for p in problems), str(problems))

    partial = row(id="p", lane="power", status="partial", why="只做了一半", evidence_line="")
    root, table = build("partial-noproof", lanes(extra=partial))
    problems = module.verify(root, table)[1]
    check("a partial row may omit the evidence line when it says why",
          problems == [], str(problems))

    root, table = build("why", lanes(row(lane="power", status="partial")))
    problems = module.verify(root, table)[1]
    check("a partial row without a why is refused",
          any("needs a why" in p for p in problems), str(problems))

    root, table = build("status", lanes(row(lane="power", status="mostly")))
    problems = module.verify(root, table)[1]
    check("an unknown status is refused",
          any("not one of" in p for p in problems), str(problems))

    root, table = build("dupid", lanes() + row(id="r0", lane="power"))
    problems = module.verify(root, table)[1]
    check("a duplicate id is refused", any("duplicate id" in p for p in problems), str(problems))

    root, table = build("dupreq", lanes() + row(id="dupe", lane="power", requirement="一句要求戊。"))
    problems = module.verify(root, table)[1]
    check("a second row in the same lane quoting the same sentence is refused",
          any("already quoted" in p for p in problems), str(problems))

    root, table = build("thin", row(id="r0", lane="power"))
    problems = module.verify(root, table)[1]
    check("a lane with no row is refused",
          any("has no row" in p for p in problems), str(problems))

    root, table = build("nopage", lanes(), page="")
    (root / "page" / "power.md").unlink()
    problems = module.verify(root, table)[1]
    check("a missing page copy is refused",
          any("is not present on this host" in p for p in problems), str(problems))

    real = REPO / "docs" / "research" / "power" / "LANE-CONFORMANCE.toml"
    if real.is_file():
        judged, problems = module.verify(REPO, real)
        check("the repository table verifies", problems == [], str(problems[:3]))
        generated = REPO / "docs" / "research" / "power" / "LANE-CONFORMANCE.md"
        check("the generated summary is committed",
              generated.is_file() and module.render(judged) == generated.read_text(encoding="utf-8"),
              "docs/research/power/LANE-CONFORMANCE.md is stale; run --render")

    print()
    if failures:
        print("TESTS FAILED %d of %d checks" % (failures, checks))
        return 1
    print("TESTS OK %d checks (0 failure(s))" % checks)
    return 0


if __name__ == "__main__":
    sys.exit(main())
