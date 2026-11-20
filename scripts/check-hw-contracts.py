#!/usr/bin/env python3
"""Verify every hardware-contract row against the line it cites.

The manifest (docs/research/power/HW-CONTRACTS.toml) is the list of numbers the
four lines cannot let drift silently: GLINK owner and lease layout, the SCM
register contract, trip points, PDMEM addresses. Each row names a file and a
line, plus the text that must sit on it, so this gate fails when a constant
moves instead of leaving a document pointing at the wrong address - the shape
that made four docs wrong in one week.

A `dependence = "firmware"` row is a number the DSP, the boot chain or the
vendor Linux also knows: a citation of our own source proves nothing about the
other side, so such a row must carry an INDEPENDENT source as well -
`second = [...]`, a firmware image offset or a line in another implementation of
the same protocol - and a row that has none must say so with
`second_unavailable = { tried = [...], why = "..." }`, where `tried` names the
sources that were actually searched and `why` names what would settle it. The
words "cannot be verified" alone are not a reason (Lead, 2026-11-20).

usage: check-hw-contracts.py [--root DIR] [--manifest PATH]
exit 0 every row verified / 1 problems / 2 manifest unusable
"""
from __future__ import annotations

import argparse
import ast
import os
import pathlib
import re
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
REL = "docs/research/power/HW-CONTRACTS.toml"
LANES = {"adsp", "battery", "charger", "thermal", "power"}
DEPENDENCE = {"none", "macro", "firmware", "property-number", "layout"}
FIELDS = ("id", "lane", "what", "source", "expect", "dependence", "ios27")
PREFLIGHT_TOOL = "scripts/check-ios27-power-preflight.py"
VERDICTS27 = ("same", "drift", "unchecked")
DRIVE = re.compile(r"^([A-Za-z]):[\\/]")


def hostpath(text: str) -> pathlib.Path:
    """Translate a Windows-style path for whichever host runs the gate (P-259).

    The table is written once and read on Windows and under WSL; a path that only
    resolves on one of them would make the gate green on one host and red on the
    other, which is the defect PROP-NUMBERS hit on its first version.
    """
    if os.name == "nt":
        return pathlib.Path(text)
    match = DRIVE.match(text)
    if not match:
        return pathlib.Path(text)
    rest = text[2:].replace("\\", "/").lstrip("/")
    return pathlib.Path("/mnt") / match.group(1).lower() / rest


def cited(root: pathlib.Path, roots: dict, text: str) -> tuple[pathlib.Path | None, str]:
    """Resolve a citation; `external:<root>/<path>` names a tree outside the repo."""
    text = text.strip()
    if not text.startswith("external:"):
        return root / text, ""
    name, _, tail = text[len("external:"):].partition("/")
    if name not in roots:
        return None, f"external root {name!r} is not declared under [roots] (have {sorted(roots)})"
    return hostpath(str(roots[name])) / tail, ""


def second_problems(label: str, row: dict, root: pathlib.Path, roots: dict) -> list[str]:
    """Check the independent sources of one row and the firmware-row obligation."""
    problems: list[str] = []
    entries = row.get("second")
    unavailable = row.get("second_unavailable")
    if entries is not None and not isinstance(entries, list):
        problems.append(f"{label}: second is not an array of tables")
        entries = None
    if unavailable is not None and not isinstance(unavailable, dict):
        problems.append(f"{label}: second_unavailable is not a table")
        unavailable = None
    if entries and unavailable:
        problems.append(f"{label}: second and second_unavailable are mutually exclusive")
    if str(row.get("dependence")) == "firmware" and not entries and not unavailable:
        problems.append(
            f"{label}: firmware row has no independent second source and does not say why "
            "(second = [...] or second_unavailable = { tried, why })")
    for entry in entries or []:
        if not isinstance(entry, dict):
            problems.append(f"{label}: a second-source entry is not a table")
            continue
        if "bytes" in entry:
            problems += bytes_problems(label, entry, root, roots)
            continue
        source = str(entry.get("source") or "")
        expect = str(entry.get("expect") or "")
        if not source or ":" not in source:
            problems.append(f"{label}: second source {source!r} is not path:line")
            continue
        rel, _, number = source.rpartition(":")
        try:
            want = int(number)
        except ValueError:
            problems.append(f"{label}: second source line {number!r} is not a number")
            continue
        path, error = cited(root, roots, rel)
        if error:
            problems.append(f"{label}: {error}")
            continue
        if path is None or not path.is_file():
            problems.append(f"{label}: second source {rel} does not exist")
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as error:
            problems.append(f"{label}: cannot read second source {rel}: {error}")
            continue
        if not 1 <= want <= len(lines):
            problems.append(f"{label}: second source {rel} has {len(lines)} lines, the row cites {want}")
            continue
        if expect and expect not in lines[want - 1]:
            problems.append(f"{label}: second source {rel}:{want} does not contain {expect!r}")
    if unavailable is not None:
        tried = unavailable.get("tried") or []
        why = str(unavailable.get("why") or "")
        if not isinstance(tried, list) or len(tried) < 2:
            problems.append(
                f"{label}: second_unavailable lists {len(tried) if isinstance(tried, list) else 0} "
                "tried source(s); at least two are required so the reason is checkable")
        if not why.strip():
            problems.append(f"{label}: second_unavailable has no why (name the artefact that would settle it)")
    return problems


