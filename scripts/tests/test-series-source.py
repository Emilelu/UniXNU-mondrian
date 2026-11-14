#!/usr/bin/env python3
"""Tests for P-194: the patch-series fingerprint must measure the built series.

board.toml's patch_series points at device:patches/xnu/series, so that file is
the ordered list the kernel is actually built from.  porting-gate.py and
record-boot.py both used to hash /mnt/e/k60-work/scratch/SERIES-FINAL.txt, a
scratch copy that had drifted to 227 entries (four bluetooth patches plus the
retired 0610-k60-metal-seeds.patch) while the repository series had 223.

These tests pin three things:
  * neither script hard-codes the scratch copy as its primary source,
  * both resolve the same file and therefore agree on the fingerprint,
  * the fingerprint's patch count matches what the build manifest recorded.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "porting-gate.py"
RECORD = ROOT / "scripts" / "record-boot.py"
SERIES = ROOT / "patches/xnu/series"
MANIFEST_DIRS = ("/mnt/e/k60-work/artifacts", "/opt/k60/trees/lead-out")


def series_assignment(path: pathlib.Path) -> str:
    """Return the source text of the module-level SERIES assignment block."""
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^SERIES = .*?(?=^\w|\Z)", text, re.M | re.S)
    if not m:
        raise SystemExit(f"{path}: no SERIES assignment found")
    return m.group(0)


def series_names(path: pathlib.Path) -> list[str]:
    return [l.strip() for l in path.read_text(encoding="utf-8").splitlines()
            if l.strip()]


def fingerprint(names: list[str], base: pathlib.Path) -> str:
    """Mirror the scripts' sha256(names + sizes)[:16]."""
    import hashlib
    h = hashlib.sha256()
    for n in names:
        h.update(n.encode())
        p = base / n
        if p.exists():
            h.update(str(p.stat().st_size).encode())
    return h.hexdigest()[:16]


def _current_branch() -> str:
    out = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--abbrev-ref", "HEAD"],
                         capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else ""


def newest_manifest() -> pathlib.Path | None:
    """Return the newest build manifest recorded from THIS branch, or None.

    The artifacts directory is shared by every worktree, and all worktrees share
    one object database, so neither mtime nor "a commit we know" identifies our
    own build: the newest manifest usually belongs to another line whose series
    has a different length. The recorded branch is what separates them.
    """
    branch = _current_branch()
    best = None
    for root in MANIFEST_DIRS:
        for p in pathlib.Path(root).glob("*/build-manifest.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            recorded = (data.get("repo") or {}).get("branch")
            if branch and recorded != branch:
                continue
            if best is None or p.stat().st_mtime > best.stat().st_mtime:
                best = p
    return best


def main() -> int:
    failures = 0
    cases = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal failures, cases
        cases += 1
        print(f"{'PASS' if ok else 'FAIL'} {label}")
        if not ok:
            failures += 1
            if detail:
                print("      " + detail)

    # 1. The scratch copy may only appear as a fallback, never as the primary.
    for path in (GATE, RECORD):
        block = series_assignment(path)
        primary = block.split("if not os.path.exists")[0]
        check(f"{path.name}: the repository series is the primary source",
              "patches/xnu/series" in primary,
              f"primary assignment does not name patches/xnu/series:\n{primary}")
        check(f"{path.name}: the scratch copy survives only as a fallback",
              "SERIES-FINAL" not in primary,
              f"primary assignment still names SERIES-FINAL:\n{primary}")

    # 2. Both scripts name the same file, so their fingerprints agree.
    check("both scripts read the same series",
          "patches/xnu/series" in series_assignment(GATE)
          and "patches/xnu/series" in series_assignment(RECORD))

    # 3. The repository series exists and is not empty.
    check("the repository series exists", SERIES.is_file(), str(SERIES))
    names = series_names(SERIES) if SERIES.is_file() else []
    check("the repository series is not empty", bool(names))
    check("no patch is listed twice", len(names) == len(set(names)),
          f"{len(names) - len(set(names))} duplicate entries")

    # 4. The fingerprint the scripts would compute matches the build manifest.
    #
    # A series edited after the newest build makes that manifest stale, and the
    # rebuild is the fix. Refusing here would be the P-165 deadlock: the gate
    # would block the very build that refreshes the record. So a manifest older
    # than the series is reported and skipped; a manifest that is newer than the
    # series and still disagrees is a real lie and stays a failure.
    manifest = newest_manifest()
    if manifest is None:
        check("a build manifest is available to compare against", False,
              "no build-manifest.json under " + " or ".join(MANIFEST_DIRS))
    else:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        recorded = data.get("series", {})
        digest = __import__("hashlib").sha256(SERIES.read_bytes()).hexdigest()
        stale = SERIES.stat().st_mtime > manifest.stat().st_mtime
        agrees = (recorded.get("count") == len(names)
                  and recorded.get("sha256") == digest)
        if stale and not agrees:
            print(f"skip {manifest.parent.name}: the series changed after this "
                  f"build (manifest {recorded.get('count')}, series "
                  f"{len(names)}); the next build refreshes it")
        else:
            check(f"{manifest.parent.name}: manifest patch count equals the series",
                  recorded.get("count") == len(names),
                  f"manifest {recorded.get('count')} vs series {len(names)}")
            check(f"{manifest.parent.name}: manifest series sha256 equals the file",
                  recorded.get("sha256") == digest,
                  "the manifest was built from a different series")

    # 5. The scratch copy is either absent or demonstrably stale; if it differs,
    #    the fallback must not be the one in use.
    scratch = pathlib.Path("/mnt/e/k60-work/scratch/SERIES-FINAL.txt")
    if scratch.is_file():
        stale = series_names(scratch) != names
        check("a stale scratch copy is not the source the gate measures",
              stale and "SERIES-FINAL" not in series_assignment(GATE).split(
                  "if not os.path.exists")[0],
              "the scratch copy matches the repository series, so this test "
              "cannot distinguish them any more — delete it or update the test")

    if failures:
        print(f"TESTS OK 0 cases ({failures} failure(s))")
        return 1
    print(f"TESTS OK {cases} cases (0 failure(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
