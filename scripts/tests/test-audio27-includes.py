#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Host cases for check-audio27-includes.py: a full tree passes, a renamed
header is named with its source line, and a directory that is not an XNU
tree is refused rather than reported as passing."""
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
GATE = REPO / 'scripts/check-audio27-includes.py'
cases = 0

HEADERS = [
    'pexpert/pexpert/arm64/board_config.h',
    'osfmk/kern/clock.h',
    'pexpert/pexpert/pexpert.h',
    'bsd/sys/systm.h',
    'bsd/sys/types.h',
    'EXTERNAL_HEADERS/stdbool.h',
    'EXTERNAL_HEADERS/stdint.h',
    'osfmk/arm/string.h',
]


def tree(work, name, skip=()):
    root = work / name
    (root / 'bsd').mkdir(parents=True)
    for header in HEADERS:
        if header in skip:
            continue
        path = root / header
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('/* stub */' + chr(10))
    return root


def run(root):
    done = subprocess.run([sys.executable, str(GATE), str(root)],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return done.returncode, done.stdout


def main():
    global cases
    work = pathlib.Path(tempfile.mkdtemp(prefix='inc27-'))
    full = tree(work, 'full')
    code, out = run(full)
    assert code == 0, out
    assert 'INCLUDES OK 8 headers resolve' in out, out
    cases += 1
    print('  ok   a tree with every header passes')

    no_string = tree(work, 'nostring', skip=('osfmk/arm/string.h',))
    code, out = run(no_string)
    assert code == 1, out
    assert 'string.h' in out and 'PongAudioAmp.c' in out, out
    cases += 1
    print('  ok   a renamed string.h is named with its source')

    no_systm = tree(work, 'nosystm', skip=('bsd/sys/systm.h',))
    code, out = run(no_systm)
    assert code == 1, out
    assert 'sys/systm.h' in out, out
    cases += 1
    print('  ok   a missing sys/systm.h is named')

    empty = work / 'empty'
    empty.mkdir()
    code, out = run(empty)
    assert code == 1, out
    assert 'not an XNU tree' in out, out
    cases += 1
    print('  ok   a directory without bsd/ is refused')

    print('TESTS OK %d cases' % cases)


if __name__ == '__main__':
    main()
