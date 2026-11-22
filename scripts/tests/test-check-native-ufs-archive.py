#!/usr/bin/env python3
"""Tests for scripts/check-native-ufs-archive.py.

Four states are graded: the key absent (skip), the key off (skip), the key on
with a producer and an archive that carries the symbols (ok), and the key on
with something missing (FAIL). The archive is a plain file here: symbol reading
goes through a fake llvm-nm shim, so the test needs no toolchain and no build.
"""
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
CHECK = ROOT / 'scripts/check-native-ufs-archive.py'
CASES = []


def case(name, ok, detail=None):
    CASES.append((name, ok, detail))


def make_repo(base, switch='y', producer=True, archive=True):
    (base / 'configs').mkdir(parents=True, exist_ok=True)
    (base / 'configs/mondrian_ios27_defconfig').write_text('CONFIG_XNU_NATIVE_UFS=%s\n' % switch)
    if producer:
        (base / 'scripts').mkdir(parents=True, exist_ok=True)
        (base / 'scripts/build-native-ufs-linux.py').write_text('#!/usr/bin/env python3\n')
    if archive:
        (base / 'build/native-ufs').mkdir(parents=True, exist_ok=True)
        (base / 'build/native-ufs/libNativeUfs.a').write_bytes(b'!<arch>\n')
    return base


def fake_nm(base, symbols=('_NativeUfs5start', '_PongUfsBlock')):
    path = base / 'fake-nm.py'
    path.write_text('import sys\nfor name in %r:\n    print("0000000000000000 T " + name)\n' % (list(symbols),))
    return '"%s" "%s"' % (sys.executable.replace('"', ''), path.as_posix())


def run(repo, extra=()):
    return subprocess.run([sys.executable, str(CHECK), '--repo', str(repo), *extra],
                          capture_output=True, text=True)


with tempfile.TemporaryDirectory() as tmp:
    base = pathlib.Path(tmp)

    absent = base / 'absent'
    (absent / 'configs').mkdir(parents=True)
    (absent / 'configs/mondrian_ios27_defconfig').write_text('CONFIG_XNU_CRYPTO_BOOTSTRAP="source"\n')
    done = run(absent)
    case('a defconfig without the key skips', done.returncode == 0 and 'skip' in done.stdout, done.stdout)

    off = make_repo(base / 'off', switch='n')
    done = run(off)
    case('the switch off skips and says why',
         done.returncode == 0 and 'SKIP CONFIG_XNU_NATIVE_UFS is off' in done.stdout, done.stdout)

    ready = make_repo(base / 'ready')
    done = run(ready, ['--nm', fake_nm(base)])
    case('a producer, an archive and the symbols pass',
         done.returncode == 0 and 'OK build/native-ufs/libNativeUfs.a carries' in done.stdout
         and 'ufs27-native-ufs-archive: ok' in done.stdout, done.stdout)

    no_producer = make_repo(base / 'noproducer', producer=False)
    done = run(no_producer, ['--nm', fake_nm(base)])
    case('a producer missing fails and names it',
         done.returncode == 1 and 'no producer' in done.stdout and 'FAIL (1)' in done.stdout, done.stdout)

    no_archive = make_repo(base / 'noarchive', archive=False)
    done = run(no_archive, ['--nm', fake_nm(base)])
    case('an archive missing fails and mentions the silent test -f',
         done.returncode == 1 and 'no archive' in done.stdout and 'test -f' in done.stdout, done.stdout)

    bare = make_repo(base / 'bare')
    done = run(bare, ['--nm', fake_nm(base, symbols=('_SomethingElse',))])
    case('an archive without the driver symbols fails',
         done.returncode == 1 and 'lacks' in done.stdout and 'NativeUfs5start' in done.stdout, done.stdout)

    done = run(make_repo(base / 'custom'), ['--nm', fake_nm(base, symbols=('_CustomThing',)),
                                            '--require-symbol', 'CustomThing'])
    case('--require-symbol replaces the default list',
         done.returncode == 0 and 'CustomThing' in done.stdout, done.stdout)

    done = run(make_repo(base / 'real'), ['--nm', 'definitely-not-an-nm'])
    case('a missing nm tool fails loudly', done.returncode == 1 and 'cannot read' in done.stdout, done.stdout)

    legacy = make_repo(base / 'legacy')
    (legacy / 'scripts/build-pong-ufs-probe-macos.py').write_text('#!/usr/bin/env python3\n')
    done = run(legacy, ['--nm', fake_nm(base), '--producer', str(legacy / 'scripts/build-pong-ufs-probe-macos.py')])
    case('a 16.6.1-only producer is labelled but accepted',
         done.returncode == 0 and 'NOTE 16.6.1-only' in done.stdout, done.stdout)

    done = run(legacy, ['--nm', fake_nm(base), '--strict',
                        '--producer', str(legacy / 'scripts/build-pong-ufs-probe-macos.py')])
    case('--strict rejects a 16.6.1-only producer',
         done.returncode == 1 and '16.6.1-only' in done.stdout, done.stdout)

failed = [name for name, ok, _ in CASES if not ok]
for name, ok, detail in CASES:
    if not ok:
        print('FAILED CASE: %s' % name)
        if detail:
            print(detail[:1200])
print('TESTS %s %d case(s)' % ('FAILED' if failed else 'OK', len(CASES)))
sys.exit(1 if failed else 0)