def bytes_problems(label: str, entry: dict, root: pathlib.Path, roots: dict) -> list[str]:
    """A second source may be a byte range inside a binary the repo does not carry."""
    rel = str(entry.get("bytes") or "")
    try:
        offset = int(entry.get("offset"))
    except (TypeError, ValueError):
        return [f"{label}: second source {rel} has no integer offset"]
    want_hex = str(entry.get("hex") or "").replace(" ", "").lower()
    if not want_hex or len(want_hex) % 2:
        return [f"{label}: second source {rel} has no whole-byte hex"]
    path, error = cited(root, roots, rel)
    if error:
        return [f"{label}: {error}"]
    if path is None or not path.is_file():
        return [f"{label}: second source {rel} does not exist"]
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            handle.seek(max(offset, 0))
            actual = handle.read(len(want_hex) // 2).hex()
    except OSError as error:
        return [f"{label}: cannot read second source {rel}: {error}"]
    if offset < 0 or offset + len(want_hex) // 2 > size:
        return [f"{label}: second source {rel} is {size} B, offset {offset} + {len(want_hex) // 2} does not fit"]
    if actual != want_hex:
        return [f"{label}: second source {rel} at offset {offset:#x} reads {actual or 'nothing'}, the row records {want_hex}"]
    return []




def checked27(label: str, row: dict, tree27) -> list[str]:
    """Every row states what the 27 copy holds, and the gate re-opens that copy. Aimed at
    the rows whose whole claim is "27 is the same as 16": that claim is two copies of one
    fact, and two copies drift (P-259)."""
    problems: list[str] = []
    verdict = str(row.get("same27") or "").strip()
    if not verdict:
        problems.append(f"{label}: does not say whether the 27 copy is the same "
                        f"(same27 = same | drift | unchecked)")
        return problems
    if verdict not in VERDICTS27:
        problems.append(f"{label}: same27 {verdict!r} is not one of {list(VERDICTS27)}")
        return problems
    why = str(row.get("why27") or "").strip()
    if verdict in ("drift", "unchecked") and not why:
        problems.append(f"{label}: same27 = {verdict} needs why27, saying what the 27 copy holds")
    copy = str(row.get("copy27") or "").strip()
    if verdict == "unchecked":
        if copy:
            problems.append(f"{label}: same27 = unchecked cannot also cite copy27")
        return problems
    if ":" not in copy:
        problems.append(f"{label}: copy27 {copy!r} is not path:line")
        return problems
    if tree27 is None:
        problems.append(f"{label}: the manifest needs tree27 to check copy27")
        return problems
    rel, _, number = copy.rpartition(":")
    try:
        line = int(number)
    except ValueError:
        problems.append(f"{label}: copy27 line {number!r} is not a number")
        return problems
    path = pathlib.Path(tree27) / rel
    if not path.is_file():
        problems.append(f"{label}: the 27 tree has no {rel}")
        return problems
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as error:
        problems.append(f"{label}: cannot read the 27 copy {rel}: {error}")
        return problems
    expect = str(row.get("expect") or "")
    found = [i + 1 for i, text in enumerate(lines) if expect and expect in text]
    if verdict == "same":
        if not 1 <= line <= len(lines):
            problems.append(f"{label}: the 27 copy {rel} has {len(lines)} lines, the row cites {line}")
        elif expect and expect not in lines[line - 1]:
            problems.append(f"{label}: 27 {rel}:{line} does not contain {expect!r} (copy27 says same, "
                            f"the copies drifted)")
    elif not found:
        pass
    else:
        problems.append(f"{label}: the 27 copy already carries {expect!r} at line(s) {found[:3]}; "
                        f"same27 = drift is stale, flip it to same")
    return problems

def computed27(row: dict, tree: pathlib.Path) -> tuple[str, str]:
    """What a real tree actually holds for this row: same, drift, moved (the line is out
    of range) or missing. This is the computed counterpart of the hand-written same27
    claim. A same/drift row is opened at its copy27 line, because that is the side the
    claim names; an unchecked row has no 27-side line yet, so its source is tried."""
    source = str(row.get("source") or "")
    if source.startswith("external:"):
        return "skipped", source
    # A row with copy27 names where the text lives in the 27 tree. For same/drift rows
    # that side is the claim under test; the source line is our own (16-line) copy and
    # its offset may legitimately differ (P-259: the copies may move independently).
    if row.get("copy27") and str(row.get("same27") or "") in ("same", "drift"):
        source = str(row["copy27"])
    if ":" not in source:
        return "missing", source
    rel, _, number = source.rpartition(":")
    try:
        line = int(number)
    except ValueError:
        return "missing", source
    path = tree / rel
    if not path.is_file():
        return "missing", rel
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "missing", rel
    expect = str(row.get("expect") or "")
    if not 1 <= line <= len(lines):
        return "moved", f"{rel} has {len(lines)} lines, the row cites {line}"
    if expect and expect in lines[line - 1]:
        return "same", f"{rel}:{line}"
    return "drift", f"{rel}:{line} does not contain {expect!r}"


def against_problems(data: dict, tree: pathlib.Path) -> tuple[list[str], list[str]]:
    """Hold every same27 claim to what the tree really contains. Unchecked, the column is
    prose that happens to sit next to a checker: "27 is the same as 16" is two copies of
    one fact, and only a run in the other tree says whether the copies still agree."""
    problems: list[str] = []
    report: list[str] = []
    for index, row in enumerate(data.get("contract") or [], 1):
        label = str(row.get("id") or f"row {index}")
        verdict, detail = computed27(row, tree)
        if verdict == "skipped":
            continue
        report.append(f"{verdict:7s} {label:30s} {detail}")
        claim = str(row.get("same27") or "").strip()
        if claim == "same" and verdict != "same":
            problems.append(f"{label}: copy27 says same, the tree says {verdict} ({detail})")
        elif claim == "drift" and verdict == "same":
            problems.append(f"{label}: copy27 says drift, the tree already carries it ({detail})")
        elif claim == "drift" and verdict == "missing":
            problems.append(f"{label}: copy27 says drift, the tree has no such file ({detail}); "
                            "same27 = unchecked with a reason")
        elif claim == "unchecked" and verdict == "same":
            problems.append(f"{label}: copy27 says unchecked, the tree already carries the text "
                            f"({detail}); say same")
    return problems, report


def preflight_functions(root: pathlib.Path) -> set[str] | None:
    """Top-level check_* functions of the 27 preflight, or None when it is absent."""
    path = root / PREFLIGHT_TOOL
    if not path.is_file():
        return None
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, ValueError):
        return set()
    return {node.name for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("check_")}


