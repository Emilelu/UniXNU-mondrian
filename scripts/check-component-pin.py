#!/usr/bin/env python3
"""Check that every component board.toml builds against matches the catalog pin,
or that docs/engineering/COMPONENT-PINS.toml records why it does not (hard-40).

The catalog (UniXNU/components.toml) names a revision per component. Our build can
drift from it in two ways: the framework submodule sits on an older commit, or a
reference tree used for porting is at a different commit. Either is fine only when
written down; silent drift is what hid the ShengUfs difference.

Board components are hard-checked. Other components that happen to have a local
tree are printed as informational warnings (the catalog covers the whole fleet).
"""
from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

REPO = Path(os.environ.get("K60_REPO") or Path(__file__).resolve().parents[1])
FRAMEWORK = Path(os.environ.get("K60_FRAMEWORK_REPO") or REPO.parent / "UniXNU")
REFERENCES = Path(os.environ.get("K60_REFERENCE_ROOT") or "/mnt/e/iOS Port/Work/references")
PINS = REPO / "docs" / "engineering" / "COMPONENT-PINS.toml"


def git(args, cwd):
    return subprocess.check_output(["git", "-C", str(cwd)] + args, text=True,
                                   stderr=subprocess.DEVNULL).strip()


def load_catalog():
    path = FRAMEWORK / "components.toml"
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return {entry["id"]: entry for entry in data.get("component", [])}


def load_board():
    data = tomllib.loads((REPO / "board.toml").read_text(encoding="utf-8"))
    return list(data.get("components", {}).get("include", []))


def load_deviations():
    if not PINS.exists():
        return []
    data = tomllib.loads(PINS.read_text(encoding="utf-8"))
    return list(data.get("deviation", []))


def resolve_local(entry):
    """Return (path, revision, how) for the tree we actually use, or None."""
    path = entry.get("path")
    if path:
        work = FRAMEWORK / path
        if (work / ".git").exists():
            try:
                return work, git(["rev-parse", "HEAD"], work), "worktree"
            except subprocess.CalledProcessError:
                pass
        try:
            line = git(["ls-tree", "HEAD", "--", path], FRAMEWORK)
            if line:
                return work, line.split()[2], "gitlink"
        except subprocess.CalledProcessError:
            pass
    # components without a path in the framework: look for the reference tree we
    # keep under E:/iOS Port/Work/references (ShengUfs, pong-ufs, ...)
    names = [entry["id"], entry["id"].lower(),
             entry["id"].replace("Pong", "pong-").lower()]
    for name in names:
        cand = REFERENCES / name
        if (cand / ".git").exists():
            return cand, git(["rev-parse", "HEAD"], cand), "reference"
    return None


def main() -> int:
    if not (FRAMEWORK / "components.toml").exists():
        print(f"check-component-pin: no catalog at {FRAMEWORK / 'components.toml'}")
        return 1
    catalog = load_catalog()
    board = load_board()
    deviations = load_deviations()
    by_component = {}
    for dev in deviations:
        by_component.setdefault(dev.get("component"), []).append(dev)

    problems = []
    used = set()
    checked = 0
    for cid in board:
        entry = catalog.get(cid)
        if entry is None:
            problems.append(f"board.toml 引用了 catalog 里没有的组件 {cid}")
            continue
        local = resolve_local(entry)
        if local is None:
            problems.append(f"{cid}: 找不到本地树，无法验证 pin（catalog {entry.get('revision','?')[:8]}）")
            continue
        checked += 1
        path, revision, how = local
        used.add(cid)
        devs = by_component.get(cid, [])
        match = [d for d in devs if d.get("our_revision") == revision]
        if revision != entry.get("revision") and not match:
            problems.append(
                f"{cid}: catalog {entry.get('revision','?')[:8]} != {how} {revision[:8]} ({path})，"
                f"未在 {PINS.relative_to(REPO)} 里说明")
        if revision == entry.get("revision") and devs:
            problems.append(f"{cid}: 已与 catalog 一致，删除 COMPONENT-PINS.toml 里的 deviation")
    for cid in by_component:
        if cid not in used:
            problems.append(f"COMPONENT-PINS.toml 里的 {cid} 不是 board 组件")

    # informational: other catalog components with a local tree
    other = []
    for cid, entry in catalog.items():
        if cid in used:
            continue
        local = resolve_local(entry)
        if local and local[1] != entry.get("revision"):
            other.append((cid, entry.get("revision", "?")[:8], local[1][:8], local[2]))

    print(f"check-component-pin: board 组件 {checked} 个，deviations {len(deviations)} 条")
    for cid, cat, ours, how in other:
        print(f"  ℹ {cid}: catalog {cat} != {how} {ours}")
    if problems:
        print("❌ " + "\n❌ ".join(problems))
        return 1
    print("✅ board 组件全部有据可查")
    return 0


if __name__ == "__main__":
    sys.exit(main())
