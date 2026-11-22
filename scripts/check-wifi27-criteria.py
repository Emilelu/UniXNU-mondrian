#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Read the seven offline Wi-Fi 27 criteria as one canonical line each.

Each step has a fixed list of facts.  The command prints exactly
``<step>: <present>/<required> present`` and, on a red input, appends
``; missing=<comma-separated-fact-names>``.  Exit 0 means every required
fact was read; exit 1 means the reading is red; exit 2 means the checker
could not read its fixture or arguments.

This is a file/evidence reader, not a build or boot probe.  A fixture is a
JSON object ``{"present": ["fact", ...]}`` used by the negative self-tests.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

STEPS = (
    "same_model",
    "official",
    "decompile",
    "wide",
    "plan",
    "deep",
    "verify",
)

REQUIRED = {
    "same_model": (
        "pci:17cb:1103",
        "bar0:0x60200000",
        "subsys:0x0108",
        "dts:wlan",
    ),
    "official": (
        "page:network.md",
        "page:ath12k-wifi.md",
        "page:platform.md",
        "page:drivers.md",
        "board:SM8475",
        "board:ios-27.0.1-24A446",
    ),
    "decompile": (
        "sheng:C3",
        "sheng:L0",
        "sheng:L1b",
        "mission:wifid",
        "mission:20G81",
    ),
    "wide": (
        "catalog:Ath12kWifi",
        "catalog:qcc2072",
        "catalog:wcn7850",
        "research:QCA6490",
    ),
    "plan": (
        "checklist:B",
        "checklist:C",
        "wpa3:blocked_by-F2/F3",
        "porting:network-planned",
    ),
    "deep": (
        "mission:section65",
        "mission:section68",
        "mission:section69",
        "gap:closing-conditions",
        "sheng:C3",
    ),
    "verify": (
        "script:station-archive",
        "test:station-archive",
        "script:link-inputs",
        "test:link-inputs",
        "script:b4-exports",
    ),
}


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def has(text: str, needle: str) -> bool:
    return needle.casefold() in text.casefold()


def default_external(root: Path) -> Path:
    candidates: list[Path] = []
    configured = os.environ.get("K60_UNIXNU")
    if configured:
        candidates.append(Path(configured))
    candidates.extend([
        root.parent / "UniXNU",
        Path("E:/hackios/UniXNU"),
        Path("/mnt/e/hackios/UniXNU"),
    ])
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


def collect(root: Path, external: Path) -> set[str]:
    research = read_text(root / "docs/research/wifi/RESEARCH.md")
    dts = read_text(root / "dts/mondrian.dts")
    sheng = read_text(root / "docs/research/wifi/SHENG-KERNEL-REFERENCE.md")
    mission = read_text(root / "docs/research/wifi/SBL-MISSION.md")
    gap = read_text(root / "docs/research/wifi/IOS27-STATION-API-GAP.md")
    checklist = read_text(root / "docs/plans/WIFI-IOS27-CHECKLIST.md")
    wpa3 = read_text(root / "docs/research/wifi/WPA3-PORT-PLAN.md")
    porting = read_text(root / "porting.toml")
    board = read_text(root / "board.toml")
    components = read_text(external / "components.toml")
    present: set[str] = set()

    if has(research, "17CB:1103"):
        present.add("pci:17cb:1103")
    if has(research, "0x60200000"):
        present.add("bar0:0x60200000")
    if has(research, "0x0108"):
        present.add("subsys:0x0108")
    if has(dts, "wlan"):
        present.add("dts:wlan")

    for name in ("network.md", "ath12k-wifi.md", "platform.md", "drivers.md"):
        if (external / "docs/zh/porting" / name).is_file() or (external / "docs/zh/drivers" / name).is_file():
            present.add("page:" + name)
    if "SM8475" in board:
        present.add("board:SM8475")
    if "ios-27.0.1-24A446" in board:
        present.add("board:ios-27.0.1-24A446")

    if "C3" in sheng:
        present.add("sheng:C3")
    if "L0" in sheng:
        present.add("sheng:L0")
    if "L1b" in sheng:
        present.add("sheng:L1b")
    if "wifid" in mission.casefold():
        present.add("mission:wifid")
    if "20G81" in mission:
        present.add("mission:20G81")

    if "Ath12kWifi" in components:
        present.add("catalog:Ath12kWifi")
    if "qcc2072" in components:
        present.add("catalog:qcc2072")
    if "wcn7850" in components:
        present.add("catalog:wcn7850")
    if "QCA6490" in research:
        present.add("research:QCA6490")

    if re.search(r"^## B\.", checklist, re.MULTILINE):
        present.add("checklist:B")
    if re.search(r"^## C\.", checklist, re.MULTILINE):
        present.add("checklist:C")
    if "blocked_by: F2/F3" in wpa3:
        present.add("wpa3:blocked_by-F2/F3")
    if re.search(r"\[\[area\]\]\s*\n\s*id = \"network\"\s*\n\s*status = \"planned\"", porting):
        present.add("porting:network-planned")

    if "## 65" in mission:
        present.add("mission:section65")
    if "## 68" in mission:
        present.add("mission:section68")
    if "## 69" in mission:
        present.add("mission:section69")
    if "关闭条件" in gap:
        present.add("gap:closing-conditions")

    files = {
        "script:station-archive": "scripts/check-wifi-station-archive.py",
        "test:station-archive": "scripts/tests/test-wifi-station-archive.py",
        "script:link-inputs": "scripts/check-wifi27-link-inputs.py",
        "test:link-inputs": "scripts/tests/test-wifi27-link-inputs.py",
        "script:b4-exports": "scripts/check-wifi-b4-exports.py",
    }
    for fact, rel in files.items():
        if (root / rel).is_file():
            present.add(fact)

    return present


def reading(step: str, present: set[str], required: tuple[str, ...]) -> tuple[str, bool]:
    missing = [fact for fact in required if fact not in present]
    line = "%s: %d/%d present" % (step, len(required) - len(missing), len(required))
    if missing:
        line += "; missing=" + ",".join(missing)
    return line, not missing


def main(argv: list[str] | None = None) -> int:
    root_default = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step", required=True, choices=STEPS)
    parser.add_argument("--root", type=Path, default=root_default)
    parser.add_argument("--external-root", type=Path, default=None)
    parser.add_argument("--fixture", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.fixture is not None:
        try:
            payload = json.loads(args.fixture.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print("FAIL fixture: %s: %s" % (args.fixture, exc), file=sys.stderr)
            return 2
        if not isinstance(payload, dict) or not isinstance(payload.get("present"), list):
            print("FAIL fixture: %s: expected an object with a present list" % args.fixture, file=sys.stderr)
            return 2
        present = {str(item) for item in payload["present"]}
    else:
        external = args.external_root or default_external(args.root)
        present = collect(args.root, external)

    line, ok = reading(args.step, present, REQUIRED[args.step])
    print(line)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
