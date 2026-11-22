#!/usr/bin/env python3
"""Tests for scripts/check-force-load-producers.py.

Two small trees stand in for the real one: a builder that force-loads an archive
a local recipe writes, and a builder that force-loads an archive nobody writes
(the P-267 shape). The third case asks the real tree and expects no gaps.
"""
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
CHECK = ROOT / 'scripts/check-force-load-producers.py'
CASES = []


def case(name, ok, detail=None):
    CASES.append((name, ok, detail))


def tree(base, body, producer=None, catalog=None):
    (base / 'scripts').mkdir(parents=True)
    (base / 'scripts/build-xnu-generic.sh').write_text('#!/bin/sh\nset -eu\n' + body)
    if producer:
        (base / 'scripts/build-known-thing.py').write_text('# writes build/known/libKnown.a\n')
    if catalog:
        framework = base / 'framework'
        framework.mkdir()
        (framework / 'components.toml').write_text(catalog)
    return base


def run(repo, framework=None):
    args = [sys.executable, str(CHECK), '--repo', str(repo)]
    if framework:
        args += ['--framework', str(framework)]
    return subprocess.run(args, capture_output=True, text=True)


with tempfile.TemporaryDirectory() as tmp:
    base = pathlib.Path(tmp)

    known = tree(base / 'known', 'KNOWN_ARCHIVE=$ROOT/build/known/libKnown.a\n'
                                'KERNEL_EXTRA_ARCHIVES="-Wl,-force_load,$KNOWN_ARCHIVE"\n',
                 producer=True)
    done = run(known)
    case('an archive a recipe writes is accepted',
         done.returncode == 0 and 'build/known/libKnown.a' in done.stdout
         and 'build-known-thing.py' in done.stdout, done.stdout)

    orphan = tree(base / 'orphan', 'ORPHAN_ARCHIVE=$ROOT/build/orphan/libOrphan.a\n'
                                   'KERNEL_EXTRA_ARCHIVES="-Wl,-force_load,$ORPHAN_ARCHIVE"\n')
    done = run(orphan)
    case('an archive nobody writes is a gap',
         done.returncode == 1 and 'no producer' in done.stdout and '1 gap(s)' in done.stdout, done.stdout)

    catalog = tree(base / 'catalog', 'STUB_ARCHIVE=$ROOT/build/stub/libStub.a\n'
                                     'KERNEL_EXTRA_ARCHIVES="-Wl,-force_load,$STUB_ARCHIVE"\n',
                   catalog='[[component]]\nid = "Stub"\noutputs = ["build/stub/libStub.a"]\n')
    done = run(catalog, framework=base / 'catalog/framework')
    case('a component output counts as the producer',
         done.returncode == 0 and 'component:Stub' in done.stdout, done.stdout)

    literal = tree(base / 'literal', 'KERNEL_EXTRA_ARCHIVES="-Wl,-force_load,$ROOT/build/literal/libLiteral.a"\n',
                   producer=False)
    (literal / 'scripts/build-xnu-4k-baseline.sh').write_text('build/literal/libLiteral.a\n')
    done = run(literal)
    case('a literal $ROOT path is parsed and graded',
         done.returncode == 0 and 'build/literal/libLiteral.a' in done.stdout, done.stdout)

    framework = pathlib.Path(os.environ.get('K60_FRAMEWORK_REPO', 'E:/hackios/UniXNU'))
    if (framework / 'components.toml').is_file():
        done = run(ROOT, framework=framework)
        case('the real tree has a producer for every site',
             done.returncode == 0 and '0 gap(s)' in done.stdout, done.stdout)

failed = [name for name, ok, _ in CASES if not ok]
for name, ok, detail in CASES:
    if not ok:
        print('FAILED CASE: %s' % name)
        if detail:
            print(detail[:1200])
print('TESTS %s %d case(s)' % ('FAILED' if failed else 'OK', len(CASES)))
sys.exit(1 if failed else 0)
