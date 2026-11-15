#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Self-test for scripts/check-defconfig-uuid.py (P-209).

The gate exists because five wifi images were declared "silent" while the only
thing wrong was a defconfig naming the memory-backed seed's Data UUID. Its own
failure mode would be the usual one: a marker regex that is too generous, or a
scanner that looks at a file the build never reads, so the gate prints a green
tick over a boot that cannot reach the console.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "check-defconfig-uuid.py"

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def load_gate():
    spec = importlib.util.spec_from_file_location("check_defconfig_uuid", GATE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def repo_with(files: dict[str, str]) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="k60-uuid-"))
    (tmp / "configs").mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (tmp / "configs" / name).write_text(text, encoding="utf-8")
    return tmp


@case
def the_live_volume_passes():
    gate = load_gate()
    repo = repo_with({"a_defconfig": f'CONFIG_XNU_OWNER_DATA_VOLUME_UUID="{gate.LIVE_DATA_UUID}"\n'})
    report = gate.run(repo)
    assert report["ok"], report["failures"]
    assert report["hits"] and report["hits"][0]["kind"] == "live"


@case
def the_seed_volume_fails_without_a_marker():
    gate = load_gate()
    repo = repo_with({"a_defconfig": f'CONFIG_XNU_OWNER_DATA_VOLUME_UUID="{gate.SEED_DATA_UUID}"\n'})
    report = gate.run(repo)
    assert not report["ok"], "a seed UUID without a marker must fail"
    assert any("memory-backed seed" in text for text in report["failures"]), report["failures"]
    assert any("P-209" in text for text in report["failures"]), report["failures"]


@case
def the_seed_volume_passes_when_marked_intentional():
    gate = load_gate()
    text = ("# SEED-UUID: intentional -- trial build mounts the 32 MiB OwnerData seed\n"
            f'CONFIG_XNU_OWNER_DATA_VOLUME_UUID="{gate.SEED_DATA_UUID}"\n')
    repo = repo_with({"a_defconfig": text})
    report = gate.run(repo)
    assert report["ok"], report["failures"]
    assert report["hits"][0]["marker"], "the marker must be recorded on the hit"


@case
def a_marker_far_away_does_not_count():
    gate = load_gate()
    text = ("# SEED-UUID: intentional -- belongs to another option\n"
            + "\n" * 20
            + f'CONFIG_XNU_OWNER_DATA_VOLUME_UUID="{gate.SEED_DATA_UUID}"\n')
    repo = repo_with({"a_defconfig": text})
    report = gate.run(repo)
    assert not report["ok"], "a marker outside the radius must not excuse the seed UUID"


@case
def no_assignment_is_not_a_failure():
    gate = load_gate()
    repo = repo_with({"a_defconfig": "# nothing about volumes here\nCONFIG_XNU_ARMCPU=y\n"})
    report = gate.run(repo)
    assert report["ok"], report["failures"]
    assert report["hits"] == []


@case
def an_unknown_volume_is_reported_not_failed():
    gate = load_gate()
    repo = repo_with({"a_defconfig": 'CONFIG_XNU_OWNER_CACHE_VOLUME_UUID="15B507FA-21B7-4EE5-B55D-0F3445DE0752"\n'})
    report = gate.run(repo)
    assert report["ok"], report["failures"]
    assert report["unknowns"], "an unknown volume must be surfaced"
    assert any("not a known volume" in text for text in report["unknowns"])


@case
def only_the_offending_file_is_named():
    gate = load_gate()
    repo = repo_with({
        "good_defconfig": f'CONFIG_XNU_OWNER_DATA_VOLUME_UUID="{gate.LIVE_DATA_UUID}"\n',
        "bad_defconfig": f'CONFIG_XNU_OWNER_DATA_VOLUME_UUID="{gate.SEED_DATA_UUID}"\n',
    })
    report = gate.run(repo)
    assert not report["ok"]
    assert len(report["failures"]) == 1, report["failures"]
    assert "bad_defconfig" in report["failures"][0], report["failures"][0]


@case
def the_real_repository_passes():
    gate = load_gate()
    report = gate.run(ROOT)
    assert report["ok"], report["failures"]
    live = [hit for hit in report["hits"] if hit["kind"] == "live"]
    assert live, "the shipped defconfig should name the live Data volume"


def main() -> int:
    failures = 0
    for fn in CASES:
        try:
            fn()
            print(f"ok   {fn.__name__}")
        except AssertionError as error:
            failures += 1
            print(f"FAIL {fn.__name__}: {error}")
    print(f"TESTS OK {len(CASES) - failures} case(s) ({failures} failure(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
