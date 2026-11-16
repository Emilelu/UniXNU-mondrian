#!/usr/bin/env python3
"""Tests for the image-series logic in scripts/record-boot.py (P-211, P-214).

P-211: the ledger used to describe the series the repo carried at record time, so a
boot of another line's image was written down as a boot of this repo's series. The
image now speaks for itself through the build-manifest.json that build-strict
writes next to boot.img.

P-214: speaking for itself is only useful if it speaks the same language. Manifests
written before 2026-11-16 carry `sha256(<bytes of series>)`; the ledger and
porting-gate compare `sha256(names + sizes)[:16]`. Both are stable, neither is
wrong, and they never agree -- so a manifest that does not declare the shared
namespace must be refused rather than believed.
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

MANIFEST_SHA = "0123456789abcdef"
FILE_SHA = "0123456789abcdef" * 4
REPO_SHA = "fedcba9876543210"
REPO_COUNT = 226


def load():
    spec = importlib.util.spec_from_file_location("k60_record_boot", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    # Keep series_fingerprint() deterministic and repo-relative-free.
    module.series_fingerprint = lambda: (REPO_SHA, REPO_COUNT)
    return module


class Fixture:
    def __init__(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="k60-record-boot-"))
        self.image = self.root / "boot.img"
        self.image.write_bytes(b"\x00" * 4096)

    def close(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def manifest(self, sha: str = MANIFEST_SHA, count: int = 229,
                 namespace: str | None = "names+sizes") -> Path:
        series = {"sha256": sha, "count": count}
        if namespace is not None:
            series["namespace"] = namespace
        path = self.root / "build-manifest.json"
        path.write_text(json.dumps({"series": series}), encoding="utf-8")
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
    assert count == REPO_COUNT, count
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


def case_a_foreign_namespace_is_refused(fx: Fixture) -> None:
    """P-214: a value from another namespace is not a comparable value."""
    fx.manifest(sha=MANIFEST_SHA, namespace="file-bytes")
    module = load()
    fp, _count, source, _repo = module.image_series(str(fx.image))
    assert fp == REPO_SHA, f"believed a foreign-namespace fingerprint: {fp}"
    assert source == "repo-series", source


def case_a_legacy_64_hex_manifest_is_refused(fx: Fixture) -> None:
    """Manifests from before P-214 have no namespace field and a 64-hex hash."""
    fx.manifest(sha=FILE_SHA, namespace=None)
    module = load()
    fp, _count, source, _repo = module.image_series(str(fx.image))
    assert fp == REPO_SHA, f"believed a pre-P-214 file-bytes hash: {fp}"
    assert source == "repo-series", source


def case_a_legacy_16_hex_manifest_is_still_usable(fx: Fixture) -> None:
    """An old manifest that happens to be 16 hex is already in our namespace."""
    fx.manifest(sha=MANIFEST_SHA, namespace=None)
    module = load()
    fp, _count, source, _repo = module.image_series(str(fx.image))
    assert fp == MANIFEST_SHA, fp
    assert source.startswith("manifest:"), source


CASES = [
    ("manifest_series_wins", case_manifest_series_wins),
    ("no_manifest_falls_back_to_the_repo", case_no_manifest_falls_back_to_the_repo),
    ("a_short_sha_falls_back", case_short_sha_falls_back),
    ("a_broken_manifest_falls_back", case_broken_manifest_falls_back),
    ("a_foreign_namespace_is_refused", case_a_foreign_namespace_is_refused),
    ("a_legacy_64_hex_manifest_is_refused", case_a_legacy_64_hex_manifest_is_refused),
    ("a_legacy_16_hex_manifest_is_still_usable", case_a_legacy_16_hex_manifest_is_still_usable),
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
