#!/usr/bin/env python3
"""Tests for scripts/check-probe-cadence.py.

A gate that currently reports zero problems proves nothing on its own - it may simply not
look at the shape it claims to catch (P-242). These fixtures make the gate prove both
directions: the exact cadence that wasted three flights must fail, and the three shapes that
must stay legal (early-sample clause, alignment mask, non-report gate) must pass.
"""
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GATE = os.path.join(REPO, 'scripts', 'check-probe-cadence.py')

FAILED = []
CASES = 0
PY = sys.executable


def check(name, ok, detail=''):
    global CASES
    CASES += 1
    if ok:
        print('  ok   %s' % name)
    else:
        print('  FAIL %s%s' % (name, (': ' + detail) if detail else ''))
        FAILED.append(name)


def run(fixture):
    """Run the gate against a tree containing one synthetic driver file."""
    tmp = tempfile.mkdtemp(prefix='cadence-')
    try:
        drivers = os.path.join(tmp, 'drivers', 'PongTest')
        os.makedirs(drivers)
        with open(os.path.join(drivers, 'Probe.cpp'), 'w', encoding='utf-8') as handle:
            handle.write(fixture)
        env = dict(os.environ, K60_REPO=tmp)
        done = subprocess.run([PY, GATE], env=env, capture_output=True, text=True,
                              encoding='utf-8', errors='replace')
        return done.returncode, (done.stdout or '') + (done.stderr or '')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')

    # The exact shape that cost three flights (P-233): a report every 32nd event, so a
    # fifteen-event flight printed nothing and the judge read "the probe did not run".
    bad = """void f(void) {
    static unsigned probed;
    if (!(++probed & 31)) {
        IOLog("PONG SUB: sample n=%u\\n", probed);
    }
}
"""
    code, out = run(bad)
    check('a report every 32nd event fails', code == 1, out.strip().split('\n')[0] if out else '')

    bad60 = """void g(unsigned copies) {
    if (!(copies % 60)) printf("scanout frames=%u\\n", copies);
}
"""
    code, _ = run(bad60)
    check('a report every 60th event fails', code == 1)

    good_early = """void f(void) {
    static unsigned probed;
    if (++probed <= 4 || !(probed & 31)) {
        IOLog("PONG SUB: sample n=%u\\n", probed);
    }
}
"""
    code, out = run(good_early)
    check('the same cadence with an early window passes', code == 0, out.strip())

    align = """void h(unsigned physical, unsigned bytes) {
    if ((physical & 4095) || (bytes & 4095)) {
        IOLog("alignment rejected\\n");
    }
}
"""
    code, out = run(align)
    check('a page-alignment mask is not a sampling gate', code == 0, out.strip())

    not_a_report = """void i(unsigned n) {
    unsigned total = 0;
    if (!(n % 16)) total += n;
}
"""
    code, out = run(not_a_report)
    check('a modulo that does not gate a report is ignored', code == 0, out.strip())

    print('TESTS %s %d case(s) (%d failure(s))'
          % ('OK' if not FAILED else 'FAILED', CASES, len(FAILED)))
    return 0 if not FAILED else 1


if __name__ == '__main__':
    sys.exit(main())
