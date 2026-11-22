#!/usr/bin/env python3
"""Judge the seven-step evidence of the four 27 power hardware blocks.

The canonical criterion for each block is CRITERIA below: one command, its expected
aggregate line, a negative self-test command and the precedent row.  The ledger carries
the same commands in its header comments; its shared schema has no criteria table.  This
checker reads the ledger and prints one line per step, then one aggregate line.  The aggregate distinguishes three states: PASS (offline evidence and
local verification complete), PENDING (offline evidence complete, no 27 image), and FAIL.
A block whose precedent starts with 无先例 prints precedent=NO-PRECEDENT, so a missing
success precedent cannot be mistaken for a green mechanism.

Exit: 0 every selected block is EVIDENCE PASS, 1 at least one block FAIL, 2 unusable input.
"""
from __future__ import annotations

import argparse
import copy
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "docs/research/eight-step/power-27.toml"
BLOCKS = ("battery", "charger", "power", "thermal")
STEPS = ("same_model", "official", "decompile", "wide", "plan", "deep", "verify")
CRITERIA = {
    "battery": {
        "cmd": "python3 scripts/check-power-27-criteria.py --block battery",
        "expect": "battery: EVIDENCE PASS 7/7 steps verify=PASS precedent=OK",
        "red_cmd": "python3 scripts/check-power-27-criteria.py --self-test --block battery",
        "red_expect": "SELF-TEST OK 9 case(s)",
        "precedent": "sheng（SM8550，已过 bsd_init）; sheng:package/ShengBattmgr.c:170-197；接收 owner/type/opcode 并维护 16 字段",
        "runs_when": "F2 27 镜像带 PongPower/Battery 后；先 C0 lease，再 C1 subscription，再 C2 四属性",
    },
    "charger": {
        "cmd": "python3 scripts/check-power-27-criteria.py --block charger",
        "expect": "charger: EVIDENCE PASS 7/7 steps verify=PASS precedent=OK",
        "red_cmd": "python3 scripts/check-power-27-criteria.py --self-test --block charger",
        "red_expect": "SELF-TEST OK 9 case(s)",
        "precedent": "sheng（SM8550）; sheng:package/ShengBattmgr.c:185-195；owner 检查、REQUEST 帧与通知路径",
        "runs_when": "同电池镜像；C1 subscription 绿后才读 C2/C3，轨/TCS4 只在 C3 后",
    },
    "power": {
        "cmd": "python3 scripts/check-power-27-criteria.py --block power",
        "expect": "power: EVIDENCE PASS 7/7 steps verify=PENDING precedent=NO-PRECEDENT",
        "red_cmd": "python3 scripts/check-power-27-criteria.py --self-test --block power",
        "red_expect": "SELF-TEST OK 9 case(s)",
        "precedent": "无先例：27 EPSS/L3 写路径没有成功先例；sheng:package/ShengPlatformPower.cpp:36-44 是 panic 负例，K60 16.6.1 w11 只读 mode-1 PASS 只算同板只读先例。",
        "runs_when": "F1 后只允许只读 EPSS 判据；写路径在拿到成功先例和 Lead 放行前不接线",
    },
    "thermal": {
        "cmd": "python3 scripts/check-power-27-criteria.py --block thermal",
        "expect": "thermal: EVIDENCE PASS 7/7 steps verify=PASS precedent=OK",
        "red_cmd": "python3 scripts/check-power-27-criteria.py --self-test --block thermal",
        "red_expect": "SELF-TEST OK 9 case(s)",
        "precedent": "sheng（SM8550）; sheng:package/ThermalProbe.cpp:1-27；只读温度，不写块、不取中断",
        "runs_when": "同镜像 TSENS 探针后；cold profile 全绿才跑 throttle profile",
    },
}
REF = re.compile(
    r"(?P<path>(?:[A-Za-z]:)?[A-Za-z0-9_./\\-]+\."
    r"(?:c|h|cpp|py|md|toml|patch|dts|sh|json|txt)):"
    r"(?P<start>[0-9]+)(?:-(?P<end>[0-9]+))?"
)


def nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def file_lines(path: Path) -> int | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)


def precedent_root(repo: str) -> Path | None:
    for base in (Path("E:/k60-work/references"), Path("/mnt/e/k60-work/references")):
        candidate = base / f"UniXNU-{repo}"
        if candidate.is_dir():
            return candidate
    return None


