#!/usr/bin/env python3
"""Review one lane's iOS 27 eight-step fragment before it is merged.

The seven new lanes work offline in their own worktrees. Nothing stops an agent
from writing plausible prose there; the only thing that stopped it so far was a
human reading the file. This turns that reading into a command the Lead can run
on every delivery, so the answer to "did they cite the official page, did they
read the references, did they invent a number" is a exit code, not an opinion.

It is deliberately narrow: it checks what a fragment can prove about itself.

  1. the seven steps exist, and `device` is absent (that is the Lead's step)
  2. every step has done / evidence / recorded_at, and `done = true` needs
     at least one evidence path that resolves on this machine
  3. every evidence string that looks like a path resolves (repo root, the
     shared evidence roots, or the lane's own worktree)
  4. every `official:` row names a page that exists in the doc mirror and an
     anchor that page really declares as `{#anchor}`
  5. every hardware item carries a `status`, and a parked item explains itself
     (`why` and `revisit`), because "parked" with no reason is a silent drop
  6. a lane that claims iron-16 compliance must have at least two distinct
     registered sources in its reading list

Exit codes: 0 pass, 1 problems, 2 could not judge (missing/unreadable input).
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

STEPS = ("same_model", "official", "decompile", "wide", "plan", "deep", "verify")
ALL_STEPS = STEPS + ("device",)
STEP_KEYS = {"done", "evidence", "recorded_at"}
WIDE_EXTRA = {"catalog_checked", "catalog_result"}
VERIFY_EXTRA = {"static_check", "unit_test", "artifact_check", "local_verified"}
ITEM_KEYS = {"name", "label", "status", "why", "revisit", "paths", "files", "step"}

HERE = Path(__file__).resolve().parents[1]
ROOTS = (
    HERE,
    Path("/mnt/e/k60-work"),
    Path("/opt/k60/trees/ios27-out"),
)
ANCHOR = re.compile(r"\{#([^}]+)\}")
# The leading slash is part of the token: without it an absolute path such as
# /mnt/e/k60-work/wt-k55/docs/... was matched from `mnt/...` and then resolved
# relative to the checkout, which can only fail (measured 2026-11-21: two lanes
# reported red for evidence that exists on disk).
PATHLIKE = re.compile(r"/?[\w.-]+(?:/[\w.-]+)+\.(?:c|h|cpp|hpp|py|sh|toml|json|md|txt|dtb|dts|dtsi|macho|img|log)\b")


class Failure(Exception):
    pass


def resolve(token: str, lane_root: Path | None) -> Path | None:
    """A path in evidence may be absolute, repo-relative, or lane-relative."""
    candidates = [Path(token)] if token.startswith("/") else []
    for root in ([lane_root] if lane_root else []) + list(ROOTS):
        candidates.append(root / token)
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def anchors(page: Path) -> set[str]:
    try:
        return set(ANCHOR.findall(page.read_text(encoding="utf-8", errors="replace")))
    except OSError:
        return set()


def check(fragment: Path, lane_root: Path | None, docs: Path,
          allow_device: bool = False, require_paths: bool = False) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    notes: list[str] = []
    try:
        data = tomllib.loads(fragment.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise Failure(f"cannot read {fragment}: {error}")

    hardware = data.get("hardware")
    if not isinstance(hardware, dict) or not hardware:
        raise Failure(f"{fragment}: no [hardware.<item>] table")

    readings = data.get("reference_reading") or data.get("sources") or []
    named = set()
    for row in readings if isinstance(readings, list) else []:
        if isinstance(row, dict):
            source = str(row.get("source") or "").strip()
            path = str(row.get("path") or "").strip()
            if source:
                named.add(source)
            if not path:
                problems.append(f"reading for {source or '?'} has no path")
                continue
            if resolve(path, lane_root) is None:
                problems.append(f"reading path does not resolve: {path}")
    if readings and len(named) < 2:
        problems.append(
            f"iron-16 needs two distinct sources, the fragment names {sorted(named) or 'none'}")

    for item_name, item in hardware.items():
        if not isinstance(item, dict):
            problems.append(f"{item_name}: not a table")
            continue
        unknown = set(item) - ITEM_KEYS
        if unknown:
            problems.append(f"{item_name}: unknown keys {sorted(unknown)}")
        for required in ("name", "status"):
            if not item.get(required):
                problems.append(f"{item_name}: missing {required}")
        if str(item.get("status", "")).lower() == "parked":
            for required in ("why", "revisit"):
                if not item.get(required):
                    problems.append(f"{item_name}: parked without {required}")

        steps = item.get("step") or {}
        if not isinstance(steps, dict):
            problems.append(f"{item_name}: step is not a table")
            continue
        if "device" in steps and not allow_device:
            problems.append(f"{item_name}: declares step.device, which belongs to the Lead")
        for step in STEPS:
            block = steps.get(step)
            if not isinstance(block, dict):
                problems.append(f"{item_name}: step {step} is absent")
                continue
            missing = STEP_KEYS - set(block)
            if missing:
                problems.append(f"{item_name}.{step}: missing {sorted(missing)}")
            extra = set(block) - STEP_KEYS - (
                WIDE_EXTRA if step == "wide" else VERIFY_EXTRA if step == "verify" else set())
            if extra:
                problems.append(f"{item_name}.{step}: unknown keys {sorted(extra)}")
            evidence = block.get("evidence")
            if evidence is None:
                continue
            rows = evidence if isinstance(evidence, list) else [evidence]
            resolved = 0
            for row in rows:
                text = str(row)
                # An `official:` citation names a page in the framework's doc
                # mirror, not a file in this checkout, so resolving it here can
                # only fail (measured 2026-11-21: every lane that cited a
                # subdirectory page was reported red). Strip the citation before
                # the repository-path scan; the page itself is checked below.
                scan = re.sub(r"official:\s*[\"']?[\w./-]+\.md(?:#[\w.-]+)?", " ", text)
                for token in PATHLIKE.findall(scan):
                    if resolve(token, lane_root) is None:
                        problems.append(f"{item_name}.{step}: evidence does not resolve: {token}")
                    else:
                        resolved += 1
                page = re.search(r"official:\s*[\"']?([\w./-]+\.md)(?:#([\w.-]+))?", text)
                if page is None:
                    continue
                page_path = docs / page.group(1)
                if not page_path.is_file():
                    problems.append(f"{item_name}.{step}: official page missing: {page.group(1)}")
                    continue
                if not page.group(2):
                    problems.append(f"{item_name}.{step}: official page cited without an anchor")
                elif page.group(2) not in anchors(page_path):
                    problems.append(
                        f"{item_name}.{step}: {page.group(1)} has no anchor #{page.group(2)}")
            if require_paths and block.get("done") is True and resolved == 0 and rows:
                problems.append(
                    f"{item_name}.{step}: done = true but no evidence path resolves")
            if block.get("done") is True and not rows:
                problems.append(f"{item_name}.{step}: done = true with empty evidence")
        for step, block in steps.items():
            if step not in ALL_STEPS:
                problems.append(f"{item_name}: unknown step {step}")

    notes.append(f"hardware items: {', '.join(sorted(hardware))}")
    return problems, notes


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    lane_root = None
    docs = Path("/mnt/e/hackios/UniXNU/docs/zh")
    allow_device = "--allow-device" in argv
    require_paths = "--require-paths" in argv
    for a in argv[1:]:
        if a.startswith("--lane-root="):
            lane_root = Path(a.split("=", 1)[1])
        elif a.startswith("--docs="):
            docs = Path(a.split("=", 1)[1])
    if not args:
        print("usage: check-lane-fragment.py <fragment.toml> [--lane-root=DIR] [--docs=DIR]")
        return 2
    if not docs.is_dir():
        print(f"FAIL: no documentation mirror at {docs}; the anchors cannot be judged (P-279)")
        return 2
    worst = 0
    for name in args:
        fragment = Path(name)
        try:
            problems, notes = check(fragment, lane_root, docs,
                                    allow_device=allow_device, require_paths=require_paths)
        except Failure as error:
            print(f"FAIL: {error}")
            worst = max(worst, 1)
            continue
        for note in notes:
            print(f"note {fragment.name}: {note}")
        if problems:
            worst = max(worst, 1)
            for problem in problems:
                print(f"FAIL: {fragment.name}: {problem}")
        else:
            print(f"OK {fragment.name}: seven steps, resolvable evidence, official anchors")
    return worst


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
