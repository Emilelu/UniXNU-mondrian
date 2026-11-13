#!/usr/bin/env python3
"""P-165: a build must apply every patch the series lists.

`git apply --numstat` only proves a diff parses; it says nothing about whether
the context still matches after the patches before it were applied. A hunk that
misses silently drops that patch AND every patch after it, and the compiler then
fails somewhere unrelated (2026-11-13: patch 0341 cost a 13-minute build and the
log never even mentioned the new file).

The count comes from the driver: `unixnu` logs one `kernel: patch <name>` line
per applied patch (framework `scripts/unixnu/patches.py`). Older logs used a
single `patches applied: N` summary line; both are accepted, and the newest
candidate log wins, because a stale log reporting 228 patches while the series
lists 229 is exactly the false alarm that cost a debugging cycle.
"""
import argparse
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
SERIES = REPO / "patches/xnu/series"
INPUT = pathlib.Path("/tmp/usb-cdc-mainline/device/patches/xnu/series")
DEFAULT_LOGS = [
    pathlib.Path("/mnt/e/k60-work/scratch/BUILD_V15.txt"),
]
LOG_GLOBS = ["/tmp/kbuild-*.log", "/tmp/build-strict-*.log", "/tmp/build-v15.log"]


def series_count() -> int:
    if not SERIES.is_file():
        return 0
    return sum(1 for line in SERIES.read_text(encoding="utf-8", errors="replace").splitlines()
               if line.strip() and not line.lstrip().startswith("#"))


def newest_log() -> pathlib.Path | None:
    candidates = [p for p in DEFAULT_LOGS if p.is_file()]
    for pattern in LOG_GLOBS:
        candidates.extend(p for p in pathlib.Path("/").glob(pattern.lstrip("/")) if p.is_file())
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


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


def input_matches_repo() -> str:
    """P-166: the build must not carry its own copy of the patch list."""
    if not INPUT.is_file():
        return "input series absent; skipping parity check"
    repo = [l.strip() for l in SERIES.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
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
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    parity = input_matches_repo()
    if parity.startswith("❌"):
        print(parity)
        return 1
    log = pathlib.Path(args.log) if args.log else newest_log()
    want = series_count()
    if log is None or not log.is_file():
        print(f"跳过 P-165 校验：找不到构建日志 {log}")
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
