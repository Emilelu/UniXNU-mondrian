#!/usr/bin/env python3
"""Exercise scripts/check-xnu27-source-storage.py against synthetic checkouts."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / 'scripts/check-xnu27-source-storage.py'
PROFILE = 'ios-27.0.1-24A446'

passed = 0
failed = 0


def case(name, ok, detail=None):
    global passed, failed
    if ok:
        passed += 1
        print(f'  OK   {name}')
    else:
        failed += 1
        print(f'  FAIL {name}')
        if detail:
            print(detail)


def make(root, include='["ArmDTPlatform", "ArmCpu", "XnuPrelink"]', ufs='n',
         builder_line='  UFS_ARCHIVE=$ROOT/build/sheng-ufs/libPongUfs.a\n',
         patches=None, source=True, framework=None):
    root = Path(root)
    (root / 'drivers/NativeUfs').mkdir(parents=True)
    if source:
        (root / 'drivers/NativeUfs/NativeUfs.cpp').write_text('// driver\n')
        (root / 'drivers/NativeUfs/PongUfsTransport.cpp').write_text('// transport\n')
    (root / 'configs').mkdir()
    (root / 'configs/mondrian_ios27_defconfig').write_text(
        f'CONFIG_XNU_BUILD_ARCHIVES=y\nCONFIG_XNU_NATIVE_UFS={ufs}\n')
    (root / 'scripts').mkdir(exist_ok=True)
    (root / 'scripts/build-xnu-generic.sh').write_text(
        'set -e\nif [ "${XNU_NATIVE_UFS:-0}" = 1 ]; then\n' + builder_line + 'fi\n')
    (root / 'patches/xnu-12377').mkdir(parents=True)
    entries = patches if patches is not None else ['0500-k60-example.patch']
    (root / 'patches/xnu-12377/series').write_text('\n'.join(entries) + '\n')
    for entry in entries:
        (root / 'patches/xnu-12377' / entry).write_text('--- a/x\n+++ b/x\n')
    (root / 'board.toml').write_text(
        f'[os_overrides."{PROFILE}"]\nremove = []\n\n'
        f'[os_overrides."{PROFILE}".components]\ninclude = {include}\n\n'
        f'[os_overrides."{PROFILE}".kernel]\ndefconfig = "mondrian_ios27_defconfig"\n'
        f'patch_series = ["device:patches/xnu-12377/series"]\n')
    if framework:
        framework = Path(framework)
        (framework / 'kits/VerifiedRoot').mkdir(parents=True)
        (framework / 'scripts/policies' / PROFILE).mkdir(parents=True)
        (framework / 'scripts/build-sheng-source-storage.py').write_text('# builder\n')


def run(root, framework=None, extra=()):
    arguments = [sys.executable, str(CHECKER), '--root', str(root)]
    if framework:
        arguments += ['--framework', str(framework)]
    arguments += list(extra)
    done = subprocess.run(arguments, capture_output=True, text=True)
    return done.returncode, done.stdout + done.stderr


def main():
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)

        bare = work / 'bare'
        make(bare)
        code, output = run(bare, work / 'no-framework')
        case('a checkout with no storage wiring reports five gaps', code == 0 and '5 gap(s)' in output, output)
        case('it still finds the driver sources',
             'OK   the block storage driver sources' in output, output)
        case('it names the builder line that links the wrong archive',
             'build-xnu-generic.sh:3' in output and 'libPongUfs.a' in output, output)

        selected = work / 'selected'
        make(selected, include='["ArmDTPlatform", "ArmCpu", "XnuPrelink", "NativeUfs"]', ufs='y')
        code, output = run(selected, work / 'no-framework')
        case('selecting the component and the defconfig closes two gaps',
             '3 gap(s)' in output, output)
        case('it shows the component list it read',
             "include = ['ArmDTPlatform', 'ArmCpu', 'XnuPrelink', 'NativeUfs']" in output, output)
        case('it shows the defconfig value it read',
             'CONFIG_XNU_NATIVE_UFS=y' in output, output)

        linked = work / 'linked'
        make(linked, include='["NativeUfs"]', ufs='y',
             builder_line='  UFS_ARCHIVE=$ROOT/build/native-ufs/libNativeUfs.a\n')
        code, output = run(linked, work / 'no-framework')
        case('a builder that links libNativeUfs.a closes that gap',
             'GAP  the builder links' not in output, output)

        personality = work / 'personality'
        make(personality, include='["NativeUfs"]', ufs='y',
             builder_line='  UFS_ARCHIVE=$ROOT/build/native-ufs/libNativeUfs.a\n',
             patches=['0500-k60-example.patch', '0543-k60-native-ufs-personality.patch'])
        (personality / 'patches/xnu-12377/0543-k60-native-ufs-personality.patch').write_text(
            '--- a/iokit/KernelConfigTables.cpp\n+++ b/iokit/KernelConfigTables.cpp\n+ IOClass NativeUfs\n')
        code, output = run(personality, work / 'no-framework')
        case('a personality patch closes the last code gap',
             '1 gap(s)' in output and '0543-k60-native-ufs-personality.patch' in output, output)

        framework = work / 'UniXNU'
        (framework / 'scripts/policies' / PROFILE).mkdir(parents=True)
        (framework / 'scripts/policies' / PROFILE / 'OS.bin').write_text('policy\n')
        (framework / 'scripts/build-sheng-source-storage.py').write_text('# builder\n')
        (framework / 'kits/VerifiedRoot').mkdir(parents=True)
        code, output = run(personality, framework, ['--require'])
        case('with the policies and the kit the closure reports no gaps', code == 0 and '0 gap(s)' in output, output)

        code, output = run(bare, work / 'no-framework', ['--require'])
        case('--require turns the gaps into a failure', code == 1, output)

        report = work / 'report'
        code, output = run(bare, work / 'no-framework', ['--out', str(report)])
        data = json.loads((report / 'report.json').read_text())
        case('the report lists every piece and the work order',
             len(data['pieces']) == 6 and len(data['gaps']) == 5 and len(data['order']) == 6
             and data['hardware_verified'] is False, data)

        nosrc = work / 'nosrc'
        make(nosrc, source=False)
        code, output = run(nosrc, work / 'no-framework')
        case('a checkout without the driver sources says so',
             'GAP  the block storage driver sources' in output and '6 gap(s)' in output, output)

        missing = work / 'empty'
        missing.mkdir()
        code, output = run(missing, work / 'no-framework')
        case('a missing board.toml fails loudly', code != 0 and 'not found' in output, output)

    print(f'TESTS {passed + failed} case(s): {passed} passed, {failed} failed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
