#!/usr/bin/env python3
"""Guard the embedded-blob patches against silent semantic drift.

0340 / 0391 / 0401 carry compiled userland blobs as C arrays. A one-line size
change in the patch is a whole new binary in the kernel, so patch line counts
and hunk counts prove nothing: the only proof is an on-device boot.

The booted entry in docs/engineering/MAIN-BASELINE.toml records the sha256 of
each blob patch that was present when that boot was proven. On `main` every
existing blob patch must still match; a mismatch means the baseline is gone and
a new boot is required before the change may land. On a feature branch the
mismatch is a warning (iron rule 9 allows experiments off main).
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASELINE = REPO / "docs" / "engineering" / "MAIN-BASELINE.toml"

BLOB_PATCHES = [
    "patches/xnu/0340-k60-uilib-deploy.patch",
    "patches/xnu/0391-k60-embedded-init.patch",
    "patches/xnu/0401-k60-embedded-init.patch",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, check=False
    ).stdout.strip()


def recorded_hashes() -> dict[str, str]:
    """Read the [entry.blob_sha256] table of the newest booted entry."""
    if not BASELINE.is_file():
        return {}
    text = BASELINE.read_text(encoding="utf-8", errors="replace")
    entries = text.split("[[entry]]")
    for block in reversed(entries):
        if 'state = "booted"' in block and "[entry.blob_sha256]" in block:
            table = block.split("[entry.blob_sha256]", 1)[1]
            table = table.split("\n[", 1)[0]
            out: dict[str, str] = {}
            for line in table.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip().strip('"')
                value = value.strip().strip('"')
                if key and value:
                    out[key] = value
            return out
    return {}


def main() -> int:
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    baseline = recorded_hashes()
    problems: list[str] = []
    warnings: list[str] = []

    if not baseline:
        warnings.append(
            "MAIN-BASELINE.toml 的 booted 条目里没有 [entry.blob_sha256]，本次只警告"
        )

    for rel in BLOB_PATCHES:
        path = REPO / rel
        if not path.is_file():
            continue
        current = sha256(path)
        expected = baseline.get(rel)
        if expected and current != expected:
            msg = (
                f"{rel} 与最近一次上机基线的值不同 "
                f"({current[:12]} != {expected[:12]})：嵌入式 blob 换了就是新代码，"
                "必须重新上机启动并在 MAIN-BASELINE.toml 更新 blob_sha256"
            )
            (problems if branch == "main" else warnings).append(msg)

    for w in warnings:
        print(f"⚠️  blob-patches: {w}")
    for p in problems:
        print(f"❌ blob-patches: {p}")
    if problems:
        return 1
    print(
        f"✅ blob-patches 通过（{len(BLOB_PATCHES)} 个嵌入 blob 补丁；分支 {branch}）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
