#!/usr/bin/env python3
"""`configs/ios.config` must match as itself, not as `configs/ios.c`.

P-253: the citation regex listed `c` among the extensions, so a non-greedy path
stopped one character after the final letter and the gate reported a missing
file that is present. These cases pin the boundary.
"""
import importlib.util
import os
import sys

REPO = os.environ.get('K60_REPO') or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GATE = os.path.join(REPO, 'scripts', 'check-doc-citations.py')

spec = importlib.util.spec_from_file_location('check_doc_citations', GATE)
cdc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdc)


def targets(line):
    return [m.group(1) for m in cdc.CITE_RE.finditer(line)]


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def config_extension_is_not_truncated():
    assert targets('see `configs/ios.config` for the fragment') == ['configs/ios.config'], \
        targets('see `configs/ios.config` for the fragment')


@case
def patch_extension_still_matches():
    assert targets('patches/xnu/0624-k60-quiet-managed-page-report.patch') == \
        ['patches/xnu/0624-k60-quiet-managed-page-report.patch']


@case
def c_extension_still_matches():
    assert targets('drivers/ArmCpu/ArmCpu.cpp and blobs/x.c') == ['drivers/ArmCpu/ArmCpu.cpp', 'blobs/x.c']


@case
def line_range_is_kept_separate():
    m = list(cdc.CITE_RE.finditer('scripts/build-xnu-4k-baseline.sh:902-1050'))[0]
    assert m.group(1) == 'scripts/build-xnu-4k-baseline.sh', m.group(1)
    assert (m.group(2), m.group(3)) == ('902', '1050')


@case
def a_table_row_is_scanned():
    row = '| S5 | x | build-strict.sh:68 | 低 |'
    assert 'scripts/build-strict.sh' not in targets(row)  # basename only: not a repo path
    row = '| S5 | x | scripts/build-strict.sh:68 | 低 |'
    assert targets(row) == ['scripts/build-strict.sh']


@case
def another_repos_prefix_is_ignored():
    assert targets('pong:drivers/PongWifi/PongWifiPlatform.cpp') == []


def main():
    failed = 0
    for fn in CASES:
        try:
            fn()
            print('ok   %s' % fn.__name__)
        except AssertionError as exc:
            failed += 1
            print('FAIL %s: %s' % (fn.__name__, exc))
    print('TESTS OK %d cases (%d failure(s))' % (len(CASES), failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())