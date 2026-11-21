#!/usr/bin/env python3
"""Offline test for the iOS 27 "13 silent" prelink set.

Checks the machine-readable copy of the 13 pointer slots that are dereferenced
inside the prelink early security initializer, against three independent
sources:

  * docs/research/ios27/osservices-27-silent13.toml   (this line's table)
  * the prelink audit  unreachable.toml               (classify.py report)
  * the build artefacts kernel.json / kernel.map.json (emitter output)

No build, no device: everything is a read of files that already exist.

Usage (paths default to this line's layout):

    python3 scripts/check-osservices27-silent13.py                 # table only
    python3 scripts/check-osservices27-silent13.py --strict        # + artefacts
    python3 scripts/check-osservices27-silent13.py --strict \\
        --unreachable E:/k60-work/scratch/stubs/unreachable.toml \\
        --kernel-json /opt/k60/trees/.../kernel/kernel.json \\
        --kernel-map  /opt/k60/trees/.../kernel/kernel.map.json

kernel.json / kernel.map.json are written by the build as root (mode 600), so
under WSL the strict run needs `wsl -u root`.  Exit status 0 means every case
passed; 1 means at least one did not.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_TABLE = REPO / "docs/research/ios27/osservices-27-silent13.toml"
# The audit lives outside the repository; give both the Windows and the WSL
# spelling of the same file so one default works from either side.
UNREACHABLE_CANDIDATES = (
    Path("E:/k60-work/scratch/stubs/unreachable.toml"),
    Path("/mnt/e/k60-work/scratch/stubs/unreachable.toml"),
)
DEFAULT_KERNEL_DIR = Path(
    "/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/kernel"
)

EXPECTED_ITEMS = {"0xfffffff00b4320d8": 5, "0xfffffff00b432308": 5, "0xfffffff00b11a998": 3}
EXPECTED_BUNDLES = {"0xfffffff00b4320d8": 5, "0xfffffff00b432308": 5, "0xfffffff00b11a998": 3}
EXPECTED_SIZE = {"0xfffffff00b4320d8": 28, "0xfffffff00b432308": 664, "0xfffffff00b11a998": 240}
EXPECTED_ANCHOR_PREV = {
    "0xfffffff00b4320d8": ("0xfffffff00b431f70", "_get_arm_cpu_version", 0x168),
    "0xfffffff00b432308": ("0xfffffff00b431f70", "_get_arm_cpu_version", 0x398),
    "0xfffffff00b11a998": ("0xfffffff00b11a890", "_code_signing_deallocate", 0x108),
}
EXPECTED_ANCHOR_NEXT = {
    "0xfffffff00b11a998": ("0xfffffff00b11aa88", "_disable_code_signing_feature", 0xF0),
}
AMFI = "com.apple.driver.AppleMobileFileIntegrity"
NON_BASELINE_BUNDLES = {AMFI: 3, "com.apple.security.sandbox": 2}

failures: list[str] = []
cases = 0


def check(condition: bool, label: str, detail: str = "") -> None:
    global cases
    cases += 1
    if condition:
        print(f"ok   - {label}")
        return
    message = f"FAIL - {label}" + (f": {detail}" if detail else "")
    print(message)
    failures.append(message)


def load_toml(path: Path) -> dict:
    with open(path, "rb") as handle:
        return tomllib.load(handle)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    parser.add_argument("--unreachable", type=Path, default=None,
                        help="prelink audit table (default: first existing candidate path)")
    parser.add_argument("--kernel-json", type=Path, default=DEFAULT_KERNEL_DIR / "kernel.json")
    parser.add_argument("--kernel-map", type=Path, default=DEFAULT_KERNEL_DIR / "kernel.map.json")
    parser.add_argument("--strict", action="store_true", help="require the audit and build artefacts")
    args = parser.parse_args(argv)
    if args.unreachable is None:
        args.unreachable = next(
            (p for p in UNREACHABLE_CANDIDATES if p.exists()), UNREACHABLE_CANDIDATES[0]
        )

    table = load_toml(args.table)
    slots = table.get("slot", [])
    targets = {t["address"]: t for t in table.get("target", [])}

    # --- 1. the table itself -------------------------------------------------
    check(len(slots) == 13, "table lists 13 slots", f"got {len(slots)}")
    check([s["id"] for s in slots] == list(range(1, 14)), "slot ids are 1..13 in order")
    sites = [s["site"] for s in slots]
    check(len(set(sites)) == 13, "slot sites are unique", f"{len(sites) - len(set(sites))} duplicate(s)")
    check(all(s["target"] in targets for s in slots), "every slot points at a described target")
    per_target_items = {t: sum(1 for s in slots if s["target"] == t) for t in targets}
    check(per_target_items == EXPECTED_ITEMS, "items per target are 5/5/3", str(per_target_items))
    per_target_bundles = {
        t: len({s["bundle"] for s in slots if s["target"] == t}) for t in targets
    }
    check(per_target_bundles == EXPECTED_BUNDLES, "bundles per target are 5/5/3", str(per_target_bundles))
    check(
        {t: targets[t]["size"] for t in targets} == EXPECTED_SIZE,
        "target sizes are 28/664/240",
        str({t: targets[t]["size"] for t in targets}),
    )

    # --- 2. baseline is bundle level, and the split is 8/5 --------------------
    flags = [s["baseline"] for s in slots]
    check(flags.count(True) == 8 and flags.count(False) == 5, "baseline split is 8 true / 5 false")
    non_baseline = [s["bundle"] for s in slots if not s["baseline"]]
    counts = {b: non_baseline.count(b) for b in set(non_baseline)}
    check(counts == NON_BASELINE_BUNDLES, "the 5 non-baseline slots are AMFI 3 + sandbox 2", str(counts))

    # --- 3. against the prelink audit ---------------------------------------
    need_audit = args.strict or args.unreachable.exists()
    if need_audit:
        if not args.unreachable.exists():
            check(False, f"audit present: {args.unreachable}")
        else:
            audit = load_toml(args.unreachable)
            rows = [r for r in audit.get("target", []) if "early_security_init" in r.get("reason", "")]
            check(len(rows) == 13, "audit has 13 early-security rows", f"got {len(rows)}")
            audit_triples = {(r["bundle"], r["target"], r["site"]) for r in rows}
            mine = {(s["bundle"], s["target"], s["site"]) for s in slots}
            check(audit_triples == mine, "table triples equal the audit triples",
                  f"only-audit {sorted(audit_triples - mine)} only-table {sorted(mine - audit_triples)}")
            check(all(r["kind"] == "__auth_got" for r in rows), "all 13 slots are __auth_got")
            check(
                all(set(r) >= {"bundle", "target", "kind", "site", "verdict", "stage", "baseline", "reason"}
                    for r in rows),
                "audit rows carry the documented fields",
            )
    else:
        print(f"skip - audit not found at {args.unreachable}")

    # --- 4. against the build artefacts --------------------------------------
    if args.strict:
        for path in (args.kernel_json, args.kernel_map):
            check(path.exists(), f"artefact present: {path}")
        if args.kernel_json.exists():
            kj = json.loads(args.kernel_json.read_text())
            stubbed, missing = kj["stubbed"], kj["missing"]
            stub_items = sum(len(v) for v in stubbed.values())
            miss_items = sum(len(v) for v in missing.values())
            check(stub_items == 203 and len(stubbed) == 25,
                  "kernel.json: 203 stubbed items in 25 bundles", f"{stub_items}/{len(stubbed)}")
            check(miss_items == 3 and len(missing) == 3,
                  "kernel.json: 3 missing items in 3 bundles", f"{miss_items}/{len(missing)}")
            declared = table["declared"]
            check(declared == {"slots": 205, "targets": 203, "bundles": 25, "missing": 3, "stubbed": 203},
                  "declared counts keep 205 and 203 side by side", str(declared))
            for slot in slots:
                bundle, target = slot["bundle"], slot["target"]
                check(target in stubbed.get(bundle, {}),
                      f"slot {slot['id']}: {bundle} stubs {target}")
            check(all(t not in missing.get(b, {}) for s in slots for b, t in [(s["bundle"], s["target"])]),
                  "no slot target is reported as missing")
            esi = kj["early_security_init"]
            check(esi == {AMFI: "0xfffffff00921000c"},
                  "early_security_init is AMFI=0xfffffff00921000c", str(esi))
            check(kj["collection_slide"] == "0x0" if isinstance(kj["collection_slide"], str)
                  else kj["collection_slide"] == 0, "collection_slide is 0 (targets are unslid)")
            check(kj["mapping_complete"] is False,
                  "mapping_complete is False (stubs are a known-open state)")
        if args.kernel_map.exists():
            km = json.loads(args.kernel_map.read_text())
            functions = {int(k, 16): v for k, v in km["functions"].items()}
            highest = max(functions)
            for address in targets:
                check(int(address, 16) not in functions, f"target {address} absent from kernel.map functions")
            for address, (anchor, name, delta) in EXPECTED_ANCHOR_PREV.items():
                prev = int(anchor, 16)
                got = functions.get(prev)
                check(got is not None and got["name"] == name,
                      f"anchor {anchor} is {name}", str(got))
                check(int(address, 16) - prev == delta,
                      f"target {address} is +0x{delta:x} above {name}")
            for address, (anchor, name, delta) in EXPECTED_ANCHOR_NEXT.items():
                nxt = int(anchor, 16)
                got = functions.get(nxt)
                check(got is not None and got["name"] == name,
                      f"next anchor {anchor} is {name}", str(got))
                check(nxt - int(address, 16) == delta,
                      f"target {address} is -0x{delta:x} below {name}")
            for address in ("0xfffffff00b4320d8", "0xfffffff00b432308"):
                check(int(address, 16) > highest,
                      f"target {address} sits above the last matched function (0x{highest:x})")

    print()
    if failures:
        print(f"TESTS FAILED {len(failures)}/{cases} cases")
        return 1
    print(f"TESTS OK {cases} cases")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