def preflight_problems(label: str, row: dict, functions: set[str] | None) -> list[str]:
    """A row that claims a preflight verdict must name a function that exists.

    P-276: a judgement that only lives in the preflight, with no contract row
    behind it, is a judgement nobody reviews. The reverse link - the coverage
    table's backed_by - is checked by scripts/check-preflight-coverage.py; this
    is the forward half, so a row cannot name a function the tool does not have.
    """
    names = row.get("preflight")
    if names is None:
        return []
    if not isinstance(names, list) or not names:
        return [f"{label}: preflight must be a non-empty array of check_* function names"]
    problems: list[str] = []
    seen: set[str] = set()
    for name in names:
        if not isinstance(name, str) or not name.startswith("check_"):
            problems.append(f"{label}: preflight entry {name!r} is not a check_* function name")
            continue
        if name in seen:
            problems.append(f"{label}: preflight names {name} twice")
            continue
        seen.add(name)
        if functions is None:
            problems.append(f"{label}: {PREFLIGHT_TOOL} is missing, so preflight {name} cannot be checked")
        elif name not in functions:
            problems.append(f"{label}: {PREFLIGHT_TOOL} has no {name} (the row names a verdict nothing computes)")
    return problems


def verify(root: pathlib.Path, manifest: pathlib.Path) -> list[str]:
    problems: list[str] = []
    try:
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [f"{manifest} is missing"]
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
        return [f"{manifest} does not parse: {error}"]
    rows = data.get("contract")
    if not isinstance(rows, list) or not rows:
        return [f"{manifest} has no [[contract]] rows"]
    roots = data.get("roots") or {}
    if not isinstance(roots, dict):
        return [f"{manifest}: [roots] is not a table"]
    tree27 = data.get("tree27")
    tree27 = hostpath(str(tree27)) if tree27 else None
    preflight_fns = preflight_functions(root)
    seen: dict[str, int] = {}
    for index, row in enumerate(rows, 1):
        label = str(row.get("id") or f"row {index}")
        for field in FIELDS:
            if not str(row.get(field) or "").strip():
                problems.append(f"{label}: {field} is empty")
        if str(row.get("lane") or "") not in LANES:
            problems.append(f"{label}: lane {row.get('lane')!r} is not one of {sorted(LANES)}")
        if str(row.get("dependence") or "") not in DEPENDENCE:
            problems.append(f"{label}: dependence {row.get('dependence')!r} is not one of {sorted(DEPENDENCE)}")
        problems += preflight_problems(label, row, preflight_fns)
        if label in seen:
            problems.append(f"{label}: duplicate id (also row {seen[label]})")
        seen.setdefault(label, index)
        source = str(row.get("source") or "")
        if ":" not in source:
            problems.append(f"{label}: source {source!r} is not path:line")
            continue
        rel, _, number = source.rpartition(":")
        try:
            want_line = int(number)
        except ValueError:
            problems.append(f"{label}: {number!r} is not a line number")
            continue
        path = root / rel
        if not path.is_file():
            problems.append(f"{label}: {rel} does not exist")
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as error:
            problems.append(f"{label}: cannot read {rel}: {error}")
            continue
        if not 1 <= want_line <= len(lines):
            problems.append(f"{label}: {rel} has {len(lines)} lines, the row cites {want_line}")
            continue
        expect = str(row.get("expect") or "")
        if expect and expect not in lines[want_line - 1]:
            problems.append(f"{label}: {rel}:{want_line} does not contain {expect!r}")
        mirror = str(row.get("mirror") or "").strip()
        if mirror:
            if ":" not in mirror:
                problems.append(f"{label}: mirror {mirror!r} is not path:line")
            else:
                mrel, _, mnumber = mirror.rpartition(":")
                try:
                    mline = int(mnumber)
                except ValueError:
                    problems.append(f"{label}: mirror line {mnumber!r} is not a number")
                else:
                    mpath = root / mrel
                    if not mpath.is_file():
                        problems.append(f"{label}: mirror {mrel} does not exist")
                    else:
                        mlines = mpath.read_text(encoding="utf-8", errors="replace").splitlines()
                        if not 1 <= mline <= len(mlines):
                            problems.append(f"{label}: mirror {mrel} has {len(mlines)} lines, the row cites {mline}")
                        elif expect and expect not in mlines[mline - 1]:
                            problems.append(
                                f"{label}: mirror {mrel}:{mline} does not contain {expect!r} (the second copy drifted)")
        problems += second_problems(label, row, root, roots)
        problems += checked27(label, row, tree27)
    covered = {str(row.get("lane") or "") for row in rows}
    for lane in sorted(LANES - covered):
        problems.append(f"no row covers the {lane} line")
    return problems


