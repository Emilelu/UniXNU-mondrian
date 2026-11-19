#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
# Copyright (c) 2026, UniXNU contributors.
"""Run the K60 GIC SPI ownership code against a distributor model.

The Bluetooth path shares the interrupt controller with UFS, PCIe and the
TLMM summary: armcpu_spi_attach() is the single place that publishes an SPI
owner, programs the router and enables the line.  A mistake there is not
local to Bluetooth, so this check compiles the production fragment from
drivers/ArmCpu/ArmCpu.cpp against a model of the GICD registers and exercises
the ownership rules, the register writes and the concurrency guard.

It reads the source, it does not boot anything.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

OWNERS_START = '/* Published SPI owners, following Sheng'
OWNERS_END = 'class ArmCpu : public IOCPU'
ATTACH_START = 'extern "C" IOReturn armcpu_spi_attach('
ATTACH_END = '\nvoid ArmCpu::signalCPU(IOCPU *target)'
MARKER = '/* @@EXTRACT@@ */'


def fail(message):
    print('bluetooth-gic-check: ' + message)
    return 1


def slice_of(source, start, end, name):
    if start not in source:
        raise SystemExit(fail('missing ' + name + ' start'))
    begin = source.index(start)
    if end not in source[begin:]:
        raise SystemExit(fail('missing ' + name + ' end'))
    return source[begin:source.index(end, begin)]


def fragment(source):
    owners = slice_of(source, OWNERS_START, OWNERS_END, 'the SPI owner block')
    attach = slice_of(source, ATTACH_START, ATTACH_END, 'armcpu_spi_attach')
    body = owners + '\n' + attach
    # dsb is a device barrier on the board; the model needs a compiler fence.
    body = body.replace('__asm__ volatile("dsb sy":::"memory");',
                        '__atomic_thread_fence(__ATOMIC_SEQ_CST);')
    for needed in ('struct SpiOwner', 'armcpu_spi_attach', 'gSpiRegistering',
                   'gBootAffinity', 'kIOReturnNoResources', 'gSpiUsed'):
        if needed not in body:
            raise SystemExit(fail('the fragment lost ' + needed))
    return body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tree', default=None,
                        help='tree that holds drivers/ArmCpu/ArmCpu.cpp')
    parser.add_argument('--source', default=None,
                        help='ArmCpu.cpp to read instead of --tree')
    parser.add_argument('--fixture', default=None,
                        help='harness that carries the extract marker')
    parser.add_argument('--out', default=None, help='directory for report.json')
    parser.add_argument('--keep', action='store_true',
                        help='keep the generated translation unit')
    args = parser.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    source_path = args.source
    if not source_path:
        for candidate in ('drivers/ArmCpu/ArmCpu.cpp',
                           'drivers/armcpu-darwin24/ArmCpu.cpp'):
            source_path = os.path.join(args.tree or root, candidate)
            if os.path.exists(source_path):
                break
    fixture_path = args.fixture or os.path.join(
        root, 'scripts', 'tests', 'fixtures', 'bt-gic-shared.c')
    if not os.path.exists(source_path):
        return fail('missing source: ' + source_path)
    if not os.path.exists(fixture_path):
        return fail('missing fixture: ' + fixture_path)

    source = open(source_path, encoding='utf-8').read()
    body = fragment(source)
    harness = open(fixture_path, encoding='utf-8').read()
    if harness.count(MARKER) != 1:
        return fail('the fixture must carry exactly one extract marker')
    unit = harness.replace(MARKER, body)

    compiler = shutil.which('clang++') or shutil.which('g++')
    if not compiler:
        return fail('no C++ compiler')
    command = [compiler, '-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
               '-pthread', '-fsanitize=address,undefined', '-x', 'c++', '-']

    work = tempfile.mkdtemp(prefix='bt-gic-')
    try:
        unit_path = os.path.join(work, 'unit.cc')
        binary = os.path.join(work, 'unit')
        open(unit_path, 'w', encoding='utf-8').write(unit)
        # The model compiles a slice of ArmCpu.cpp: a global the slice carries
        # (the platform sleep hook sits beside the SPI owners) but the
        # assertions never touch is expected, so unused-variable stays quiet.
        build = subprocess.run([compiler, '-std=c++17', '-O1', '-g', '-Wall',
                                '-Wextra', '-Werror',
                                '-Wno-unused-variable',
                                '-Wno-unused-const-variable', '-pthread',
                                '-fsanitize=address,undefined', unit_path,
                                '-o', binary],
                               capture_output=True, text=True)
        if build.returncode != 0:
            print(build.stdout + build.stderr)
            return fail('the fragment does not compile against the model')
        run = subprocess.run([binary], capture_output=True, text=True)
        print(run.stdout.rstrip())
        if run.returncode != 0:
            print(run.stderr.rstrip())
            return fail('the model reported a failure')
        match = re.search(r'OK \((\d+) assertion\(s\), (\d+) write\(s\)\)', run.stdout)
        if not match:
            return fail('the model did not report its counts')
        assertions = int(match.group(1))
        writes = int(match.group(2))

        report = {
            'passed': True,
            'hardware_verified': False,
            'assertions': assertions,
            'distributor_writes': writes,
            'source': os.path.basename(source_path),
            'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
            'fragment_sha256': hashlib.sha256(body.encode()).hexdigest(),
            'fixture_sha256': hashlib.sha256(harness.encode()).hexdigest(),
            'compiler': os.path.basename(compiler),
            'compile_command': ' '.join(command),
        }
        if args.out:
            os.makedirs(args.out, exist_ok=True)
            open(os.path.join(args.out, 'report.json'), 'w',
                 encoding='utf-8').write(json.dumps(report, indent=2) + '\n')
            open(os.path.join(args.out, 'output.txt'), 'w',
                 encoding='utf-8').write(run.stdout)
        if args.keep:
            print('unit: ' + unit_path)
        print('bluetooth-gic-check: OK (%d assertion(s), %d write(s))'
              % (assertions, writes))
        return 0
    finally:
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
