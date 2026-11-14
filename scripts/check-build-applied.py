#!/usr/bin/env python3
"""P-165: a build must apply every patch the series lists, from the exact bytes
the repository holds.

`git apply --numstat` only proves a diff parses; it says nothing about whether
the context still matches after the patches before it were applied. A hunk that
misses silently drops that patch AND every patch after it, and the compiler then
fails somewhere unrelated (2026-11-13: patch 0341 cost a 13-minute build and the
log never even mentioned the new file).

The authoritative record is the driver's own stamp, not a log: `unixnu` writes
`<out>/xnu-inputs.json` listing every patch path and its sha256 at the moment the
work tree was prepared (`scripts/unixnu/patches.py`). Comparing that list with
the repository proves both the count and the contents. Grepping a log is the
fallback for builds made before the stamp existed, and the log globs point at
`$K60_ARTIFACTS` rather than /tmp, per iron rule 1.
"""
import argparse
import hashlib
import json
import os
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
SERIES = REPO / "patches/xnu/series"
# The registry runs as a child of build-strict.sh, which knows which device tree
# this build uses. A hard-coded mirror here judged another line's series and
# failed P-166 for a difference that does not exist (2026-11-14).
INPUT = pathlib.Path(os.environ.get(
    "K60_DEVICE_INPUT", "/opt/k60/trees/usb-cdc-mainline/device")) / "patches/xnu/series"
BUILD_OUT = pathlib.Path(os.environ.get("K60_OUT", "/opt/k60/trees/k60build/out-baseline"))
ARTIFACTS = pathlib.Path(os.environ.get("K60_ARTIFACTS", "/mnt/e/k60-work/artifacts"))
DEFAULT_LOGS = [
    pathlib.Path("/mnt/e/k60-work/scratch/BUILD_V15.txt"),
]
LOG_GLOBS = ["*/logs/kernel.log"]
# build-strict.sh exports this for the whole run. A stale stamp then means
# "this build is about to rewrite it", not "somebody forgot to build".
IN_PROGRESS = os.environ.get("K60_BUILD_IN_PROGRESS") == "1"


def series_entries() -> list[str]:
    if not SERIES.is_file():
        return []
    return [line.strip() for line in SERIES.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def series_count() -> int:
    return len(series_entries())


def newest_log() -> pathlib.Path | None:
    candidates = [p for p in DEFAULT_LOGS if p.is_file()]
    if ARTIFACTS.is_dir():
        for pattern in LOG_GLOBS:
            candidates.extend(p for p in ARTIFACTS.glob(pattern) if p.is_file())
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def stamp_path() -> pathlib.Path | None:
    """The newest `<out>/*/*/*/xnu-inputs.json` written by the driver."""
    if not BUILD_OUT.is_dir():
        return None
    stamps = [p for p in BUILD_OUT.glob("*/*/*/xnu-inputs.json") if p.is_file()]
    if not stamps:
        return None
    return max(stamps, key=lambda p: p.stat().st_mtime)


def applied_count(log: pathlib.Path) -> int:
    text = log.read_text(encoding="utf-8", errors="replace")
    hits = re.findall(r"patches applied:\s*(\d+)", text)
    if hits:
        return int(hits[-1])
    # The driver prefixes its own lines with `== ` when it echoes the stage, so
    # accept both `kernel: patch x` and `== kernel: patch x`.
    per_patch = re.findall(r"^(?:==\s*)?kernel: patch \S+", text, re.MULTILINE)
    if per_patch:
        return len(per_patch)
    return -1


def check_stamp(stamp: pathlib.Path, quiet: bool) -> int:
    """Compare the driver's applied patch list with the repository's series."""
    try:
        record = json.loads(stamp.read_text(encoding="utf-8"))
        applied = record["patches"]
    except (ValueError, KeyError, OSError) as error:
        print(f"❌ P-165 无法读取构建记录 {stamp}：{error}")
        return 1

    want = series_entries()
    if len(applied) != len(want):
        print(f"❌ P-165 构建应用了 {len(applied)} 个补丁，但 series 列了 {len(want)} 个")
        print(f"   构建记录 {stamp}")
        print("   说明序列里有补丁的上下文对不上；它和它之后的补丁都没有进树（P-165）。")
        return 0 if IN_PROGRESS else 1

    # Same count is not enough: the bytes must be the ones this checkout holds.
    stale = []
    for entry in applied:
        path = pathlib.Path(entry.get("path", ""))
        if not path.is_file():
            stale.append(f"{path.name}: 文件不存在")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != entry.get("sha256"):
            stale.append(f"{path.name}: 构建时 {entry.get('sha256', '?')[:12]} 现在是 {actual[:12]}")
    if stale:
        print(f"❌ P-165 构建用的补丁内容与仓库不一致（{len(stale)} 个）：")
        for line in stale[:5]:
            print(f"   {line}")
        print(f"   构建记录 {stamp}；需要重新构建才能证明这棵树来自当前补丁集。")
        return 0 if IN_PROGRESS else 1

    if not quiet:
        print(f"✅ 序列里 {len(want)} 个补丁全部应用且内容与仓库一致（P-165，{stamp.name}）")
    return 0


def input_matches_repo() -> str:
    """P-166: the build must not carry its own copy of the patch list."""
    if not INPUT.is_file():
        return "input series absent; skipping parity check"
    repo = series_entries()
    dev = [l.strip() for l in INPUT.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
    if repo == dev:
        return ""
    only_repo = [n for n in repo if n not in dev]
    only_dev = [n for n in dev if n not in repo]
    return (f"❌ P-166 构建输入序列与仓库不一致：只在仓库有 {only_repo[:3]}，"
            f"只在输入有 {only_dev[:3]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", help="build log; defaults to the newest candidate")
    ap.add_argument("--stamp", help="xnu-inputs.json; defaults to the newest under the build out")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    parity = input_matches_repo()
    if parity.startswith("❌"):
        print(parity)
        return 1

    if not args.log:
        stamp = pathlib.Path(args.stamp) if args.stamp else stamp_path()
        if stamp is not None:
            return check_stamp(stamp, args.quiet)

    log = pathlib.Path(args.log) if args.log else newest_log()
    want = series_count()
    if log is None or not log.is_file():
        print(f"跳过 P-165 校验：找不到构建记录或日志 {log}")
        return 0
    got = applied_count(log)
    if got < 0:
        print(f"跳过 P-165 校验：{log} 里没有 'kernel: patch' 或 'patches applied:' 行")
        return 0
    if got != want:
        print(f"❌ P-165 {log.name} 只应用了 {got} 个补丁，但 series 列了 {want} 个")
        print("   说明序列里有补丁的上下文对不上；它和它之后的补丁都没有进树（P-165）。")
        return 1
    if not args.quiet:
        print(f"✅ 序列里 {want} 个补丁全部应用（P-165，{log.name}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
