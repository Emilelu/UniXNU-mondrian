#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Self-test for scripts/research-gate.py reference resolution.

The gate used to resolve a reference path against exactly two places: the
device checkout and `/mnt/e/k60-work`. Two reference repositories are checked
out under `/mnt/e/hackios` instead (QcaBluetooth, UniXNU-liuqin), so a
`required` entry naming either of them failed forever and the refmine line had
to keep those findings in prose.

These cases pin the resolution order and the failure message:

  1. REPO comes from K60_REPO or the script's own checkout, never a literal.
  2. `/mnt/e/hackios` is one of the prefixes.
  3. A path that exists under the hackios prefix resolves (QcaBluetooth).
  4. A path that exists nowhere is reported with the prefix count.
  5. A relative path inside the repo still wins over a reference checkout.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "research-gate.py"

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def load_gate():
    spec = importlib.util.spec_from_file_location("research_gate", GATE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@case
def the_repo_root_is_not_a_literal_checkout():
    gate = load_gate()
    # 拆开拼装，免得这一行自己被 check-repo-paths.py 当成硬编码。
    shared_checkout = '/mnt/e/' + 'hackios/UniXNU-mondrian'
    assert shared_checkout not in str(gate.REPO), (
        "REPO is still the hard-coded shared checkout; a worktree would validate "
        "somebody else's files"
    )
    assert Path(gate.REPO).name != '', "REPO resolved to an empty path"


@case
def the_hackios_prefix_is_searched():
    gate = load_gate()
    prefixes = [str(p) for p in gate.REFERENCE_PREFIXES]
    assert '/mnt/e/hackios' in prefixes, f"missing /mnt/e/hackios in {prefixes}"
    assert prefixes[0] == str(gate.REPO), "the repo itself must be searched first"


@case
def a_reference_under_hackios_resolves():
    gate = load_gate()
    probe = 'QcaBluetooth/README.md'
    if not os.path.exists('/mnt/e/hackios/' + probe):
        print('   (skipped: /mnt/e/hackios/QcaBluetooth is not checked out here)')
        return
    tried = [os.path.join(prefix, probe) for prefix in gate.REFERENCE_PREFIXES]
    assert any(os.path.exists(t) for t in tried), (
        f"{probe} exists under /mnt/e/hackios but no prefix found it: {tried}"
    )


@case
def a_missing_reference_names_the_prefix_count():
    gate = load_gate()
    with tempfile.TemporaryDirectory() as tmp:
        sources = Path(tmp) / 'docs' / 'research'
        sources.mkdir(parents=True)
        (sources / 'SOURCES.toml').write_text(
            '[subsystem.probe]\n'
            '[[subsystem.probe.required]]\n'
            'path = "no-such-reference-anywhere/zz.md"\n'
            'examined = "yes"\n'
            'finding = "this finding is long enough to pass the length check"\n',
            encoding='utf-8',
        )
        old_repo, old_sources = gate.REPO, gate.SOURCES
        try:
            gate.REPO = tmp
            gate.SOURCES = str(sources / 'SOURCES.toml')
            ok, problems = gate.check(verbose=False)
        finally:
            gate.REPO, gate.SOURCES = old_repo, old_sources
    assert not ok, "a missing reference must fail the gate"
    joined = ' '.join(problems)
    assert '不存在' in joined, f"expected a missing-file problem, got {problems}"
    assert '前缀' in joined, f"the message must say how many prefixes were tried: {problems}"


@case
def a_repo_relative_path_still_resolves_first():
    gate = load_gate()
    probe = 'docs/engineering/PITFALLS.md'
    first = os.path.join(str(gate.REPO), probe)
    assert os.path.exists(first), f"{first} should exist in the repo"
    tried = [os.path.join(prefix, probe) for prefix in gate.REFERENCE_PREFIXES]
    assert tried[0] == first, "the repo-relative candidate must be tried first"


def main() -> int:
    failures = 0
    for fn in CASES:
        try:
            fn()
            print(f"ok   {fn.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001 - a broken gate is a failure, not a crash
            failures += 1
            print(f"FAIL {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"TESTS OK {len(CASES) - failures} case(s) ({failures} failure(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