CHECKLIST = "docs/research/power/HW-CONTRACTS-IOS27.md"
ORDER = ["none", "macro", "firmware", "property-number", "layout"]


def second_note(row: dict) -> str:
    entries = row.get("second")
    if isinstance(entries, list) and entries:
        return f"independent, {len(entries)} citation(s)"
    unavailable = row.get("second_unavailable")
    if isinstance(unavailable, dict):
        tried = unavailable.get("tried") or []
        return f"none found, {len(tried) if isinstance(tried, list) else 0} tried"
    return ""


def render(root: pathlib.Path, manifest: pathlib.Path) -> str:
    """The rewire checklist, generated from the table so it cannot drift (P-259)."""
    rows = tomllib.loads(manifest.read_text(encoding="utf-8"))["contract"]
    out = [
        "# iOS 27 rewire checklist (generated)",
        "",
        "Generated by `python3 scripts/check-hw-contracts.py --render` from",
        "`docs/research/power/HW-CONTRACTS.toml`; edit the table, never this file.",
        "The gate fails while the two disagree.",
        "",
        f"{len(rows)} rows. Grouped by `dependence`, which says what a move to",
        "iOS 27 has to re-check: `none` rows are our own encoding and travel as-is,",
        "the rest name the thing to confirm before the number is trusted again.",
        "The `second source` column is the independent evidence behind a `firmware`",
        "row: a citation in another implementation, bytes inside the firmware image,",
        "or the count of sources searched when none exists (see the table's reason).",
        "",
    ]
    for dependence in ORDER:
        group = [row for row in rows if str(row.get("dependence")) == dependence]
        if not group:
            continue
        out.append(f"## {dependence} ({len(group)})")
        out.append("")
        out.append("| id | lane | what | source | second source | 27 copy | 27 action |")
        out.append("| --- | --- | --- | --- | --- | --- | --- |")
        for row in group:
            cells = [str(row.get(key) or "").replace("|", "\\|")
                     for key in ("id", "lane", "what", "source")]
            cells.append(second_note(row).replace("|", "\\|"))
            copy = str(row.get("copy27") or "").strip()
            cells.append((str(row.get("same27") or "") + (f" `{copy}`" if copy else "")).replace("|", "\\|"))
            cells.append(str(row.get("ios27") or "").replace("|", "\\|"))
            out.append("| " + " | ".join(cells) + " |")
        out.append("")
    return "\n".join(out)


