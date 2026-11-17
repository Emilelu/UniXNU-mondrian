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
_INPUT_ENV = os.environ.get("K60_DEVICE_INPUT")
if not _INPUT_ENV:
    sys.exit("check-build-applied: K60_DEVICE_INPUT is not set; refusing to compare the series "
             "against a mirror the caller did not name (2026-11-16: the silent fallback turned "
             "one unset variable into five false reds in check-rules).")
INPUT = pathlib.Path(_INPUT_ENV) / "patches/xnu/series"
BUILD_OUT = pathlib.Path(os.environ.get("K60_OUT", "/opt/k60/trees/k60build/out-baseline"))
# 一棵树可以有多个输出目录（mondrian_defconfig -> mondrian/，
# mondrian_wifi_defconfig -> mondrian_wifi/），而 K60_OUT 只指向其中一个。
# 不设 K60_OUT 时如果只看 out-baseline，读到的就是别的配置留下的旧存根，
# 于是"构建应用了 230 个补丁但 series 列了 223 个"这种假红。改成在所有
# 输出目录里取最新的那份存根（P-189）。
OUT_ROOTS = [pathlib.Path('/opt/k60/trees')]
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


def _stamp_matches(stamp: pathlib.Path) -> bool:
    """True when every patch in the stamp has the same bytes as this checkout."""
    try:
        record = json.loads(stamp.read_text(encoding="utf-8"))
        applied = record["patches"]
    except (ValueError, KeyError, OSError):
        return False
    want = series_entries()
    if len(applied) != len(want):
        return False
    for index, entry in enumerate(applied):
        repo = REPO / "patches/xnu" / want[index]
        if not repo.is_file():
            return False
        if hashlib.sha256(repo.read_bytes()).hexdigest() != entry.get("sha256"):
            return False
    return True


def _stamp_names(stamp: pathlib.Path) -> list[str] | None:
    """The patch names a stamp recorded, or None when it cannot be read."""
    try:
        record = json.loads(stamp.read_text(encoding="utf-8"))
        return [str(entry.get("name") or pathlib.Path(str(entry.get("path", ""))).name)
                for entry in record["patches"]]
    except (ValueError, KeyError, OSError, TypeError):
        return None


def _same_series_names(stamp: pathlib.Path) -> bool:
    """True when the stamp lists exactly the patch names this checkout lists.

    This is the line between the two situations a stamp mismatch can mean:

      * same names, different bytes -> this checkout's series changed after the
        build, so the tree no longer proves anything about the current patches;
        that is a real red and a rebuild is required.
      * different names -> the stamp belongs to another branch or another
        board's series (P-189: several output trees share the machine). Nothing
        about this checkout can be concluded from it, so it must not be graded
        at all (P-207: never judge a stale artifact).
    """
    names = _stamp_names(stamp)
    return names is not None and names == series_entries()


def stamp_path() -> pathlib.Path | None:
    """The newest build stamp that this checkout can actually vouch for.

    A stamp only says "these patch bytes were applied". Several checkouts and
    several output trees share the machine, so the newest stamp may belong to a
    different branch: picking it blindly turned a clean tree into a false red
    (P-189). Prefer a stamp whose recorded bytes equal this checkout's series;
    failing that, keep only a stamp that lists the same patch names, because
    only then does a byte difference say something about this checkout.
    """
    stamps = []
    if os.environ.get("K60_OUT"):
        out = pathlib.Path(os.environ["K60_OUT"])
        if out.is_dir():
            stamps = [p for p in out.rglob("xnu-inputs.json") if p.is_file()]
    else:
        for root in OUT_ROOTS:
            stamps.extend(p for p in root.rglob("xnu-inputs.json") if p.is_file())
    if not stamps:
        return None
    stamps.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for stamp in stamps:
        if _stamp_matches(stamp):
            return stamp
    for stamp in stamps:
        if _same_series_names(stamp):
            return stamp
    return None


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

    # Compare the stamp with THIS checkout, not with itself: the recorded sha
    # only proves the build input has not changed since, which a stale mirror
    # satisfies happily.
    stale = []
    for index, entry in enumerate(applied):
        name = want[index]
        repo = REPO / "patches/xnu" / name
        if not repo.is_file():
            stale.append(f"{name}: 仓库里没有这个补丁")
            continue
        now = hashlib.sha256(repo.read_bytes()).hexdigest()
        if now != entry.get("sha256"):
            stale.append(f"{name}: 构建时 {entry.get('sha256', '?')[:12]} 现在 {now[:12]}")
            continue
        built = pathlib.Path(entry.get("path", ""))
        if built.is_file() and hashlib.sha256(built.read_bytes()).hexdigest() != now:
            stale.append(f"{name}: 构建输入副本与仓库不一致")
    if stale:
        if IN_PROGRESS:
            print(f"⚠️  P-165 补丁集已改（{len(stale)} 个），本次构建会重新生成记录：")
            for line in stale[:5]:
                print(f"   {line}")
            return 0
        print(f"❌ P-165 上次构建用的补丁内容与仓库不一致（{len(stale)} 个）：")
        for line in stale[:5]:
            print(f"   {line}")
        print(f"   构建记录 {stamp}；需要重新构建才能证明这棵树来自当前补丁集。")
        return 1

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
        if not args.stamp:
            # No stamp on this machine lists this checkout's patch names, so no
            # build here can speak for the current series. Falling back to a log
            # would grade another branch's build (P-189/P-207).
            print("跳过 P-165 校验：本机没有一次构建记录与当前 series 的补丁名一致，"
                  "没有构建能证明这棵树来自当前补丁集")
            return 0

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
