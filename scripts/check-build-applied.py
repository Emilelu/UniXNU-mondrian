#!/usr/bin/env python3
"""P-165: a build must apply every patch the series lists.

`git apply --numstat` only proves a diff parses; it says nothing about whether
the context still matches after the patches before it were applied. A hunk that
misses silently drops that patch AND every patch after it, and the compiler then
fails somewhere unrelated (2026-11-13: patch 0341 cost a 13-minute build and the
log never even mentioned the new file).

This reads the build log the driver writes and compares the applied count with
the series length. Run after every kernel build, or let check-rules do it.
"""
import argparse
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
SERIES = REPO / "patches/xnu/series"


def series_count() -> int:
    if not SERIES.is_file():
        return 0
    return sum(1 for line in SERIES.read_text(encoding="utf-8", errors="replace").splitlines()
               if line.strip() and not line.lstrip().startswith("#"))


def applied_count(log: pathlib.Path) -> int:
    text = log.read_text(encoding="utf-8", errors="replace")
    hits = re.findall(r"patches applied:\s*(\d+)", text)
    return int(hits[-1]) if hits else -1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default="/mnt/e/k60-work/scratch/BUILD_V15.txt",
                    help="build log that prints 'patches applied: N'")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    log = pathlib.Path(args.log)
    want = series_count()
    if not log.is_file():
        print(f"跳过 P-165 校验：找不到构建日志 {log}")
        return 0
    got = applied_count(log)
    if got < 0:
        print(f"跳过 P-165 校验：{log} 里没有 'patches applied:' 行")
        return 0
    if got != want:
        print(f"❌ P-165 {log.name} 只应用了 {got} 个补丁，但 series 列了 {want} 个")
        print("   说明序列里有补丁的上下文对不上；它和它之后的补丁都没有进树（P-165）。")
        return 1
    if not args.quiet:
        print(f"✅ 序列里 {want} 个补丁全部应用（P-165）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
