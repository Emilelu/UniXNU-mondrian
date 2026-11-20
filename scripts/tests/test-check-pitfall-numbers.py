#!/usr/bin/env python3
"""Fixtures for scripts/check-pitfall-numbers.py.

The check exists because a human handed out the same number three times in one
day (2026-11-20: P-260/261/262 on this branch were main's P-260/261/262 too).
Each case here is one of the shapes that made that invisible.
"""

import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts/check-pitfall-numbers.py"
spec = importlib.util.spec_from_file_location("pitfall_numbers", TOOL)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

checks = 0
failures = 0


def check(label, condition):
    global checks, failures
    checks += 1
    if condition:
        print("  ok   " + label)
    else:
        failures += 1
        print("  FAIL " + label)


PITFALLS = "# P-01 one\n\n## P-274 - the judge exit table\n\nbody\n"
RULES = '[[rule]]\nid = "P-274"\nsource = "docs/engineering/PITFALLS.md:P-274"\n'


def tree(pitfalls=PITFALLS, rules=RULES):
    base = Path(tempfile.mkdtemp(prefix="pitfall-numbers-"))
    (base / "docs/engineering").mkdir(parents=True)
    (base / module.PITFALLS).write_text(pitfalls, encoding="utf-8")
    (base / module.RULES).write_text(rules, encoding="utf-8")
    return base


def verdict(root, against=None):
    return module.verify(root, against)


def main():
    clean = tree()
    check("a clean table verifies", verdict(clean) == [])

    bare = tree(pitfalls="## P-212\n\nthe title lives on the next line\n\n## P-213 - short\n")
    rows = module.headings((bare / module.PITFALLS).read_text(encoding="utf-8"))
    check("a bare heading takes its title from the next line",
          ("P-212", "the title lives on the next line", 2) in rows)
    check("the same number is not re-read as a shorter one",
          all(number != "P-21" for number, _title, _level in rows))
    check("a one-line heading keeps its own title",
          ("P-213", "short", 2) in rows)

    dup = tree(pitfalls="## P-274 - one\n\n## P-274 - two\n")
    problems = verdict(dup)
    check("one number with two titles is refused",
          any("names two different pitfalls" in p for p in problems))
    check("the message names both titles",
          any("one" in p and "two" in p for p in problems))

    cont = tree(pitfalls="## P-168 - a pitfall\n\n### P-168 追加实测（2026-11-13）\n",
                rules=RULES.replace("P-274", "P-168"))
    check("a 追加实测 continuation of the same id is allowed",
          not any("names two different" in p for p in verdict(cont)))

    deep = tree(pitfalls="## P-168 - a pitfall\n\n#### P-168 a deeper note\n",
                rules=RULES.replace("P-274", "P-168"))
    check("a deeper heading repeating the id is a note, not a second pitfall",
          verdict(deep) == [])

    story = tree(pitfalls="## P-274 - one\n\n## P-274 the other story\n")
    check("two stories at the same depth are refused",
          any("names two different pitfalls" in p for p in verdict(story)))

    orphan = tree(rules='[[rule]]\nid = "P-099"\nsource = "docs/engineering/PITFALLS.md:P-099"\n')
    problems = verdict(orphan)
    check("a RULES id with no section is refused",
          any("registers P-099" in p for p in problems))
    check("and so is its source line",
          any("points at docs/engineering/PITFALLS.md:P-099" in p for p in problems))

    half = tree(rules='[[rule]]\nid = "P-274"\nsource = "docs/engineering/PITFALLS.md:P-275"\n')
    problems = verdict(half)
    check("a source pointing at a missing section is refused",
          any("P-275" in p for p in problems))
    check("while the registered id itself is accepted",
          not any("registers P-274" in p for p in problems))

    empty = tree(pitfalls="# nothing here\n\nno headings at all\n", rules="")
    quiet = tree(rules="")
    problems = verdict(empty)
    check("a file with no pitfall heading refuses to pass vacuously",
          any("pass vacuously" in p for p in problems))
    check("and a rules file with no id is refused too",
          any("registers no rule id" in p for p in verdict(quiet)))

    missing = tree()
    (missing / module.PITFALLS).unlink()
    check("a missing PITFALLS.md is reported, not crashed on",
          any("cannot read" in p for p in verdict(missing)))

    other = Path(tempfile.mkdtemp(prefix="pitfall-main-")) / "PITFALLS.md"
    other.write_text("## P-274 - the other tree's own idea\n", encoding="utf-8")
    problems = verdict(clean, other)
    check("a number main already used for another story is refused",
          any("is a different pitfall on the other tree" in p for p in problems))
    check("and the message says to renumber",
          any("renumber before merging" in p for p in problems))

    same = Path(tempfile.mkdtemp(prefix="pitfall-same-")) / "PITFALLS.md"
    same.write_text(PITFALLS, encoding="utf-8")
    check("the same story on both trees agrees", verdict(clean, same) == [])
    same.write_text(PITFALLS + "\n## P-274 更正：clarify the wording\n", encoding="utf-8")
    check("an addendum on the other tree does not replace the original title", verdict(clean, same) == [])
    local_cont = tree(pitfalls=PITFALLS + "\n### P-274 追加实测: another run\n")
    check("a local addendum is not compared as a separate story", verdict(local_cont, same) == [])
    same.write_text(PITFALLS + "\n### P-274 another pitfall\n", encoding="utf-8")
    check("a duplicate on the other tree is not hidden by depth",
          any("names two different pitfalls" in p for p in verdict(clean, same)))
    same.write_text("# This is not a pitfall list\n", encoding="utf-8")
    check("an empty comparison is not reported as collision-free",
          any("pass vacuously" in p for p in verdict(clean, same)))

    run = subprocess.run([sys.executable, str(TOOL), "--root", str(clean)],
                         capture_output=True, text=True, encoding="utf-8", errors="replace",
                         env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    check("the CLI exits 0 on a clean tree", run.returncode == 0)
    check("and prints the highest number", "highest P-274" in run.stdout)
    run = subprocess.run([sys.executable, str(TOOL), "--root", str(dup)],
                         capture_output=True, text=True, encoding="utf-8", errors="replace",
                         env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    check("the CLI exits 1 on a duplicate", run.returncode == 1)

    check("this checkout has no duplicate and no orphan", verdict(ROOT) == [])

    if failures:
        print("pitfall-numbers TESTS FAILED %d of %d checks" % (failures, checks))
    else:
        print("pitfall-numbers TESTS OK %d checks" % checks)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