def check_precedent(text: str) -> list[str]:
    match = re.search(
        r"(?P<repo>[A-Za-z0-9_-]+):(?P<path>[A-Za-z0-9_./-]+\."
        r"(?:c|h|cpp|py|md)):(?P<line>[0-9]+)(?:-(?P<end>[0-9]+))?",
        text,
    )
    if not match:
        return ["precedent has no repo:file:line"]
    repo = match.group("repo")
    root = precedent_root(repo)
    if root is None:
        return [f"precedent root not found for {repo!r}"]
    path = root / match.group("path")
    if not path.exists():
        return [f"precedent file missing: {path}"]
    total = file_lines(path)
    if total is None:
        return [f"precedent file unreadable: {path}"]
    end = int(match.group("end") or match.group("line"))
    if end > total:
        return [f"precedent line {end} outside {total}: {match.group('path')}"]
    required = None
    for base in (ROOT, Path("E:/hackios/k60-gates"), Path("/mnt/e/hackios/k60-gates")):
        candidate = base / "docs/research/ios27/PRECEDENT-REQUIRED.md"
        if candidate.exists():
            required = candidate
            break
    if required is None:
        return ["cannot find docs/research/ios27/PRECEDENT-REQUIRED.md"]
    try:
        listed = required.read_text(encoding="utf-8")
    except OSError:
        return [f"cannot read {required}"]
    if repo not in listed:
        return [f"precedent repo {repo!r} is not listed in PRECEDENT-REQUIRED.md"]
    return []


def resolve(raw: str) -> Path:
    raw = raw.replace("\\", "/")
    if raw.startswith("/mnt/e/"):
        return Path("E:/" + raw[len("/mnt/e/"):])
    if re.match(r"^[A-Za-z]:/", raw):
        return Path(raw)
    if raw.startswith("/"):
        return Path(raw)
    return ROOT / raw


def check_refs(text: str) -> list[str]:
    matches = list(REF.finditer(text))
    if not matches:
        return ["no file:line reference"]
    errors: list[str] = []
    for match in matches:
        raw = match.group("path")
        path = resolve(raw)
        if not path.exists():
            errors.append(f"missing {raw}")
            continue
        if path.is_dir():
            errors.append(f"is a directory: {raw}")
            continue
        total = file_lines(path)
        if total is None:
            errors.append(f"cannot read {raw}")
            continue
        start = int(match.group("start"))
        end = int(match.group("end") or start)
        if start < 1 or end < start or end > total:
            errors.append(f"{raw}:{start}-{end} outside {total} line(s)")
    return list(dict.fromkeys(errors))


def check_step(block: dict, name: str, step: dict) -> list[str]:
    evidence = step.get("evidence")
    if not nonempty(evidence):
        return ["evidence is empty"]
    errors = check_refs(evidence)
    if name == "official" and "power.md" not in evidence:
        errors.append("official evidence does not cite power.md")
    if name == "wide":
        if step.get("catalog_checked") is not True:
            errors.append("catalog_checked is not true")
        if not nonempty(step.get("catalog_result")):
            errors.append("catalog_result is empty")
    if name == "plan":
        paths = block.get("paths")
        if not isinstance(paths, list) or not paths:
            errors.append("paths is empty")
        else:
            for item in paths:
                if not (ROOT / str(item)).exists():
                    errors.append(f"path does not exist: {item}")
    if name == "verify":
        for field in ("static_check", "unit_test", "artifact_check"):
            if not nonempty(step.get(field)):
                errors.append(f"{field} is empty")
        if not isinstance(step.get("local_verified"), bool):
            errors.append("local_verified is not a boolean")
    elif step.get("done") is not True:
        errors.append("done is not true")
    return list(dict.fromkeys(errors))


def check_criteria(block_name: str) -> list[str]:
    criteria = CRITERIA[block_name]
    errors: list[str] = []
    for field in ("cmd", "expect", "red_cmd", "red_expect", "precedent", "runs_when"):
        if not nonempty(criteria.get(field)):
            errors.append(f"criteria.{field} is empty")
    cmd = str(criteria.get("cmd", ""))
    red_cmd = str(criteria.get("red_cmd", ""))
    if f"--block {block_name}" not in cmd:
        errors.append(f"criteria.cmd does not name --block {block_name}")
    if f"--block {block_name}" not in red_cmd:
        errors.append(f"criteria.red_cmd does not name --block {block_name}")
    if "EVIDENCE PASS 7/7" not in str(criteria.get("expect", "")):
        errors.append("criteria.expect does not name EVIDENCE PASS 7/7")
    if "SELF-TEST OK 9" not in str(criteria.get("red_expect", "")):
        errors.append("criteria.red_expect does not name SELF-TEST OK 9")
    precedent = str(criteria.get("precedent", ""))
    if not precedent.startswith("无先例"):
        errors.extend(check_precedent(precedent))
    return list(dict.fromkeys(errors))


