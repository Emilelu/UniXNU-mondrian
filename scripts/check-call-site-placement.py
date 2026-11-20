#!/usr/bin/env python3
"""Check where the two probe calls sit relative to the Data-mount stage.

The probes must run after the Data mount is prepared and before the stage
reaches 3, because the baseband reads its EFS files as soon as it is powered.
--anchor-auto finds the line; this checks the result rather than the intent.

usage: check-call-site-placement.py --tree <xnu-work> [--stage 3] [--window 30]
                                  [--self-test]
"""

import argparse
import pathlib
import re
import sys
import tempfile

MODEM = "k60_modem_probe_from_handoff"
IPA = "k60_ipa_probe_from_handoff"
KERN_EXEC = pathlib.Path("bsd") / "kern" / "kern_exec.c"


def read_lines(tree, stage):
    path = pathlib.Path(tree) / KERN_EXEC
    if not path.is_file():
        return None, "no %s under %s" % (KERN_EXEC, tree)
    return path.read_text(errors="replace").splitlines(), None


def stage_line(lines, stage):
    pattern = re.compile(r"^\s*native_owner_data_stage\s*=\s*%d\s*;" % stage)
    return [i for i, line in enumerate(lines) if pattern.match(line)]


def split_hits(lines, name):
    """Separates call sites from declarations: a call has nothing but an optional
    (void) cast before the name, a declaration carries a type in front of it."""
    calls = []
    declarations = []
    pattern = re.compile(r"\b" + name + r"\s*\(([^)]*)\)\s*;")
    for index, line in enumerate(lines):
        match = pattern.search(line)
        if not match:
            continue
        prefix = line[:match.start()].strip()
        if prefix in ("", "(void)", "void"):
            calls.append(index)
        else:
            declarations.append(index)
    return calls, declarations


def inspect(tree, stage=3, window=30):
    lines, error = read_lines(tree, stage)
    if error:
        return [error], ""
    stages = stage_line(lines, stage)
    if len(stages) != 1:
        return ["native_owner_data_stage = %d appears %d times, need exactly one"
                % (stage, len(stages))], ""
    at = stages[0]
    problems = []
    seen = {}
    for name in (MODEM, IPA):
        hits, declarations = split_hits(lines, name)
        seen[name] = hits
        if len(hits) != 1:
            problems.append("%s has %d call site(s) and %d declaration(s), need one call"
                            % (name, len(hits), len(declarations)))
    if not problems:
        if seen[MODEM][0] > seen[IPA][0]:
            problems.append("%s is called after %s" % (MODEM, IPA))
        for name in (MODEM, IPA):
            gap = at - seen[name][0]
            if gap <= 0:
                problems.append("%s runs after the stage reaches %d" % (name, stage))
            elif gap > window:
                problems.append("%s is %d lines above the stage, window is %d"
                                % (name, gap, window))
        guards = [i for i in range(at) if "goto done;" in lines[i]]
        if guards:
            last = guards[-1]
            for name in (MODEM, IPA):
                if seen[name][0] < last:
                    problems.append("%s runs before the error guard above the stage" % name)
        else:
            return problems, "no error guard above the stage line"
    return problems, ""


def fixture(root, stage_lines, modem_offset, ipa_offset, guard=True):
    body = ["static int prepare(void) {", "  int error = 0;"]
    if guard:
        body.append("  if (error) goto done;")
    body.append("  /* filler */")
    body.append("  /* filler */")
    later = max(modem_offset, ipa_offset) + 4
    for offset in sorted((modem_offset, ipa_offset)):
        while len(body) < 4 + offset:
            body.append("  /* filler */")
        name = MODEM if offset == modem_offset else IPA
        body.append("  extern int %s(int);" % name)
        body.append("  %s(proc);" % name)
    while len(body) < 4 + later:
        body.append("  /* filler */")
    for line in stage_lines:
        body.append("  " + line)
    body.append("done:")
    body.append("  return error;")
    body.append("}")
    target = pathlib.Path(root) / KERN_EXEC
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(chr(10).join(body) + chr(10))
    return str(root)


def self_test():
    cases = []
    with tempfile.TemporaryDirectory(prefix="k60-placement-") as base:
        stage3 = ["native_owner_data_stage = 3;"]
        good = fixture(pathlib.Path(base, "good"), stage3, 2, 4)
        cases.append(("good", good, ""))
        swapped = fixture(pathlib.Path(base, "swapped"), stage3, 6, 2)
        cases.append(("swapped", swapped, "is called after"))
        double = fixture(pathlib.Path(base, "double"), stage3 + stage3, 2, 4)
        cases.append(("double", double, "appears 2 times"))
        order = fixture(pathlib.Path(base, "order"), stage3, 2, 4)
        text = (pathlib.Path(order) / KERN_EXEC).read_text()
        text = text.replace("  " + IPA + "(proc);", "  /* moved */")
        text = text.replace("done:", "  " + IPA + "(proc);" + chr(10) + "done:")
        (pathlib.Path(order) / KERN_EXEC).write_text(text)
        cases.append(("order", order, "runs after the stage reaches 3"))
        far = fixture(pathlib.Path(base, "far"), stage3, 2, 4)
        text = (pathlib.Path(far) / KERN_EXEC).read_text()
        lines = text.splitlines()
        at = [i for i, line in enumerate(lines) if line.strip() == "native_owner_data_stage = 3;"][0]
        lines = lines[:at] + ["  /* gap */"] * 40 + lines[at:]
        (pathlib.Path(far) / KERN_EXEC).write_text(chr(10).join(lines) + chr(10))
        cases.append(("far", far, "window is 30"))
        failed = 0
        for name, tree, needle in cases:
            problems, _ = inspect(tree)
            joined = " ".join(problems)
            if needle and needle not in joined:
                print("K60 PLACEMENT FAILED fixture %s: expected %r in %r"
                      % (name, needle, joined))
                failed += 1
            if not needle and problems:
                print("K60 PLACEMENT FAILED fixture %s: %s" % (name, joined))
                failed += 1
        if failed:
            return 1
    print("K60 PLACEMENT PASS stage line, both probes, order, window, guard")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree")
    ap.add_argument("--stage", type=int, default=3)
    ap.add_argument("--window", type=int, default=30)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not args.tree:
        print("usage: check-call-site-placement.py --tree <xnu-work> [--self-test]")
        return 2
    problems, note = inspect(args.tree, args.stage, args.window)
    if note:
        print("K60 PLACEMENT note %s" % note)
    if problems:
        for problem in problems:
            print("K60 PLACEMENT FAILED %s" % problem)
        return 1
    print("K60 PLACEMENT ok   both probes run after the guard and before stage %d"
          % args.stage)
    return 0


if __name__ == "__main__":
    sys.exit(main())
