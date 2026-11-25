#!/usr/bin/env python3
"""P-315: an ABI fixture enumerated from one kernelcache must not be used on another.

The generator refuses before writing anything when the fixture's recorded
kernelcache_sha256 differs from the local kernelcache.  K60_ALLOW_FOREIGN_FIXTURE=1
is an inspection escape hatch only; it must not silence the guard silently.
"""
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[2]
GEN = REPO / 'scripts/gen-legacy-display-abi.py'
CASES = []


def make_tree(tmp, fixture_sha):
    tree = pathlib.Path(tmp) / 'tree'
    (tree / 'scripts').mkdir(parents=True)
    (tree / 'scripts/kernel_target.py').write_text(
        "ARCH='arm64e'\nIOS_VERSION='27.0'\nTRIPLE='arm64e-apple-ios27.0'\n")
    shutil.copy(GEN, tree / 'scripts/gen-legacy-display-abi.py')
    (tree / 'scripts/legacy-display-24A446.json').write_text(json.dumps({
        'kernelcache_sha256': fixture_sha,
        'collection_slide': '0x1f000000000',
    }))
    return tree


def run(tree, kc, extra=None):
    env = dict(os.environ)
    env['PYTHONPATH'] = str(tree / 'scripts')
    env['K60_KERNELCACHE'] = str(kc)
    env.pop('K60_ALLOW_FOREIGN_FIXTURE', None)
    env.update(extra or {})
    return subprocess.run([sys.executable, str(tree / 'scripts/gen-legacy-display-abi.py')],
                          cwd=str(tree), env=env, capture_output=True, text=True)


def check(name, ok, detail=''):
    CASES.append((name, ok, detail))


with tempfile.TemporaryDirectory() as tmp:
    kc = pathlib.Path(tmp) / 'kernelcache'
    kc.write_bytes(b'local kernelcache bytes')
    local = hashlib.sha256(kc.read_bytes()).hexdigest()
    foreign = '38e6d9fa' + '0' * 56

    tree = make_tree(tmp, foreign)
    r = run(tree, kc)
    check('a foreign fixture is refused', r.returncode != 0 and 'not valid here' in r.stderr, r.stderr[-200:])
    check('the refusal names both kernelcaches', foreign[:16] in r.stderr and local[:16] in r.stderr, r.stderr[-200:])
    check('the refusal writes no header', not (tree / 'build/native-legacy-display/OriginalLegacyFramebufferABI.h').exists())

    r2 = run(tree, kc, {'K60_ALLOW_FOREIGN_FIXTURE': '1'})
    check('the escape hatch is the only way past the guard', 'not valid here' not in r2.stderr, r2.stderr[-200:])

    tree2 = make_tree(pathlib.Path(tmp) / 'same', local)
    r3 = run(tree2, kc)
    check('a matching fixture passes the guard', 'not valid here' not in r3.stderr and 'enumerated from kernelcache' not in r3.stderr, r3.stderr[-200:])

failed = [c for c in CASES if not c[1]]
for name, ok, detail in CASES:
    print(('ok   ' if ok else 'FAIL ') + name + ('' if ok else ' :: ' + detail))
print(f'TESTS {"OK" if not failed else "FAILED"} {len(CASES) - len(failed)}/{len(CASES)}')
sys.exit(1 if failed else 0)
