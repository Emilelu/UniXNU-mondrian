#!/usr/bin/env python3
"""Tests for the image-series logic in scripts/record-boot.py (P-211).

The ledger used to describe the series the repo carried at record time, so a boot
of another line's image was written down as a boot of this repo's series. The
image now speaks for itself through the build-manifest.json that build-strict
writes next to boot.img.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "record-boot.py"

MANIFEST_SHA = "0123456789abcdef" * 4
REPO_SHA = "fedcba9876543210"


def load():
    spec = importlib.util.spec_from_file_location("k60_record_boot", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    # Keep series_fingerprint() deterministic and repo-relative-free.
    module.series_fingerprint = lambda: (REPO_SHA, 226)
    return module


class Fixture:
    def __init__(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="k60-record-boot-"))
        self.image = self.root / "boot.img"
        self.image.write_bytes(b"\x00" * 4096)

    def close(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def manifest(self, sha: str = MANIFEST_SHA, count: int = 229) -> Path:
        path = self.root / "build-manifest.json"
        path.write_text(json.dumps({"series": {"sha256": sha, "count": count}}),
                        encoding="utf-8")
        return path


def case_manifest_series_wins(fx: Fixture) -> None:
    fx.manifest()
    module = load()
    fp, count, source, repo_fp = module.image_series(str(fx.image))
    assert fp == MANIFEST_SHA[:16], fp
    assert count == 229, count
    assert source.startswith("manifest:"), source
    assert repo_fp == REPO_SHA, repo_fp


def case_no_manifest_falls_back_to_the_repo(fx: Fixture) -> None:
    module = load()
    fp, count, source, repo_fp = module.image_series(str(fx.image))
    assert fp == REPO_SHA, fp
    assert count is None, count
    assert source == "repo-series", source


def case_short_sha_falls_back(fx: Fixture) -> None:
    fx.manifest(sha="deadbeef")
    module = load()
    fp, _count, source, _repo = module.image_series(str(fx.image))
    assert fp == REPO_SHA and source == "repo-series", (fp, source)


def case_broken_manifest_falls_back(fx: Fixture) -> None:
    (fx.root / "build-manifest.json").write_text("{not json", encoding="utf-8")
    module = load()
    fp, _count, source, _repo = module.image_series(str(fx.image))
    assert fp == REPO_SHA and source == "repo-series", (fp, source)


CASES = [
    ("manifest_series_wins", case_manifest_series_wins),
    ("no_manifest_falls_back_to_the_repo", case_no_manifest_falls_back_to_the_repo),
    ("a_short_sha_falls_back", case_short_sha_falls_back),
    ("a_broken_manifest_falls_back", case_broken_manifest_falls_back),
]


def main() -> int:
    failures = 0
    for name, function in CASES:
        fx = Fixture()
        try:
            function(fx)
            print(f"  ok   {name}")
        except Exception:
            failures += 1
            print(f"  FAIL {name}")
            traceback.print_exc()
        finally:
            fx.close()
    print(f"TESTS {'OK' if not failures else 'FAILED'} {len(CASES) - failures}/{len(CASES)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
