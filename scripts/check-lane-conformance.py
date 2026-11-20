#!/usr/bin/env python3
"""Check the per-lane conformance table against the official page it quotes.

docs/research/power/LANE-CONFORMANCE.toml is the answer to "each lane, line by
line, against the official page, with evidence". Three things make such a table
survive: the quote must exist in the page (otherwise somebody is remembering a
sentence that was never there), the evidence must be a file that exists, and a
lane may not sit at "verified" without a reason once it is partial.

Render the reader-facing summary with --render.
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
TABLE = ROOT / "docs" / "research" / "power" / "LANE-CONFORMANCE.toml"
RENDER = ROOT / "docs" / "research" / "power" / "LANE-CONFORMANCE.md"
LANES = ("adsp", "battery", "charger", "thermal", "power")
STATUSES = ("verified", "partial", "not-done", "delegated")
NEEDS_WHY = ("partial", "not-done", "delegated")
HEADER = """# 四条线 + Power 对官网页面的逐条对齐（生成物）

由 `python3 scripts/check-lane-conformance.py --render` 生成，**不要手改**：改
`docs/research/power/LANE-CONFORMANCE.toml`。门禁核对三件事——引用的句子确实在页面上、
证据文件确实存在、非 `verified` 的行写了理由（P-259）。

页面：`docs/zh/porting/power.md`（unixnu.com/zh/porting/power）。
"""


def read(path):
    return pathlib.Path(path).read_text(encoding="utf-8", errors="replace")


def hostpath(path):
    match = re.match(r"^([A-Za-z]):[\\/](.*)$", str(path))
    if match and os.name != "nt":
        return "/mnt/%s/%s" % (match.group(1).lower(), match.group(2))
    return str(path)


def page_text(table):
    root = str(table.get("page_root") or "")
    page = str(table.get("page") or "")
    if not root or not page:
        return None, "the table records no page_root/page"
    target = pathlib.Path(hostpath(root)) / page
    if not target.is_file():
        return None, "the page copy %s is not present on this host" % target
    return target, read(target)


def evidence_path(root, evidence):
    text = str(evidence or "").strip()
    for prefix in ("judge:", "gate:", "console:", "external:"):
        if text.startswith(prefix):
            text = text[len(prefix):]
            if prefix == "external:":
                return None, None
    target = pathlib.Path(text)
    if not target.is_absolute():
        target = pathlib.Path(root) / text
    return target, None


def verify(root, table_path):
    table = tomllib.loads(read(table_path))
    rows = table.get("row") or []
    problems, judged = [], []
    seen = set()
    if not rows:
        problems.append("the table carries no row")
    target_page, page_error = page_text(table)
    body = ""
    if target_page is None:
        problems.append(page_error)
    else:
        body = read(target_page)
    for row in rows:
        label = row.get("id")
        lane = row.get("lane")
        status = row.get("status")
        if not label:
            problems.append("a row carries no id")
            continue
        if label in seen:
            problems.append("%s: duplicate id" % label)
        seen.add(label)
        if lane not in LANES:
            problems.append("%s: lane %r is not one of %s" % (label, lane, ", ".join(LANES)))
        if status not in STATUSES:
            problems.append("%s: status %r is not one of %s" % (label, status, ", ".join(STATUSES)))
        if status in NEEDS_WHY and not str(row.get("why") or "").strip():
            problems.append("%s: status %s needs a why" % (label, status))
        if status == "verified" and str(row.get("why") or "").strip():
            pass  # a note on a verified row is fine, it is not the reason it is partial
        requirement = str(row.get("requirement") or "").strip()
        if not requirement:
            problems.append("%s: no requirement quoted" % label)
        elif body and requirement not in body:
            problems.append("%s: the page does not carry %r" % (label, requirement))
        section = str(row.get("section") or "")
        anchor = str(row.get("anchor") or "")
        if body and section:
            if not re.search(r"^##+ %s\. " % re.escape(section), body, re.M):
                problems.append("%s: the page has no section %s" % (label, section))
        if body and anchor:
            if "{%s}" % anchor.lstrip("#") not in body and "{#%s}" % anchor.lstrip("#") not in body:
                problems.append("%s: the page has no anchor %s" % (label, anchor))
        target, _ = evidence_path(root, row.get("evidence"))
        if target is None:
            pass  # an external: citation cannot be opened here, and says so
        elif not target.exists():
            problems.append("%s: evidence %s does not exist" % (label, row.get("evidence")))
        judged.append((label, lane, section, status, row))
    covered = {lane for _, lane, _, _, _ in judged}
    for lane in LANES:
        if lane not in covered:
            problems.append("lane %s has no row" % lane)
    return judged, problems


def render(judged):
    lines = [HEADER]
    counts = {}
    for _, _, _, status, _ in judged:
        counts[status] = counts.get(status, 0) + 1
    lines.append("合计 %d 行：%s。" % (len(judged),
                 "，".join("%s %d" % (k, counts[k]) for k in STATUSES if k in counts)))
    for lane in LANES:
        rows = [entry for entry in judged if entry[1] == lane]
        if not rows:
            continue
        lines.append("")
        lines.append("## %s（%d 行）" % (lane, len(rows)))
        lines.append("")
        lines.append("| id | § | 页面要求 | 证据 | 状态 | 说明 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for label, _, section, status, row in rows:
            why = str(row.get("why") or "").strip().replace("|", "/")
            lines.append("| `%s` | %s | %s | `%s` | %s | %s |"
                         % (label, section, row.get("requirement", ""), row.get("evidence", ""),
                            status, why or "—"))
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
    parser.add_argument("--render", nargs="?", const=str(RENDER), default=None)
    args = parser.parse_args(argv)
    try:
        judged, problems = verify(pathlib.Path(args.root), args.table)
    except (OSError, tomllib.TOMLDecodeError) as error:
        print("check-lane-conformance: cannot read the table: %s" % error)
        return 2
    if args.render:
        pathlib.Path(args.render).write_text(render(judged), encoding="utf-8", newline="\n")
        print("lane-conformance: rendered %s (%d row(s))" % (args.render, len(judged)))
    for problem in problems:
        print("FAIL %s" % problem)
    if problems:
        print("lane-conformance: FAIL (%d problem(s))" % len(problems))
        return 1
    counts = {}
    for _, _, _, status, _ in judged:
        counts[status] = counts.get(status, 0) + 1
    print("lane-conformance: OK (%d row(s) across %d lane(s): %s)"
          % (len(judged), len(LANES),
             ", ".join("%s %d" % (k, counts[k]) for k in STATUSES if k in counts)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
