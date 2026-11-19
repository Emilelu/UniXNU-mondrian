#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
# Copyright (c) 2026, UniXNU contributors.
"""The GIC SPI ownership check: the production fragment against a model."""

import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHECK = os.path.join(ROOT, 'scripts', 'check-bluetooth-gic.py')
SOURCE = os.path.join(ROOT, 'drivers', 'ArmCpu', 'ArmCpu.cpp')
FIXTURE = os.path.join(ROOT, 'scripts', 'tests', 'fixtures', 'bt-gic-shared.c')

CASES = 0
FAILURES = []


def check(ok, message):
    global CASES
    CASES += 1
    if not ok:
        FAILURES.append(message)


def run(*args):
    return subprocess.run([sys.executable, CHECK, *args],
                          capture_output=True, text=True)


check(os.path.exists(CHECK), 'check-bluetooth-gic.py exists')
check(os.path.exists(FIXTURE), 'the harness fixture exists')

with tempfile.TemporaryDirectory() as tmp:
    out = os.path.join(tmp, 'report')
    result = run('--out', out)
    check(result.returncode == 0, 'the shipped source passes: ' + result.stdout[-400:])
    check('bluetooth-gic-check: OK' in result.stdout, 'the checker reports OK')

    report_path = os.path.join(out, 'report.json')
    check(os.path.exists(report_path), 'the checker writes a report')
    report = json.load(open(report_path, encoding='utf-8'))
    check(report['passed'] is True, 'the report says passed')
    check(report['hardware_verified'] is False,
          'the report never claims hardware verification')
    check(report['assertions'] >= 40, 'the report counts the assertions')
    check(report['distributor_writes'] >= 10,
          'the report counts the distributor writes')
    check(report['source'] == 'ArmCpu.cpp', 'the report names the source')
    check(len(report['source_sha256']) == 64, 'the report fingerprints the source')
    check(report['fragment_sha256'] != report['source_sha256'],
          'the fragment is a slice, not the whole file')
    check(len(report['fixture_sha256']) == 64, 'the report fingerprints the fixture')

    # The model must notice a broken ownership rule: drop the duplicate check
    # and the second attach of 619 succeeds, so the run has to fail.
    broken = os.path.join(tmp, 'ArmCpu.cpp')
    source = open(SOURCE, encoding='utf-8').read()
    needle = ('  for(uint32_t i=0;i<used;i++)if(gSpi[i].id==intid)'
              'result=kIOReturnExclusiveAccess;\n')
    check(source.count(needle) == 1, 'the duplicate guard is where the test expects')
    open(broken, 'w', encoding='utf-8').write(source.replace(needle, ''))
    result = run('--source', broken)
    check(result.returncode != 0, 'a missing duplicate guard fails the check')

    # Losing the enable write is equally fatal.
    broken2 = os.path.join(tmp, 'ArmCpu2.cpp')
    open(broken2, 'w', encoding='utf-8').write(
        source.replace('    write32(gDist,0x100+word,bit);',
                       '    (void)bit;'))
    result = run('--source', broken2)
    check(result.returncode != 0, 'a missing enable write fails the check')

    missing = run('--source', os.path.join(tmp, 'absent.cpp'))
    check(missing.returncode != 0, 'a missing source is refused')
    check('missing source' in missing.stdout + missing.stderr,
          'the refusal names the missing source')

    no_marker = os.path.join(tmp, 'nomarker.c')
    open(no_marker, 'w', encoding='utf-8').write('int main(void){return 0;}\n')
    result = run('--fixture', no_marker)
    check(result.returncode != 0, 'a fixture without the marker is refused')

    tree = run('--tree', tmp)
    check(tree.returncode != 0, 'an empty tree is refused')

if FAILURES:
    for failure in FAILURES:
        print('FAIL ' + failure)
    print('TESTS FAILED (%d/%d)' % (len(FAILURES), CASES))
    sys.exit(1)
print('TESTS OK %d case(s)' % CASES)