def checklist_problems(root: pathlib.Path, manifest: pathlib.Path) -> list[str]:
    path = root / CHECKLIST
    if not path.is_file():
        return [f"{CHECKLIST} is missing; run --render"]
    try:
        expected = render(root, manifest)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return []
    if path.read_text(encoding="utf-8") != expected:
        return [f"{CHECKLIST} is stale; run --render (P-259: a generated list may not be hand-edited)"]
    return []


WORKORDER = "docs/research/power/27-WORKORDER.md"
BT = chr(96)


def code(text) -> str:
    return BT + str(text) + BT


def line_at(base: pathlib.Path, text: str) -> str:
    if ":" not in text:
        return ""
    rel, _, number = text.rpartition(":")
    try:
        n = int(number)
        lines = (base / rel).read_text(encoding="utf-8", errors="replace").splitlines()
    except (ValueError, OSError):
        return ""
    return lines[n - 1].strip() if 1 <= n <= len(lines) else ""


def tokens(expect: str) -> list[str]:
    seen: list[str] = []
    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", expect):
        if token not in seen:
            seen.append(token)
    return seen


def candidates(base: pathlib.Path, text: str, expect: str, limit: int = 3) -> list[str]:
    """The copy27 offset is our line number, so on a drifted copy it usually lands
    somewhere unrelated. Locate the text by its own keywords instead of trusting the
    offset, otherwise the work order shows a wrong line and invites a wrong edit."""
    if ":" not in text:
        return []
    rel, _, _number = text.rpartition(":")
    try:
        lines = (base / rel).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    wanted = tokens(expect)
    if not wanted:
        return []
    found: list[str] = []
    for number, line in enumerate(lines, 1):
        if any(token in line for token in wanted):
            found.append(f"{rel}:{number} {line.strip()[:110]}")
    return found[:limit]


