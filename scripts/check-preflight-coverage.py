#!/usr/bin/env python3
"""Every check the iOS 27 power preflight makes has to land somewhere.

A preflight verdict has two consumers: the preflight run and the generated 27
work order, which is computed from the contract table. A verdict that exists
only in the preflight is therefore invisible to the work order (P-276).

An [[item]] row says where one check_* lands:
  backed_by = contract-row ids   (a hardware fact; the row must link back with
                                  preflight = ["check_..."], checked both ways)
  gate      = a repository file  (an independently runnable check)
  why       = neither, with a reason of at least 20 characters
  planned   = not implemented yet; needs next and cannot already land

The generated PREFLIGHT-COVERAGE.md is checked on every plain run, so a hand
edit is red even when the table is consistent (P-259).
"""
from __future__ import annotations

import argparse
import ast
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = "docs/research/power/PREFLIGHT-COVERAGE.toml"
RENDERED = "docs/research/power/PREFLIGHT-COVERAGE.md"
MIN_WHY = 20


def load(root: Path) -> tuple[dict, list[str]]:
    path = root / MANIFEST
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, [f"no {MANIFEST} (the preflight classes would go unlanded silently)"]
    except (OSError, tomllib.TOMLDecodeError) as error:
        return {}, [f"cannot read {MANIFEST}: {error}"]
    return data, []


def functions(root: Path, data: dict) -> tuple[set[str], list[str]]:
    """Top-level check_* functions, found by parsing rather than by a line regex.

    A regex only sees the shape it was written for: a decorator, an async def or
    a name with a digit would slip past it and the coverage table would measure
    less than it claims."""
    rel = data.get("preflight", "scripts/check-ios27-power-preflight.py")
    try:
        text = (root / rel).read_text(encoding="utf-8")
    except OSError as error:
        return set(), [f"cannot read {rel}: {error}"]
    try:
        tree = ast.parse(text, filename=str(root / rel))
    except SyntaxError as error:
        return set(), [f"{rel} does not parse: {error}"]
    names = {node.name for node in tree.body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
             and node.name.startswith("check_")}
    if not names:
        return set(), [f"{rel} carries no top-level check_* function; the coverage table measures nothing"]
    return names, []


