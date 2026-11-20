#!/usr/bin/env python3
"""Exercise scripts/check-prop-numbers.py against synthetic tables.

The gate is only worth having if it refuses the shapes that make a comparison
table useless: a row that claims "same" for a file nobody can open, a
"differs-known" with no owner, a token that is not actually on the cited line,
and a wire table that disagrees with itself. Each of those is a case here.
"""
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check-prop-numbers.py"
WORK = ROOT / "build" / ("prop-numbers-tests-%d" % os.getpid())
CASES = []


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def run(table, root, extra=()):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, str(CHECKER), "--root", str(root),
                           "--table", str(table), *extra],
                          cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=300)


def expect(name, result, expect_rc, expect=(), forbid=()):
    text = result.stdout + result.stderr
    problems = []
    if result.returncode != expect_rc:
        problems.append("rc %d != %d" % (result.returncode, expect_rc))
    for needle in expect:
        if needle not in text:
            problems.append("missing %r" % needle)
    for needle in forbid:
        if needle in text:
            problems.append("unexpected %r" % needle)
    if problems:
        print("FAIL %s: %s\n%s" % (name, "; ".join(problems), text[-1500:]))
        return 1
    return 0


def row(label, kind="key", value="kFooKey", value27=None, verdict="same", at16=2,
        at27=2, who="", left="a.c", right="b.c"):
    return ["[[row]]",
            'id = "%s"' % label,
            'kind = "%s"' % kind,
            'what = "%s symbol"' % label,
            'side16 = { value = "%s", source = "%s:%d" }' % (value, left, at16),
            'side27 = { value = "%s", source = "%s:%d" }' % (value27 or value, right, at27),
            'verdict = "%s"' % verdict,
            'who_changes = "%s"' % who]


def tree(rows, text16=None, text27=None):
    root = WORK / ("case-%02d" % len(CASES))
    root.mkdir(parents=True, exist_ok=True)
    plain = "line one\nstatic const char *kFooKey = \"x\";\n"
    write(root / "a.c", text16 or plain)
    write(root / "b.c", text27 or plain)
    table = root / "PROP-NUMBERS.toml"
    write(table, "\n".join(["schema = 1"] + ["\n".join(r) + "\n" for r in rows]))
    return table, root


def case(fn):
    CASES.append(fn)
    return fn


@case
def ok_same():
    table, root = tree([row("ok-same")])
    return expect("ok same", run(table, root), 0, ["prop-numbers: OK (1 row(s)", "same 1"])


@case
def missing_file():
    table, root = tree([row("gone", right="missing.c")])
    return expect("missing file", run(table, root), 1,
                  ["missing.c does not exist", "claimed same"])


@case
def unknown_pending():
    table, root = tree([row("pending", verdict="unknown", right="missing.c")])
    return expect("unknown pending", run(table, root), 0,
                  ["prop-numbers: OK", "1 pending"], ["FAIL"])


@case
def render_pending():
    table, root = tree([row("pending", verdict="unknown", right="missing.c")])
    out = root / "PROP-NUMBERS.md"
    result = run(table, root, ["--render", str(out)])
    problems = expect("render pending", result, 0, ["rendered"])
    text = out.read_text(encoding="utf-8") if out.exists() else ""
    for needle in ("待查", "pending", "missing.c does not exist"):
        if needle not in text:
            print("FAIL render pending: %r missing from the summary" % needle)
            problems += 1
    return problems


@case
def bad_verdict():
    table, root = tree([row("hedged", verdict="probably")])
    return expect("hedged verdict", run(table, root), 1,
                  ["is not one of same, differs-known, unknown"])


DRIFT27 = "line one" + chr(10) + 'static const char *kBarKey = "x";' + chr(10)

@case
def differs_no_owner():
    table, root = tree([row("drift", value27="kBarKey", verdict="differs-known")],
                       text27=DRIFT27)
    return expect("differs no owner", run(table, root), 1,
                  ["differs-known without who_changes"])


@case
def differs_owner():
    table, root = tree([row("drift", value27="kBarKey", verdict="differs-known",
                            who="27 line")], text27=DRIFT27)
    return expect("differs owner", run(table, root), 0, ["differs-known 1"])


@case
def token_off_line():
    table, root = tree([row("moved", at16=1)])
    return expect("token off line", run(table, root), 1, ["does not carry 'kFooKey'"])


WIRE_SAME = "int x;\nfields[K60BmFields] = {\n    { 0x01, 0 },\n    { 0x02, 1 },\n};\n"
WIRE_OTHER = "int x;\nfields[K60BmFields] = {\n    { 0x01, 0 },\n    { 0x07, 1 },\n};\n"


@case
def wire_same():
    table, root = tree([row("wire", kind="wire-table", value="2 fields")],
                       text16=WIRE_SAME, text27=WIRE_SAME)
    return expect("wire same", run(table, root), 0, ["prop-numbers: OK"])


@case
def wire_drift():
    table, root = tree([row("wire", kind="wire-table", value="2 fields")],
                       text16=WIRE_SAME, text27=WIRE_OTHER)
    return expect("wire drift", run(table, root), 1, ["differ but the row says same"])


@case
def wire_drift_declared():
    table, root = tree([row("wire", kind="wire-table", value="2 fields",
                            verdict="differs-known", who="27 line")],
                       text16=WIRE_SAME, text27=WIRE_OTHER)
    return expect("wire drift declared", run(table, root), 0, ["differs-known 1"])


@case
def duplicate_id():
    table, root = tree([row("dup"), row("dup")])
    return expect("duplicate id", run(table, root), 1, ["duplicate id"])


@case
def empty_table():
    root = WORK / "empty"
    root.mkdir(parents=True, exist_ok=True)
    table = write(root / "PROP-NUMBERS.toml", "schema = 1\n")
    return expect("empty table", run(table, root), 1, ["carries no row"])


@case
def source_no_line():
    table, root = tree([row("noline")])
    write(table, table.read_text(encoding="utf-8").replace("a.c:2", "a.c"))
    return expect("source no line", run(table, root), 1, ["is not path:line"])


@case
def repository():
    table = ROOT / "docs" / "research" / "charger" / "PROP-NUMBERS.toml"
    result = run(table, ROOT)
    problems = expect("repository", result, 0, ["prop-numbers: OK (18 row(s)"])
    for word in ("probably", "maybe"):
        if word in result.stdout:
            problems += 1
            print("FAIL repository: hedged word %r in the output" % word)
    return problems


def main():
    failures = 0
    for fn in CASES:
        try:
            failures += fn() or 0
        except Exception as error:  # noqa: BLE001 - a raising case is a failure
            print("FAIL %s: raised %s: %s" % (fn.__name__, type(error).__name__, error))
            failures += 1
    shutil.rmtree(WORK, ignore_errors=True)
    if failures:
        print("TESTS FAILED: %d check(s) failed in %d case(s)" % (failures, len(CASES)))
        return 1
    print("TESTS OK %d cases (0 failure(s))" % len(CASES))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
