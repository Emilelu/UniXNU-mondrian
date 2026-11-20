#!/usr/bin/env python3
"""Check the 16 -> 27 property table row by row, and render its summary.

docs/research/charger/PROP-NUMBERS.toml answers one question per row: does the
27 checkout carry the same property symbol / wire index we use on the 16 line?
Only three verdicts are allowed, because "probably" is what makes a table
useless:

  same           both sides open, the values taken from them are equal
  differs-known  they differ AND who_changes names who must move
  unknown        at least one side cannot be opened or read; the row is also
                 listed as PENDING so someone decides whether to dig

A row's source may point inside this repository, into the 27 checkout, or at
something that is neither (sheng, a build tree) - those carry an "external:"
prefix so a reader who cannot open them knows it is external evidence rather
than a stale citation (P-259).

Exit 0 every row judged and consistent, 1 a row is inconsistent with its
sources, 2 the table or a required input cannot be read.
"""
import argparse
import os
import pathlib
import re
import sys

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - python < 3.11
    tomllib = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
TABLE = ROOT / "docs" / "research" / "charger" / "PROP-NUMBERS.toml"
RENDER = ROOT / "docs" / "research" / "charger" / "PROP-NUMBERS.md"
VERDICTS = ("same", "differs-known", "unknown")
FIELDS = re.compile(r"fields\[K60BmFields\]\s*=\s*\{")

HEADER = """# 16 → 27 属性号对照（生成物）

由 `python3 scripts/check-prop-numbers.py --render` 生成，**不要手改**：改
`docs/research/charger/PROP-NUMBERS.toml`，门禁会在两者不一致时报 stale（P-259）。

三档结论只有 `same` / `differs-known` / `unknown`；`unknown` 的行同时进下面的待查清单。
"""


def read(path):
    return pathlib.Path(path).read_text(encoding="utf-8", errors="replace")


def hostpath(path):
    """Translate a Windows drive path for a POSIX host, and back again."""
    match = re.match(r"^([A-Za-z]):[\\/](.*)$", str(path))
    if match and os.name != "nt":
        return "/mnt/%s/%s" % (match.group(1).lower(), match.group(2))
    return str(path)


def tree_root(root, table, source):
    """Resolve a "27:" prefixed source against the 27 checkout recorded in the table."""
    base = str((table.get("tree27") or "")).strip()
    if not base:
        return None, "the table records no tree27 root for a 27: source"
    candidate = hostpath(base)
    if not pathlib.Path(candidate).is_dir():
        return None, "the 27 checkout %s is not present on this host" % base
    return pathlib.Path(candidate) / str(source)[len("27:"):].rpartition(":")[0], None


def resolve(root, table, source):
    """Return (path, line) or (None, reason). Honours external: and 27: prefixes."""
    text = str(source or "")
    external = text.startswith("external:")
    if external:
        text = text[len("external:"):]
    tree27 = text.startswith("27:")
    if tree27:
        base, error = tree_root(root, table, text)
        if base is None:
            return None, error
        line = text.rpartition(":")[2]
        try:
            number = int(line)
        except ValueError:
            return None, "source %r is not path:line" % source
        full = base
        if not full.is_file():
            return None, "%s does not exist in the 27 checkout" % (text[len("27:"):].rpartition(":")[0])
        rows = read(full).splitlines()
        if not 1 <= number <= len(rows):
            return None, "%s has %d line(s), the row cites %d" % (full.name, len(rows), number)
        return (full, number, rows[number - 1]), None
    path, _, line = text.rpartition(":")
    try:
        number = int(line)
    except ValueError:
        return None, "source %r is not path:line" % source
    target = pathlib.Path(path)
    if not target.is_absolute():
        target = pathlib.Path(root) / path
    if not target.is_file():
        return None, ("external source %s cannot be opened here" % path) if external \
            else ("%s does not exist" % path)
    rows = read(target).splitlines()
    if not 1 <= number <= len(rows):
        return None, "%s has %d line(s), the row cites %d" % (path, len(rows), number)
    return (target, number, rows[number - 1]), None


def wire_table(text):
    match = FIELDS.search(text)
    if not match:
        return None
    body = text[match.end():]
    body = body[: body.index("};")]
    pairs = []
    for chunk in body.split("{")[1:]:
        head = chunk.split("}")[0].strip()
        if head:
            opcode, index = [part.strip() for part in head.split(",")]
            pairs.append((opcode, int(index)))
    return pairs