def contract_rows(root: Path, data: dict) -> tuple[dict[str, dict], list[str]]:
    rel = data.get("manifest", "docs/research/power/HW-CONTRACTS.toml")
    try:
        manifest = tomllib.loads((root / rel).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, [f"no {rel}"]
    except (OSError, tomllib.TOMLDecodeError) as error:
        return {}, [f"cannot read {rel}: {error}"]
    rows = {}
    for row in manifest.get("contract", []):
        cid = str(row.get("id") or "")
        if cid:
            rows[cid] = row
    return rows, []


def linked(contract: dict) -> list[str]:
    mapped = contract.get("preflight", [])
    if isinstance(mapped, str):
        mapped = [mapped]
    return mapped if isinstance(mapped, list) else []


def verify(root: Path) -> tuple[list[dict], list[str], list[str]]:
    data, problems = load(root)
    if problems:
        return [], problems, []
    items = data.get("item", [])
    if not items:
        return [], ["the coverage table has no [[item]] row"], []
    names, bad = functions(root, data)
    problems += bad
    contracts, bad = contract_rows(root, data)
    problems += bad
    seen: dict[str, int] = {}
    planned: list[str] = []
    for index, row in enumerate(items, start=1):
        function = row.get("function", "")
        backed = row.get("backed_by", [])
        gate = row.get("gate", "")
        why = row.get("why", "")
        next_step = row.get("next", "")
        is_planned = bool(row.get("planned"))
        label = function or f"item {index}"
        if is_planned:
            if not next_step.strip():
                problems.append(f"{label}: a planned item has to say what will make it real (next)")
            if function:
                problems.append(f"{label}: a planned item must leave function empty")
            if gate or backed:
                problems.append(f"{label}: a planned item cannot already be landed")
            planned.append(label)
            continue
        if not function:
            problems.append(f"item {index}: names no check_* function")
            continue
        if function in seen:
            problems.append(f"{function}: appears twice in the table")
            continue
        seen[function] = index
        if function not in names:
            problems.append(f"{function}: the preflight has no such function")
        if not isinstance(backed, list):
            problems.append(f"{function}: backed_by must be a list of contract ids")
            backed = []
        for cid in backed:
            contract = contracts.get(cid)
            if contract is None:
                problems.append(f"{function}: names contract row {cid!r}, which "
                                f"{data.get('manifest', MANIFEST)} does not carry")
                continue
            if function not in linked(contract):
                problems.append(f"{function}: contract row {cid!r} does not link back "
                                f"with preflight = [{function!r}]")
        if gate and not (root / gate).is_file():
            problems.append(f"{function}: names the gate {gate}, which is not a file")
        if not backed and not gate and len(why.strip()) < MIN_WHY:
            problems.append(f"{function}: neither a contract row nor a gate, and no readable reason")
    missing = sorted(names - set(seen))
    for name in missing:
        problems.append(f"{name}: the preflight checks it, but no [[item]] row says where it lands")
    landed = {str(row.get("function") or ""): row for row in items
              if row.get("function") and not row.get("planned")}
    for cid, contract in contracts.items():
        mapped = linked(contract)
        if not mapped:
            continue
        if isinstance(contract.get("preflight"), list) is False and isinstance(contract.get("preflight"), str) is False:
            problems.append(f"contract row {cid!r}: preflight must be a list of check_* functions")
            continue
        for function in mapped:
            item = landed.get(function)
            if item is None:
                problems.append(f"contract row {cid!r}: preflight names {function!r}, "
                                f"which has no landed coverage row")
            elif cid not in (item.get("backed_by") or []):
                problems.append(f"contract row {cid!r}: {function!r} does not link back "
                                f"through backed_by")
    return items, problems, planned


def render(root: Path) -> str:
    items, problems, planned = verify(root)
    if problems:
        return "# 生成失败\n\n" + "\n".join(f"- {p}" for p in problems) + "\n"
    tick = chr(96)
    out = ["# 预检判定的落地表（生成物）", "",
           f"> Generated by {tick}scripts/check-preflight-coverage.py --render{tick}; edit",
           f"> {tick}docs/research/power/PREFLIGHT-COVERAGE.toml{tick}, never this file.", "",
           "| 判定 | 拦的是什么 | 落地在哪 | 说明 |", "|---|---|---|---|"]
    for row in items:
        if row.get("planned"):
            continue
        backed = row.get("backed_by", [])
        gate = row.get("gate", "")
        if backed:
            where = "契约表 " + "、".join(f"{tick}{cid}{tick}" for cid in backed)
        elif gate:
            where = f"门禁 {tick}{gate}{tick}"
        else:
            where = "无独立落地（见说明）"
        out.append(f"| {tick}{row.get('function', '')}{tick} | {row.get('what', '')} | {where} | {row.get('note', row.get('why', ''))} |")
    if planned:
        out += ["", "## 滚动待办（还没实现的判定）", ""]
        for row in items:
            if row.get("planned"):
                out += [f"### {row.get('what', '')}", "", row.get("why", "").strip(), "", "下一步：" + row.get("next", "").strip(), ""]
    return "\n".join(out).rstrip() + "\n"


def rendered_problems(root: Path) -> list[str]:
    """The committed generated table is checked even on a plain run: P-276 says a
    judgement may not exist only in the preflight, and the rendered file is the
    readable form of that judgement."""
    path = root / RENDERED
    if not path.is_file():
        return [f"{RENDERED} is missing; run --render {RENDERED}"]
    try:
        actual = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return [f"cannot read {RENDERED}: {error}"]
    if actual != render(root):
        return [f"{RENDERED} is stale; run --render {RENDERED} (P-259: generated coverage may not be hand-edited)"]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--render", metavar="PATH")
    args = parser.parse_args(argv)
    root = Path(args.root)
    if args.render:
        target = Path(args.render)
        if not target.is_absolute():
            target = root / target
        _, problems, planned = verify(root)
        if problems:
            print(f"❌ preflight-coverage: {len(problems)} problem(s)")
            for problem in problems:
                print(f"   - {problem}")
            return 1
        target.write_text(render(root), encoding="utf-8", newline="\n")
        print(f"wrote {target} ({len(planned)} planned item(s))")
        return 0
    items, problems, planned = verify(root)
    if not problems:
        problems += rendered_problems(root)
    if problems:
        print(f"❌ preflight-coverage: {len(problems)} problem(s)")
        for problem in problems:
            print(f"   - {problem}")
        return 1
    landed = sum(1 for row in items if not row.get("planned"))
    print(f"✅ preflight-coverage: {landed} preflight check(s) land on a contract row or a gate; "
          f"{len(planned)} still planned")
    for row in items:
        if row.get("planned"):
            print(f"   · planned: {row.get('what', '')[:70]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
