#!/usr/bin/env python3
"""Prove the XNU patch series assembles, in build order, on a throwaway clone.

Why this exists (P-312): `check-patch-apply.py` only proves a patch parses and
`check-series-numbering.py` only proves numbers are unique. Neither proves the
series can be *applied in order* — and `unixnu build kernel` applies the series
strictly in file order, aborting the whole step on the first failure. The only
honest test is to replay the four layers the way the builder does:

    arch -> soc -> os -> device

Entries may carry a scope prefix (`arch:../../../patches/...`); those resolve
against the layer root, exactly like scripts/unixnu/profiles.py does.

Exit codes: 0 every patch applied, 1 any patch failed, 2 the inputs are missing
(an unreadable input is not a pass — P-251/P-279).
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_FEED = '/opt/k60/trees/ios27-out/feeds/xnu-3199e8bc'


def framework_root() -> pathlib.Path:
    env = os.environ.get('K60_FRAMEWORK')
    if env:
        return pathlib.Path(env)
    return REPO.parent / 'UniXNU'


def os_profile() -> str:
    text = (REPO / 'board.toml').read_text(encoding='utf-8')
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('os_profile'):
            return line.split('=', 1)[1].strip().strip('"')
    return ''


def soc_feed() -> pathlib.Path:
    env = os.environ.get('K60_SOC_FEED')
    if env:
        return pathlib.Path(env)
    feeds = pathlib.Path('/opt/k60/trees/ios27-out/feeds')
    matches = sorted(feeds.glob('UniXNU-sm8475-common-*'))
    if not matches:
        raise SystemExit('FAIL: no soc feed under %s (set K60_SOC_FEED)' % feeds)
    return matches[-1]


def series_entries(path: pathlib.Path):
    if not path.exists():
        return None
    return [l.strip() for l in path.read_text(encoding='utf-8').splitlines()
            if l.strip() and not l.strip().startswith('#')]


def main() -> int:
    fw = framework_root()
    profile = os_profile()
    if not profile:
        print('FAIL: board.toml has no [board].os_profile')
        return 2
    os_root = fw / 'profiles/os' / profile
    os_arch = 'arm64'
    profile_toml = os_root / 'profile.toml'
    if profile_toml.is_file():
        import tomllib
        data = tomllib.loads(profile_toml.read_text(encoding='utf-8'))
        os_arch = data.get('os', {}).get('arch', 'arm64')
    roots = {
        'arch': fw / 'profiles/arch' / os_arch,
        'soc': soc_feed(),
        'os': os_root,
        'device': REPO,
    }
    layers = [
        ('arch', roots['arch'] / 'patches/xnu/series'),
        ('soc', roots['soc'] / 'patches/xnu-12377/series'),
        ('os', roots['os'] / 'patches/xnu/series'),
        ('device', REPO / 'patches/xnu-12377/series'),
    ]
    for name, series in layers:
        if not series.exists():
            print('FAIL: %s layer series is missing: %s' % (name, series))
            return 2

    feed = os.environ.get('K60_XNU_FEED', DEFAULT_FEED)
    work = pathlib.Path(tempfile.mkdtemp(prefix='k60-series-order-'))
    clone = work / 'tree'
    try:
        subprocess.run(['git', 'clone', '-q', '--shared', feed, str(clone)],
                       check=True, capture_output=True)
        total_ok = total_bad = 0
        for name, series in layers:
            listed = series_entries(series) or []
            ok = bad = 0
            for item in listed:
                prefix, _, rest = item.partition(':')
                if rest and prefix in roots:
                    patch = roots[prefix] / rest
                else:
                    patch = series.parent / item
                if not patch.exists():
                    print('FAIL: %s: %s does not exist' % (name, patch))
                    bad += 1
                    continue
                result = subprocess.run(
                    ['git', '-C', str(clone), 'apply', '--whitespace=nowarn', str(patch)],
                    capture_output=True, text=True)
                if result.returncode:
                    bad += 1
                    print('  FAIL %s: %s' % (item, (result.stderr or '').splitlines()[:1]))
                else:
                    ok += 1
            total_ok += ok
            total_bad += bad
            print('%s: %d applied, %d failed' % (name, ok, bad))
        print('TOTAL applied=%d failed=%d' % (total_ok, total_bad))
        if total_bad:
            print('结论: ❌ 序列不能装配（P-312）；构建会在这条补丁上整步失败')
            return 1
        print('结论: ✅ 四层序列按构建顺序全部可用（P-312）')
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
