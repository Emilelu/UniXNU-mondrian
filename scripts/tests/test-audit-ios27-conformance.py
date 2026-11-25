"""Tests for scripts/audit-ios27-conformance.py.

The checker exists because "we follow Sheng strictly" was an assertion nobody could
check: a defconfig lookup used *our* OS profile name against Sheng's board, and a
missing `[kernel.prelink]` produced 44 silent differences. These cases pin the three
things that made it lie.
"""

import importlib.util
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(HERE), 'audit-ios27-conformance.py')

_cases = []


def case(fn):
    _cases.append(fn)
    return fn


def load():
    spec = importlib.util.spec_from_file_location('conformance', TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules['conformance'] = module
    spec.loader.exec_module(module)
    return module


OUR_BOARD = """
schema_version = 2
[board]
os_profile = "ios-27.0.1-24A446"
[kernel]
driver_records = "DEVELOPMENT_ARM64_BCM2837"
config_fragments = ["arch:configs/common.config", "soc:configs/sm8475.config"]
patch_series = ["patches/xnu-12377/series"]
archives = ["build-k60-platform-archives.py", "component:ArmCpu"]
[package.defconfig]
"ios-27.0.1-24A446" = "mondrian_ios27_defconfig"
"""

SHENG_BOARD = """
schema_version = 2
[board]
os_profile = "ipados-27.0.1-24A446"
[kernel]
config_fragments = ["arch:configs/common.config", "os:configs/ipados.config"]
patch_series = ["patches/xnu-12377/series"]
archives = ["component:ArmCpu", "build-gop-legacy-display-27.py"]
[kernel.prelink]
roots = ["com.apple.iokit.IOStorageFamily", "com.apple.security.sandbox"]
[package.defconfig]
"ipados-27.0.1-24A446" = "sheng_ipados27_defconfig"
"""

OUR_CFG = "CONFIG_XNU_ARM_DT_PLATFORM=y\nCONFIG_XNU_NATIVE_ADRENO=n\n"
SHENG_CFG = "CONFIG_XNU_ARM_DT_PLATFORM=y\nCONFIG_XNU_NATIVE_ADRENO=y\n"


def world(base):
    ours = os.path.join(base, 'ours')
    sheng = os.path.join(base, 'sheng')
    for root in (ours, sheng):
        os.makedirs(os.path.join(root, 'configs'), exist_ok=True)
    open(os.path.join(ours, 'board.toml'), 'w', encoding='utf-8').write(OUR_BOARD)
    open(os.path.join(sheng, 'board.toml'), 'w', encoding='utf-8').write(SHENG_BOARD)
    open(os.path.join(ours, 'configs', 'mondrian_ios27_defconfig'), 'w').write(OUR_CFG)
    open(os.path.join(sheng, 'configs', 'sheng_ipados27_defconfig'), 'w').write(SHENG_CFG)
    open(os.path.join(ours, 'NOTES.md'), 'w').write('line1\nline2\n')
    return ours, sheng


@case
def defconfig_is_looked_up_under_each_tree_s_own_profile(base):
    mod = load()
    ours, sheng = world(base)
    rows = {(r['key']): r for r in mod.collect(ours, sheng)}
    row = rows['config:CONFIG_XNU_ARM_DT_PLATFORM']
    assert row['ours'] == 'y' and row['sheng'] == 'y', row
    assert rows['package.defconfig[27]']['sheng'] == 'sheng_ipados27_defconfig'


@case
def a_missing_prelink_section_is_reported_not_ignored(base):
    mod = load()
    ours, sheng = world(base)
    rows = {(r['key']): r for r in mod.collect(ours, sheng)}
    assert rows['kernel.prelink.roots']['ours'] == ('no [kernel.prelink]',)
    assert rows['prelink-root:com.apple.security.sandbox']['ours'] == mod.MISSING


@case
def an_unexplained_difference_is_a_gap(base):
    mod = load()
    ours, sheng = world(base)
    rows = mod.collect(ours, sheng)
    out = mod.classify(rows, {}, ours)
    gap = [r for r in out if r['key'] == 'config:CONFIG_XNU_NATIVE_ADRENO'][0]
    assert gap['state'] == 'GAP'


@case
def a_justification_with_unresolvable_evidence_falls_back_to_gap(base):
    mod = load()
    ours, sheng = world(base)
    rows = mod.collect(ours, sheng)
    deviations = {'config:CONFIG_XNU_NATIVE_ADRENO':
                  {'reason': 'stage-0 keeps it off', 'evidence': 'NOTHERE.md:1'}}
    out = mod.classify(rows, deviations, ours)
    row = [r for r in out if r['key'] == 'config:CONFIG_XNU_NATIVE_ADRENO'][0]
    assert row['state'] == 'GAP' and 'does not resolve' in row['why'], row


@case
def a_justification_with_resolvable_evidence_is_justified(base):
    mod = load()
    ours, sheng = world(base)
    rows = mod.collect(ours, sheng)
    deviations = {'config:CONFIG_XNU_NATIVE_ADRENO':
                  {'reason': 'stage-0 keeps it off', 'evidence': 'NOTES.md:2'}}
    out = mod.classify(rows, deviations, ours)
    row = [r for r in out if r['key'] == 'config:CONFIG_XNU_NATIVE_ADRENO'][0]
    assert row['state'] == 'justified', row


@case
def prefixes_justify_a_family_of_archives(base):
    mod = load()
    ours, sheng = world(base)
    rows = mod.collect(ours, sheng)
    deviations = {'prefix:archive:build-gop-':
                  {'reason': 'display comes later', 'evidence': 'NOTES.md:1'}}
    out = mod.classify(rows, deviations, ours)
    row = [r for r in out if r['key'] == 'archive:build-gop-legacy-display-27.py'][0]
    assert row['state'] == 'justified', row


@case
def archive_keys_ignore_arguments(base):
    mod = load()
    assert mod._norm_archive('build-gop-legacy-display-27.py --tree .') == 'build-gop-legacy-display-27.py'
    assert mod._norm_archive('component:ArmCpu') == 'component:ArmCpu'
    assert mod._norm_archive('{tree}/scripts/x.py') == 'x.py'


@case
def the_os_overlay_wins_over_the_base(base):
    mod = load()
    base = {'driver_records': 'A', 'archives': ['one']}
    overlay = {'driver_records': 'B', 'remove': ['archives']}
    merged = mod._overlay(base, overlay)
    assert merged['driver_records'] == 'B' and 'archives' not in merged, merged


@case
def exit_code_is_nonzero_while_any_gap_remains(base):
    mod = load()
    ours, sheng = world(base)
    argv = ['--ours', ours, '--sheng', sheng, '--deviations', 'none.toml']
    assert mod.main(argv) == 1


def main():
    failed = 0
    for fn in _cases:
        with tempfile.TemporaryDirectory() as base:
            try:
                fn(base)
                print('ok   %s' % fn.__name__)
            except AssertionError as exc:
                failed += 1
                print('FAIL %s: %s' % (fn.__name__, exc))
    if failed:
        print('FAILED %d of %d' % (failed, len(_cases)))
        return 1
    print('OK %d cases: the conformance audit reads each tree s own profile, calls an '
          'unexplained difference a gap, and refuses a reason whose evidence does not resolve'
          % len(_cases))
    return 0


if __name__ == '__main__':
    sys.exit(main())
