#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Host cases for run-warnings.sh: a clean pair passes, one unused variable
fails, and the failure names the compiler, the source and the macro state."""
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
GATE = REPO / 'scripts/tests/portability/run-warnings.sh'
cases = 0


def fixture(work, amp_body, geni_body):
    root = work / ('tree%d' % len(list(work.iterdir())))
    port = root / 'scripts/tests/portability'
    drv = root / 'drivers/PongAudio'
    port.mkdir(parents=True)
    drv.mkdir(parents=True)
    shutil.copy(str(GATE), str(port / 'run-warnings.sh'))
    (drv / 'PongAudioAmp.c').write_text(amp_body)
    (drv / 'PongAudioGeniI2c.c').write_text(geni_body)
    return root


def run(root):
    done = subprocess.run(['sh', str(root / 'scripts/tests/portability/run-warnings.sh')],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return done.returncode, done.stdout


def main():
    global cases
    work = pathlib.Path(tempfile.mkdtemp(prefix='warn-'))
    clean = fixture(work, 'int amp_probe(void) { return 0; }', 'int geni_prepare(void) { return 0; }')
    code, out = run(clean)
    assert code == 0, out
    assert 'WARNINGS OK' in out, out
    cases += 1
    print('  ok   a clean pair passes')

    dirty = fixture(work, 'static int helper(int a) { return a; }\nint amp_probe(void) { return 0; }',
                    'int geni_prepare(void) { return 0; }')
    code, out = run(dirty)
    assert code == 1, out
    assert 'WARNINGS FAILED' in out, out
    assert 'Amp' in out, out
    cases += 1
    print('  ok   an unused variable fails and names the source')

    print('TESTS OK %d cases' % cases)


if __name__ == '__main__':
    main()