def judge_row(root, table, row):
    """Return (verdict_actual, problems, pending_reason)."""
    label = row.get("id", "?")
    kind = row.get("kind")
    claimed = row.get("verdict")
    problems, pending = [], ""
    if claimed not in VERDICTS:
        problems.append("%s: verdict %r is not one of %s" % (label, claimed, ", ".join(VERDICTS)))
        return "unknown", problems, pending

    def side(name):
        entry = row.get(name) or {}
        resolved, error = resolve(root, table, entry.get("source"))
        if resolved is None:
            return None, entry.get("value"), error
        return resolved, entry.get("value"), None

    left, left_value, left_error = side("side16")
    right, right_value, right_error = side("side27")

    if kind == "wire-table":
        if left is None or right is None:
            pending = left_error or right_error or "a wire table cannot be read"
            return ("unknown" if claimed == "unknown" else claimed), \
                   ([] if claimed == "unknown" else
                    ["%s: claimed %s but %s" % (label, claimed, pending)]), pending
        first, second = wire_table(read(left[0])), wire_table(read(right[0]))
        if first is None or second is None:
            problems.append("%s: a cited line carries no fields[] table" % label)
            return claimed, problems, ""
        actual = "same" if first == second else "differs-known"
        if actual != claimed:
            problems.append("%s: the two tables %s but the row says %s"
                            % (label, "agree" if actual == "same" else "differ", claimed))
        if actual == "differs-known" and not row.get("who_changes"):
            problems.append("%s: differs-known without who_changes" % label)
        return actual, problems, ""

    if kind != "key":
        problems.append("%s: unknown kind %r" % (label, kind))
        return claimed, problems, ""

    if left is None or right is None:
        pending = left_error or right_error or ""
        if claimed != "unknown":
            problems.append("%s: claimed %s but %s" % (label, claimed, pending))
        return "unknown", problems, pending

    text16, text27 = left[2], right[2]
    token16, token27 = str(left_value or ""), str(right_value or "")
    if token16 and token16 not in text16:
        problems.append("%s: %s does not carry %r" % (label, row["side16"]["source"], token16))
    if token27 and token27 not in text27:
        problems.append("%s: %s does not carry %r" % (label, row["side27"]["source"], token27))
    agree = bool(token16) and token16 == token27 and token16 in text16 and token27 in text27
    actual = "same" if agree else "differs-known"
    if actual != claimed:
        problems.append("%s: sources say %s but the row says %s" % (label, actual, claimed))
    if actual == "differs-known" and not row.get("who_changes"):
        problems.append("%s: differs-known without who_changes" % label)
    return actual, problems, ""


def verify(root, table_path):
    try:
        table = tomllib.loads(read(table_path))
    except OSError as error:
        raise SystemExit("check-prop-numbers: cannot read the table: %s" % error)
    rows = table.get("row") or []
    problems, judged, pending_rows = [], [], []
    seen = set()
    for row in rows:
        label = row.get("id")
        if not label:
            problems.append("a row carries no id")
            continue
        if label in seen:
            problems.append("%s: duplicate id" % label)
        seen.add(label)
        verdict, row_problems, pending = judge_row(root, table, row)
        judged.append((label, row.get("what", ""), verdict, row))
        problems.extend(row_problems)
        if verdict == "unknown":
            pending_rows.append((label, pending or "no source could be read"))
    if not rows:
        problems.append("the table carries no row")
    return judged, pending_rows, problems


def render(judged, pending_rows):
    lines = [HEADER, "| id | 属性 | 16 侧 | 27 侧 | 结论 | 谁改 |", "| --- | --- | --- | --- | --- | --- |"]
    for label, what, verdict, row in judged:
        left = (row.get("side16") or {}).get("value", "")
        right = (row.get("side27") or {}).get("value", "")
        who = row.get("who_changes") or ("—" if verdict == "same" else "**未定**")
        lines.append("| `%s` | %s | `%s` | `%s` | %s | %s |"
                     % (label, what, left, right, verdict, who))
    lines.append("")
    lines.append("## 待查（verdict = unknown）")
    lines.append("")
    if pending_rows:
        for label, reason in pending_rows:
            lines.append("- `%s` — %s" % (label, reason))
    else:
        lines.append("- 无：每一行两侧都能打开并核对过。")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--table", default=str(TABLE))
    parser.add_argument("--render", nargs="?", const=str(RENDER), default=None,
                        help="rewrite the generated summary from the table")
    args = parser.parse_args(argv)
    try:
        judged, pending_rows, problems = verify(pathlib.Path(args.root), args.table)
    except SystemExit as error:
        print(error)
        return 2
    counts = {}
    for _, _, verdict, _ in judged:
        counts[verdict] = counts.get(verdict, 0) + 1
    if args.render:
        pathlib.Path(args.render).write_text(render(judged, pending_rows), encoding="utf-8", newline="\n")
        print("prop-numbers: rendered %s (%d row(s))" % (args.render, len(judged)))
    for problem in problems:
        print("FAIL %s" % problem)
    if problems:
        print("prop-numbers: FAIL (%d problem(s))" % len(problems))
        return 1
    print("prop-numbers: OK (%d row(s): %s; %d pending)"
          % (len(judged), ", ".join("%s %d" % (k, counts[k]) for k in VERDICTS if k in counts),
             len(pending_rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