def expectation_error(block_name: str, aggregate: str) -> str | None:
    expected = CRITERIA[block_name]["expect"]
    if aggregate == expected:
        return None
    return f"expected {expected!r}, got {aggregate!r}"


def run_block(block_name: str, block: dict) -> bool:
    criteria = CRITERIA[block_name]
    criteria_errors = check_criteria(block_name)
    if criteria_errors:
        print(f"{block_name}/criteria FAIL " + "; ".join(criteria_errors))
    step_errors = {
        name: check_step(block, name, block.get("step", {}).get(name, {}))
        for name in STEPS
    }
    verify = block.get("step", {}).get("verify", {})
    valid = 0
    for name in STEPS:
        errors = step_errors[name]
        if errors:
            print(f"{block_name}/{name} FAIL " + "; ".join(errors))
            continue
        valid += 1
        if name == "verify":
            if verify.get("local_verified") is True:
                print(f"{block_name}/{name} PASS local_verified=true")
            else:
                print(f"{block_name}/{name} PENDING local_verified=false")
        elif name == "wide":
            print(f"{block_name}/{name} PASS catalog=checked")
        elif name == "plan":
            print(f"{block_name}/{name} PASS paths={len(block.get('paths', []))}")
        else:
            print(f"{block_name}/{name} PASS")
    if valid == len(STEPS):
        verify_state = "PASS" if verify.get("local_verified") is True else "PENDING"
    else:
        verify_state = "FAIL"
    precedent = criteria["precedent"]
    precedent_state = "NO-PRECEDENT" if precedent.startswith("无先例") else "OK"
    ok = not criteria_errors and all(not errors for errors in step_errors.values())
    aggregate = (
        f"{block_name}: EVIDENCE {'PASS' if ok else 'FAIL'} "
        f"{valid}/7 steps verify={verify_state} precedent={precedent_state}"
    )
    print(aggregate)
    mismatch = expectation_error(block_name, aggregate)
    if mismatch:
        print(f"{block_name}/criteria FAIL {mismatch}")
        ok = False
    return ok


def self_test(block_name: str, block: dict) -> int:
    failures = 0
    for name in STEPS:
        mutated = copy.deepcopy(block)
        mutated.setdefault("step", {}).setdefault(name, {})["evidence"] = ""
        errors = check_step(mutated, name, mutated["step"][name])
        if not errors:
            print(f"SELF-TEST FAIL {block_name}/{name} did not go red")
            failures += 1
        else:
            print(f"SELF-TEST {block_name}/{name} red: {errors[0]}")
    aggregate = CRITERIA[block_name]["expect"] + " [mutated]"
    mismatch = expectation_error(block_name, aggregate)
    if mismatch is None:
        print(f"SELF-TEST FAIL {block_name}/expectation did not go red")
        failures += 1
    else:
        print(f"SELF-TEST {block_name}/expectation red: {mismatch}")
    precedent_error = check_precedent("sheng:package/ShengBattmgr.c:9999")
    if not precedent_error:
        print(f"SELF-TEST FAIL {block_name}/precedent did not go red")
        failures += 1
    else:
        print(f"SELF-TEST {block_name}/precedent red: {precedent_error[0]}")
    if failures:
        return 1
    print(f"SELF-TEST OK {len(STEPS) + 2} case(s)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", default=str(LEDGER), help="power-27.toml path")
    parser.add_argument("--block", choices=BLOCKS, help="one hardware block")
    parser.add_argument("--self-test", action="store_true", help="empty each step, then mismatch the expected aggregate")
    args = parser.parse_args()

    ledger = Path(args.ledger)
    if not ledger.is_absolute():
        ledger = ROOT / ledger
    try:
        data = tomllib.loads(ledger.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        print(f"power-27-criteria: cannot read {ledger}: {exc}")
        return 2
    hardware = data.get("hardware")
    if not isinstance(hardware, dict):
        print(f"power-27-criteria: {ledger} has no [hardware] table")
        return 2

    chosen = [args.block] if args.block else list(BLOCKS)
    missing = [name for name in chosen if not isinstance(hardware.get(name), dict)]
    if missing:
        print(f"power-27-criteria: missing hardware block(s): {', '.join(missing)}")
        return 2

    if args.self_test:
        status = 0
        for name in chosen:
            status = self_test(name, hardware[name]) or status
        return status

    status = 0
    for name in chosen:
        if not run_block(name, hardware[name]):
            status = 1
    print(f"OK power-27-criteria: {len(chosen)} hardware item(s), {len(chosen) * len(STEPS)} step(s) checked")
    return status


if __name__ == "__main__":
    sys.exit(main())
