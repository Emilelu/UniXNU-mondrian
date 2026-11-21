#!/usr/bin/env python3
"""check-official-scope.py -- the two na decisions in the official registry.

concepts/security.md and drivers/qcom-baseband.md are marked na because this
board's iOS 27 stage-0 profile does not select either stack.  An na is a
decision, not a silent drop: this gate re-reads the facts the decision rests on
and fails when any of them changes, which is the signal to re-audit the page
before the profile grows a trust cache or a baseband bridge.

    python3 scripts/check-official-scope.py --repo E:/hackios/k60-gates

Exit 0 when both pages are still out of profile, 1 when one premise moved.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TRUST_KEYS = ('CONFIG_XNU_NATIVE_TRUST_CACHE', 'CONFIG_XNU_OWNER_ROOT_TRUST',
              'CONFIG_XNU_TRUST_CACHE_RUNTIME')
SECURITY_PATCH = re.compile(r'trust.?cache|amfi|appsync', re.IGNORECASE)
BASEBAND_PATCH = re.compile(r'baseband|qcom.*ipa|applebaseband', re.IGNORECASE)
BASEBAND_CONFIG = re.compile(r'BASEBAND|MODEM|CELLULAR', re.IGNORECASE)
PATCH_NAME = re.compile(r'^\s*([^#\s][^\s]*\.patch)\s*$', re.MULTILINE)


def load_board(repo: Path) -> dict:
    path = repo / 'board.toml'
    return tomllib.loads(path.read_text(encoding='utf-8'))


def config_lines(repo: Path):
    for path in sorted((repo / 'configs').glob('*defconfig')):
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            yield path.name, number, line.strip()


def series_names(repo: Path) -> list[str]:
    path = repo / 'patches/xnu-12377/series'
    if not path.is_file():
        return []
    return [name for name in PATCH_NAME.findall(path.read_text(encoding='utf-8'))]


def security_problems(repo: Path, board: dict) -> list[str]:
    problems: list[str] = []
    payload = board.get('payload', {})
    trust = payload.get('trust_cache_sha256', [])
    if trust:
        problems.append(f'board.toml: payload.trust_cache_sha256 is {trust!r}, not empty; '
                        'the security page is no longer na, re-audit it')
    for name, number, line in config_lines(repo):
        for key in TRUST_KEYS:
            if re.match(rf'^{re.escape(key)}\s*=\s*[yY]\b', line):
                problems.append(f'configs/{name}:{number}: {key} is enabled; '
                                'the security page is no longer na, re-audit it')
    for patch in series_names(repo):
        if SECURITY_PATCH.search(patch):
            problems.append(f'patches/xnu-12377/series: {patch} brings a trust-cache/AMFI/'
                            'AppSync change; the security page is no longer na, re-audit it')
    return problems


def baseband_problems(repo: Path, board: dict) -> list[str]:
    problems: list[str] = []
    selected = list(board.get('components', {}).get('include', []))
    override = (board.get('os_overrides', {}).get('ios-27.0.1-24A446', {})
                .get('components', {}).get('include', []))
    for label, names in (('board.toml [components]', selected),
                         ('board.toml ios-27.0.1-24A446 components', override)):
        for name in names:
            if 'QcomBaseband' in name or 'AppleBaseband' in name:
                problems.append(f'{label}: {name} is selected; '
                                'the qcom-baseband page is no longer na, re-audit it')
    for name, number, line in config_lines(repo):
        if re.match(r'^CONFIG_[A-Z0-9_]*=', line) and BASEBAND_CONFIG.search(line.split('=', 1)[0]):
            problems.append(f'configs/{name}:{number}: {line}; '
                            'the qcom-baseband page is no longer na, re-audit it')
    for patch in series_names(repo):
        if BASEBAND_PATCH.search(patch):
            problems.append(f'patches/xnu-12377/series: {patch} brings a baseband change; '
                            'the qcom-baseband page is no longer na, re-audit it')
    return problems


def check(repo: Path) -> list[str]:
    repo = Path(repo)
    try:
        board = load_board(repo)
    except Exception as error:
        return [f'{repo / "board.toml"}: {type(error).__name__}: {error}']
    return security_problems(repo, board) + baseband_problems(repo, board)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='re-check the security/baseband na premises')
    parser.add_argument('--repo', type=Path, default=REPO, help='repository root')
    parser.add_argument('--json', action='store_true', help='machine-readable result')
    options = parser.parse_args(argv)
    problems = check(options.repo)
    if options.json:
        print(json.dumps({'repo': str(options.repo), 'problems': problems,
                          'ok': not problems}, ensure_ascii=False, indent=2))
    else:
        for problem in problems:
            print(f'FAIL {problem}')
        if not problems:
            print('official-scope: OK (security trust cache/AMFI/AppSync are off; '
                  'no QcomBaseband component is selected)')
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
