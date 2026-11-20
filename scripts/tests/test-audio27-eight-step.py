#!/usr/bin/env python3
"""test-audio27-eight-step.py — the seven-step record checker must reject drift.

Cases: valid, missing step, device step, evidence not a list, unresolved line,
missing recorded_at, verify without artifact_check, official without docs/zh.
"""
import os
import re
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHECKER = os.path.join(REPO, 'scripts', 'check-audio27-eight-step.py')
SOURCE = os.path.join(REPO, 'docs', 'research', 'eight-step', 'audio-27.toml')
BASE = open(SOURCE, encoding='utf-8').read()


def run(text):
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, 'audio-27.toml')
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
        return subprocess.run([sys.executable, CHECKER, '--data', path],
                              capture_output=True, text=True, timeout=60)


def expect(name, text, rc, needle):
    r = run(text)
    ok = r.returncode == rc and needle in (r.stdout + r.stderr)
    print('%s %s' % ('PASS' if ok else 'FAIL', name))
    if not ok:
        print('  rc=%s wanted=%s' % (r.returncode, rc))
        print('  needle=%r' % needle)
        print((r.stdout + r.stderr).strip()[:800])
    return ok


def main():
    cases = []
    cases.append(expect('seven-step file is accepted', BASE, 0, 'AUDIO27 EIGHT-STEP OK: 7 steps'))
    t = BASE.replace('[hardware.audio.step.verify]', '[hardware.audio.step.verify_extra]')
    cases.append(expect('missing step is named', t, 1, 'missing step(s): verify'))
    t = BASE + '\n[hardware.audio.step.device]\ndone = false\nrecorded_at = "2026-11-21T03:37:00"\nevidence = []\n'
    cases.append(expect('device step is refused', t, 1, 'unexpected step(s): device'))
    t = re.sub(r'(\[hardware\.audio\.step\.same_model\][^\n]*\n(?:[^\n]*\n)*?)evidence = \[.*?\n\]',
               r'\1evidence = "short"', BASE, count=1, flags=re.S)
    cases.append(expect('string evidence is refused', t, 1, 'evidence is not a non-empty list'))
    t = BASE.replace('docs/research/audio/RESEARCH.md:11-23',
                     'docs/research/audio/RESEARCH.md:99999', 1)
    cases.append(expect('unresolved line is named', t, 1, 'RESEARCH.md:99999'))
    t = BASE.replace('recorded_at = "2026-11-21T03:37:00"\n', '', 1)
    cases.append(expect('missing recorded_at is named', t, 1, 'recorded_at=YYYY-MM-DDTHH:MM:SS'))
    t = BASE.replace('artifact_check = [', 'artifact_check_missing = [', 1)
    cases.append(expect('verify missing a class is named', t, 1, 'has no artifact_check'))
    t = BASE.replace('UniXNU:docs/zh/', 'UniXNU:docs/xx/')
    cases.append(expect('official outside docs/zh is refused', t, 1, 'needs a docs/zh page'))
    r = subprocess.run([sys.executable, CHECKER, '--help'], capture_output=True, text=True, timeout=60)
    ok = r.returncode == 0 and 'usage:' in r.stdout
    print('%s --help is clean' % ('PASS' if ok else 'FAIL'))
    cases.append(ok)
    print('TESTS OK %d cases' % len(cases) if all(cases) else 'TESTS FAILED %d of %d cases'
          % (cases.count(False), len(cases)))
    return 0 if all(cases) else 1


if __name__ == '__main__':
    sys.exit(main())