def source_text(root: pathlib.Path, row: dict) -> str:
    source = str(row.get("source") or "")
    if source.startswith("external:"):
        return ""
    return line_at(root, source)


def render_workorder(root: pathlib.Path, manifest: pathlib.Path, tree=None) -> str:
    """The drift columns are only useful if somebody can act on them, so this turns the
    computed verdicts into an ordered list: for every row the 27 tree disagrees with, our
    line and the 27 line are printed side by side. Generated, never hand-written (P-259):
    a work order that is edited by hand stops matching the tree it describes."""
    data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    rows = data.get("contract") or []
    tree27 = str(data.get("tree27") or "")
    if tree is None and tree27:
        tree = hostpath(tree27)
    out = ["# iOS 27 侧要做的事（从契约表算出来）", ""]
    out.append("Generated by " + code("python3 scripts/check-hw-contracts.py --workorder " + WORKORDER)
               + " from " + code(REL) + "; edit the table, never this file (P-259).")
    out.append("每一行都是 " + code("--against") + " 在该 27 检出上现算的结果；27 线改完后重新生成，条目自己会变少。")
    out.append("")
    if tree is None or not tree.is_dir():
        out.append("本机没有 27 检出（" + code(tree27 or "树里没写 tree27") + "），所以什么都没算。")
        out.append("")
        return "\n".join(out)
    buckets = {"drift": [], "moved": [], "missing": []}
    same = 0
    for index, row in enumerate(rows, 1):
        verdict, detail = computed27(row, tree)
        if verdict == "same":
            same += 1
        elif verdict in buckets:
            buckets[verdict].append((row, detail))
    for verdict, title, blurb in (
        ("drift", "必须改：27 侧这一行与契约不符",
         "两边都还在，但 27 侧的行上不是契约要的文本。下面给出两边的原文，改法是机械的。"),
        ("moved", "行号越界：27 侧文件比契约引用的位置短",
         "文件在，内容可能也对，但行号已经指不到；先按关键字在 27 侧定位再决定搬哪一行。"),
        ("missing", "缺文件：27 侧还没有这个文件",
         "整份文件要过去（走 build/power-carry-bundle 或 Emilelu 远端），不是改一行。"),
    ):
        items = buckets[verdict]
        out.append("## " + title + "（" + str(len(items)) + " 行）")
        out.append("")
        if not items:
            out.append("无。")
            out.append("")
            continue
        out.append(blurb)
        out.append("")
        for row, detail in items:
            out.append("### " + str(row.get("id") or "?") + " — " + str(row.get("what") or ""))
            out.append("")
            out.append("- 线：" + str(row.get("lane") or "") + "；依赖：" + str(row.get("dependence") or ""))
            out.append("- 契约（本仓）：" + code(str(row.get("source") or "")))
            ours = source_text(root, row)
            if ours:
                out.append("- 本仓这一行：" + code(ours))
            if verdict == "drift":
                out.append("- 27 侧现状：" + code(detail))
                hits = candidates(tree, str(row.get("copy27") or ""), str(row.get("expect") or ""))
                if hits:
                    out.append("- 27 侧候选位置（按契约文本里的关键字找；copy27 的偏移是我们这边的行号，在 27 侧不可信）：")
                    for hit in hits:
                        out.append("  - " + code(hit))
                else:
                    out.append("- 27 侧连关键字都没出现：这一段要整段搬过去")
            else:
                out.append("- 27 侧现状：" + detail)
            out.append("- 27 要做什么：" + str(row.get("ios27") or ""))
            why = str(row.get("why27") or "").strip()
            if why:
                out.append("- 为什么这样记：" + why)
            out.append("")
    out.append("## 已同（" + str(same) + " 行）")
    out.append("")
    out.append("这些行 27 侧已经和本仓一致，不需要动作；表里仍逐行记着 " + code("copy27")
               + "，所以它们下次漂移时 " + code("--against") + " 会先说。")
    out.append("")
    out.append("改完再跑 " + code("python3 scripts/check-hw-contracts.py --against " + tree27)
               + "：它必须把每一行都算一遍、并且与表里的 same27 一致。")
    return "\n".join(out)


