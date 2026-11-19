#!/usr/bin/env python3
"""Check the iOS 27 power carry manifest.

The seven pure C modules behind the power page are the only assets that cross the
iOS 16 -> iOS 27 boundary unchanged. This gate keeps that promise checkable:

  * every listed file exists and still hashes to the recorded sha256;
  * the host suite that pins the module still records the same number of asserts
    in scripts/tests/run-k60-power-host.sh (a suite that silently loses cases is
    the failure mode P-204 warns about);
  * scripts/check-power-portability.py still compiles the module freestanding;
  * with --target, the copy in another checkout (E:/hackios/xnekom-ios27) is
    compared file by file, so a carry that dropped or edited one file is caught
    before it reaches a build;
  * every listed judge is compilable and its fixture suite still prints the
    recorded number of cases (a judge whose fixtures shrank reads a real console
    the way P-204 warns about: green, and blind).

No device access, no MMIO, no network.

usage:
  python3 scripts/check-power-carry.py                     # verify this tree
  python3 scripts/check-power-carry.py --target <tree>     # compare a copy
  python3 scripts/check-power-carry.py --update            # refresh hashes
exit: 0 ok, 1 problems, 2 manifest unusable
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import tomllib
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

MANIFEST = Path("docs/research/power/CARRY.toml")
RUNNER = Path("scripts/tests/run-k60-power-host.sh")
PORTABILITY = Path("scripts/check-power-portability.py")
RUN_RE = re.compile(r"^run\s+(?P<suite>\S+)\s+(?P<checks>\d+)\s")
CASES_RE = re.compile(r"TESTS OK\s+(?P<cases>\d+)\s+(?:case|check)")


def repo_root() -> Path:
    env = os.environ.get("K60_REPO")
    return Path(env).resolve() if env else Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def suite_counts(runner: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not runner.is_file():
        return counts
    for line in runner.read_text(encoding="utf-8", errors="replace").splitlines():
        match = RUN_RE.match(line)
        if match:
            counts[match.group("suite")] = int(match.group("checks"))
    return counts


def load_manifest(root: Path) -> dict:
    path = root / MANIFEST
    return tomllib.loads(path.read_text(encoding="utf-8"))


def modules(manifest: dict) -> list[dict]:
    return list(manifest.get("module") or [])


def judges(manifest: dict) -> list[dict]:
    return list(manifest.get("judge") or [])


def fixture_cases(root: Path, test: str) -> int | None:
    """Run one fixture suite and return the case count it printed, or None."""
    import subprocess

    try:
        done = subprocess.run(
            [sys.executable, str(root / test)],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=dict(os.environ, PYTHONIOENCODING="utf-8"),
            timeout=600,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    found = CASES_RE.findall(done.stdout or "")
    return int(found[-1]) if found else None


def verify(root: Path, manifest: dict, update: bool) -> tuple[list[str], list[str]]:
    """Return (rows, problems) for the manifest against this tree."""
    rows: list[str] = []
    problems: list[str] = []
    counts = suite_counts(root / RUNNER)
    portability = ""
    if (root / PORTABILITY).is_file():
        portability = (root / PORTABILITY).read_text(encoding="utf-8", errors="replace")
    else:
        problems.append(f"{PORTABILITY}: missing")
    seen: dict[str, str] = {}
    for entry in modules(manifest):
        name = str(entry.get("name") or "?")
        suite = str(entry.get("suite") or "")
        checks = entry.get("checks")
        test = str(entry.get("test") or "")
        files = list(entry.get("files") or [])
        if not files:
            problems.append(f"{name}: lists no files")
        if not test:
            problems.append(f"{name}: names no test")
        elif not (root / test).is_file():
            problems.append(f"{name}: test {test} is missing")
        if suite not in counts:
            problems.append(f"{name}: suite '{suite}' is not run by {RUNNER}")
        elif checks != counts[suite]:
            problems.append(
                f"{name}: manifest says {checks} checks, {RUNNER} runs {counts[suite]}"
            )
        for item in files:
            rel = str(item.get("path") or "")
            want = str(item.get("sha256") or "")
            if not rel:
                problems.append(f"{name}: a file entry has no path")
                continue
            if rel in seen:
                problems.append(f"{name}: {rel} is already claimed by {seen[rel]}")
            seen[rel] = name
            path = root / rel
            if not path.is_file():
                problems.append(f"{name}: {rel} is missing")
                continue
            if not rel.endswith(".h") and portability and Path(rel).name not in portability:
                problems.append(
                    f"{name}: {Path(rel).name} is not in the portability module list"
                )
            got = sha256_file(path)
            if update:
                item["sha256"] = got
                want = got
            if want and got != want:
                problems.append(f"{name}: {rel} changed (sha256 {got[:12]} != {want[:12]})")
        rows.append(f"OK   {name:<20} suite={suite:<12} checks={checks} files={len(files)}")
    for entry in judges(manifest):
        name = str(entry.get("name") or "?")
        rel = str(entry.get("path") or "")
        want = str(entry.get("sha256") or "")
        cases = entry.get("cases")
        test = str(entry.get("test") or "")
        if not rel:
            problems.append(f"judge {name}: names no path")
            continue
        path = root / rel
        if not path.is_file():
            problems.append(f"judge {name}: {rel} is missing")
            continue
        if not test:
            problems.append(f"judge {name}: names no test")
        elif not (root / test).is_file():
            problems.append(f"judge {name}: test {test} is missing")
        try:
            compile(path.read_text(encoding="utf-8", errors="replace"), rel, "exec")
        except SyntaxError as error:
            problems.append(f"judge {name}: {rel} does not compile ({error.msg})")
        got = sha256_file(path)
        if update:
            entry["sha256"] = got
            want = got
        if want and got != want:
            problems.append(f"judge {name}: {rel} changed (sha256 {got[:12]} != {want[:12]})")
        if test and (root / test).is_file():
            seen_cases = fixture_cases(root, test)
            if seen_cases is None:
                problems.append(f"judge {name}: {test} printed no 'TESTS OK N cases/checks' line")
            elif cases != seen_cases:
                problems.append(
                    f"judge {name}: manifest says {cases} cases, {test} prints {seen_cases}"
                )
        rows.append(f"OK   judge {name:<27} cases={cases} {rel}")
    if not modules(manifest):
        problems.append(f"{MANIFEST}: lists no modules")
    return rows, problems


def compare(root: Path, target: Path, manifest: dict) -> tuple[list[str], list[str]]:
    rows: list[str] = []
    problems: list[str] = []
    for entry in modules(manifest):
        name = str(entry.get("name") or "?")
        for item in entry.get("files") or []:
            rel = str(item.get("path") or "")
            want = str(item.get("sha256") or "")
            copy = target / rel
            if not copy.is_file():
                rows.append(f"MISS {name:<20} {rel}")
                problems.append(f"{name}: {rel} is missing from {target}")
                continue
            got = sha256_file(copy)
            if want and got != want:
                rows.append(f"DRIFT {name:<19} {rel}")
                problems.append(f"{name}: {rel} differs from the source tree")
            else:
                rows.append(f"SAME {name:<20} {rel}")
        test = str(entry.get("test") or "")
        if test and not (target / test).is_file():
            rows.append(f"MISS {name:<20} {test}")
            problems.append(f"{name}: test {test} is missing from {target}")
    for entry in judges(manifest):
        name = str(entry.get("name") or "?")
        for rel in (str(entry.get("path") or ""), str(entry.get("test") or "")):
            if not rel:
                continue
            copy = target / rel
            if not copy.is_file():
                rows.append(f"MISS judge {name:<21} {rel}")
                problems.append(f"judge {name}: {rel} is missing from {target}")
                continue
            want = str(entry.get("sha256") or "")
            got = sha256_file(copy)
            if rel == str(entry.get("path") or "") and want and got != want:
                rows.append(f"DRIFT judge {name:<20} {rel}")
                problems.append(f"judge {name}: {rel} differs from the source tree")
            else:
                rows.append(f"SAME judge {name:<21} {rel}")
    return rows, problems


def render(manifest: dict) -> str:
    lines = [
        "# iOS 27 电源搬运清单（版本无关部分）。",
        "#",
        "# 这八个纯 C 模块（含充电认证状态机 K60ChargeAuth）是对 https://unixnu.com/zh/porting/power",
        "# 的可搬资产：它们不碰",
        "# IOKit、不碰 MMIO、只依赖 stdint.h，host 套件把每一条策略钉死。iOS 27 的关键",
        "# 不是\"重写一遍\"，而是\"原样搬过去、先跑同一组断言、再只替换接线\"。",
        "#",
        "# 另列四个判读器（scripts/judge-k60-*.py）：它们只吃 console 与镜像文本，同样",
        "# 与版本无关。搬过去先跑各自的夹具（33 / 28 / 14 / 17 例），再拿它读真机日志。",
        "#",
        "# 校验者：scripts/check-power-carry.py",
        "#   - 自带模式：文件存在、sha256 未漂移、套件数与 run-k60-power-host.sh 的记录",
        "#     一致、check-power-portability.py 仍然 freestanding 编译它；",
        "#   - --target <树>：逐文件比对目标树的副本，报告 same / missing / drift；",
        "#   - 判读器：文件与夹具存在、自己可编译、夹具仍打印记录里的用例数（夹具缩水",
        "#     的判读器就是 P-204 说的那种\"绿而盲\"）。",
        "#",
        "# 改模块时先改代码，再 `python3 scripts/check-power-carry.py --update` 刷新哈希，",
        "# 并在同一个提交里同步 docs/research/power/08-IOS27-POWER-PORT.md 的矩阵行。",
        "version = 1",
        "",
    ]
    for entry in modules(manifest):
        lines.append("[[module]]")
        lines.append(f'name = "{entry.get("name", "")}"')
        lines.append(f'suite = "{entry.get("suite", "")}"')
        lines.append(f'checks = {entry.get("checks", 0)}')
        lines.append(f'test = "{entry.get("test", "")}"')
        lines.append("files = [")
        for item in entry.get("files") or []:
            lines.append(
                f'  {{ path = "{item.get("path", "")}", sha256 = "{item.get("sha256", "")}" }},'
            )
        lines.append("]")
        lines.append("")
    for entry in judges(manifest):
        lines.append("[[judge]]")
        lines.append(f'name = "{entry.get("name", "")}"')
        lines.append(f'path = "{entry.get("path", "")}"')
        lines.append(f'sha256 = "{entry.get("sha256", "")}"')
        lines.append(f'test = "{entry.get("test", "")}"')
        lines.append(f'cases = {entry.get("cases", 0)}')
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="check the iOS 27 power carry manifest")
    parser.add_argument("--repo", type=Path, default=None)
    parser.add_argument("--target", type=Path, default=None)
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    root = (args.repo or repo_root()).resolve()
    try:
        manifest = load_manifest(root)
    except (OSError, tomllib.TOMLDecodeError) as error:
        print(f"power-carry: {root / MANIFEST}: {error}", file=sys.stderr)
        return 2
    if int(manifest.get("version") or 0) != 1:
        print(f"power-carry: {MANIFEST}: unsupported version", file=sys.stderr)
        return 2

    rows, problems = verify(root, manifest, args.update)
    if args.update:
        (root / MANIFEST).write_text(render(manifest), encoding="utf-8", newline="\n")
        print(f"power-carry: rewrote {MANIFEST}")
    if args.target is not None:
        target = args.target.resolve()
        target_rows, target_problems = compare(root, target, manifest)
        rows.extend(target_rows)
        problems.extend(target_problems)

    if not args.quiet:
        for row in rows:
            print(row)
    if problems:
        for problem in problems:
            print(f"power-carry: {problem}", file=sys.stderr)
        print(f"power-carry: FAIL ({len(problems)} problem(s))")
        return 1
    total = sum(int(entry.get("checks") or 0) for entry in modules(manifest))
    files = sum(len(entry.get("files") or []) for entry in modules(manifest))
    judged = len(judges(manifest))
    judge_cases = sum(int(entry.get("cases") or 0) for entry in judges(manifest))
    suffix = f"; target {args.target} matches" if args.target is not None else ""
    print(
        f"power-carry: OK ({len(modules(manifest))} modules, {files} files, {total} checks; "
        f"{judged} judge(s), {judge_cases} cases{suffix})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
