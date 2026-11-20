#!/usr/bin/env python3
"""Check the per-lane conformance table against the official page it quotes.

docs/research/power/LANE-CONFORMANCE.toml is the answer to "each lane, line by
line, against the official page, with evidence". Six things make such a table
survive: the quote must exist in the page section the row names (otherwise
somebody is remembering a sentence that was never there, or reading it out of
another section), the evidence must be a file that exists, a
verified row must name the line in that file which proves it (otherwise any
unrelated file passes), that line may not be the quoted sentence itself, a lane
may not sit at "partial" without a reason, and two rows in the same lane may not
quote the same sentence.

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
MIN_PROOF = 8
HEADER = """# 四条线 + Power 对官网页面的逐条对齐（生成物）

由 `python3 scripts/check-lane-conformance.py --render` 生成，**不要手改**：改
`docs/research/power/LANE-CONFORMANCE.toml`。门禁核对六件事——引用的句子确实在页面、且在该行写的节里；
证据文件确实存在、`verified` 行写的那行证据确实在文件里、证据行不能又是页面要求本身、
非 `verified` 的行写了理由、同一 lane 里同一句要求没有被两行重复引用（P-259）。

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


def evidence_line(row):
    text = str(row.get("evidence_line") or "").strip()
    return text


def section_block(body, section):
    """Return the named top-level section, heading included, or None."""
    text = str(section or "").strip()
    if not text:
        return None
    match = re.search(r"^##[ \t]+%s\.(?=[ \t]|$)" % re.escape(text), body, re.M)
    if not match:
        return None
    rest = body[match.end():]
    following = re.search(r"^#{1,2}[ \t]+", rest, re.M)
    end = match.end() + (following.start() if following else len(rest))
    return body[match.start():end]


def verify(root, table_path):
    table = tomllib.loads(read(table_path))
    rows = table.get("row") or []
    problems, judged = [], []
    seen = set()
    seen_requirements = {}
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
        section = str(row.get("section") or "")
        anchor = str(row.get("anchor") or "")
        block = section_block(body, section) if body and section else None
        if body and section and block is None:
            problems.append("%s: the page has no section %s" % (label, section))
        requirement = str(row.get("requirement") or "").strip()
        if not requirement:
            problems.append("%s: no requirement quoted" % label)
        elif body and requirement not in body:
            problems.append("%s: the page does not carry %r" % (label, requirement))
        elif body and block is not None and requirement not in block:
            problems.append("%s: the page carries %r outside section %s" % (label, requirement, section))
        if requirement:
            key = (lane, requirement)
            earlier = seen_requirements.get(key)
            if earlier:
                problems.append("%s: %r is already quoted by %s in the same lane; split the page sentence into the clauses it lists" % (label, requirement, earlier))
            else:
                seen_requirements[key] = label
        if body and anchor:
            name = anchor.lstrip("#")
            markers = ("{%s}" % name, "{#%s}" % name)
            if not any(marker in body for marker in markers):
                problems.append("%s: the page has no anchor %s" % (label, anchor))
            elif block is not None and not any(marker in block for marker in markers):
                problems.append("%s: the page has anchor %s outside section %s" % (label, anchor, section))
        target, _ = evidence_path(root, row.get("evidence"))
        if target is None:
            pass  # an external: citation cannot be opened here, and says so
        elif not target.exists():
            problems.append("%s: evidence %s does not exist" % (label, row.get("evidence")))
        proof = evidence_line(row)
        if proof and requirement and proof == requirement:
            problems.append("%s: evidence_line is the requirement itself; cite the implementation, not the page" % label)
        if status == "verified" and not proof:
            problems.append("%s: a verified row must name the line in its evidence that proves it (evidence_line)" % label)
        if proof and target is None:
            problems.append("%s: evidence_line cannot be checked on an external citation" % label)
        elif proof and target is not None and target.is_file():
            proof_body = read(target)
            if len(proof) < MIN_PROOF:
                problems.append("%s: evidence_line %r is too short to identify a line" % (label, proof))
            elif proof not in proof_body:
                problems.append("%s: evidence %s does not contain %r" % (label, row.get("evidence"), proof))
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
            evidence = "`%s`" % row.get("evidence", "")
            proof = evidence_line(row)
            if proof:
                evidence += "<br>`%s`" % proof.replace("|", "\\|")
            lines.append("| `%s` | %s | %s | %s | %s | %s |"
                         % (label, section, row.get("requirement", ""), evidence,
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