def workorder_problems(root: pathlib.Path, manifest: pathlib.Path) -> list[str]:
    """A host without the 27 checkout cannot compute this list, so it is not policed
    there; everywhere else a work order that no longer matches the tree is red."""
    try:
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    except (FileNotFoundError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return []
    tree27 = str(data.get("tree27") or "")
    if not tree27 or not hostpath(tree27).is_dir():
        return []
    path = root / WORKORDER
    if not path.is_file():
        return [WORKORDER + " is missing; run --workorder " + WORKORDER]
    expected = render_workorder(root, manifest)
    if path.read_text(encoding="utf-8") != expected:
        return [WORKORDER + " is stale; run --workorder " + WORKORDER
                + " (P-259: the work order is computed from the 27 tree, not written)"]
    return []


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--manifest")
    parser.add_argument("--render", metavar="PATH", help="write the generated rewire checklist here")
    parser.add_argument("--workorder", metavar="PATH",
                        help="write the ordered list of what the 27 tree still has to change")
    parser.add_argument("--against", metavar="TREE",
                        help="compute every row in TREE and hold the same27 claims to it")
    args = parser.parse_args()
    root = pathlib.Path(args.root).resolve()
    manifest = pathlib.Path(args.manifest) if args.manifest else root / REL
    if args.render:
        target = pathlib.Path(args.render)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(root, manifest), encoding="utf-8", newline="\n")
        print(f"rendered {len(tomllib.loads(manifest.read_text(encoding='utf-8'))['contract'])} row(s) to {target}")
        return 0

    if args.workorder:
        target = pathlib.Path(args.workorder)
        target.parent.mkdir(parents=True, exist_ok=True)
        tree = hostpath(args.against) if args.against else None
        text = render_workorder(root, manifest, tree)
        target.write_text(text, encoding="utf-8", newline="\n")
        sections = text.count("\n### ")
        print(f"wrote the 27 work order to {target} ({sections} section(s))")
        return 0

    if args.against:
        tree = hostpath(args.against)
        if not tree.is_dir():
            print(f"❌ {tree} is not a directory", file=sys.stderr)
            return 2
        try:
            data = tomllib.loads(manifest.read_text(encoding="utf-8"))
        except (FileNotFoundError, tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
            print(f"❌ {manifest}: {error}", file=sys.stderr)
            return 2
        claims, report = against_problems(data, tree)
        for line in report:
            print(line)
        counts = {}
        for line in report:
            counts[line.split()[0]] = counts.get(line.split()[0], 0) + 1
        summary = ", ".join(f"{n} {verdict}" for verdict, n in sorted(counts.items()))
        if claims:
            for problem in claims:
                print(f"❌ {problem}", file=sys.stderr)
            print(f"hw-contracts --against {tree}: {len(claims)} claim(s) disagree", file=sys.stderr)
            return 1
        print(f"✅ hw-contracts --against {tree}: {len(report)} row(s) computed ({summary}); "
              f"every same27 claim agrees")
        return 0

    problems = verify(root, manifest)
    if not args.manifest:
        problems += checklist_problems(root, manifest)
        problems += workorder_problems(root, manifest)
    if problems:
        for problem in problems:
            print(f"❌ {problem}", file=sys.stderr)
        print(f"hw-contracts: {len(problems)} problem(s)", file=sys.stderr)
        return 2 if problems and problems[0].startswith(str(manifest)) else 1
    rows = tomllib.loads(manifest.read_text(encoding="utf-8"))["contract"]
    lanes = sorted({str(row["lane"]) for row in rows})
    independent = sum(1 for row in rows if isinstance(row.get("second"), list) and row["second"])
    pending = sum(1 for row in rows if isinstance(row.get("second_unavailable"), dict))
    checked = [row for row in rows if str(row.get("same27") or "") in ("same", "drift")]
    same27 = sum(1 for row in checked if str(row.get("same27")) == "same")
    print(f"✅ hw-contracts: {len(rows)} contract(s) across {len(lanes)} lane(s) match the lines they cite "
          f"({independent} with an independent second source, {pending} documented as not found; "
          f"{len(checked)} re-opened in the 27 copy: {same27} same, {len(checked) - same27} drift)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
