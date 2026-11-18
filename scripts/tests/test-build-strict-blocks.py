#!/usr/bin/env python3
"""Tests for scripts/check-build-strict-blocks.py (P-226).

Every case builds a throwaway tree and points the checker at it with K60_REPO,
so the real build-strict.sh is never touched.  Each variant is produced by
deleting one sentinel line, so exactly one block disappears and the gate must go
red -- that is the reverse verification the rule asks for.

Run: python3 scripts/tests/test-build-strict-blocks.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / 'scripts' / 'check-build-strict-blocks.py'

CASES = 0
FAILURES = 0

GOOD = '''#!/bin/bash
# --- gate-table:BEGIN ---
python3 "@@D@@REPO/scripts/check-build-env.py" || die "build environment is incomplete (P-185)"
# --- gate-table:END ---

board_dir() {
    if [ -n "@@D@@{K60_BOARD_DIR:-}" ]; then
        [ -f "@@D@@K60_BOARD_DIR/.config" ] || die "K60_BOARD_DIR=@@D@@K60_BOARD_DIR has no .config"
        echo "@@D@@K60_BOARD_DIR"
        return 0
    fi
    local all=() full=() d
    for d in "@@D@@OUT"/mondrian/ipados-*/*/; do
        d=@@D@@{d%/}
        [ -f "@@D@@d/.config" ] || continue
        all+=("@@D@@d")
        if grep -q "^CONFIG_XNU_GPU_ADDON=\\|^CONFIG_XNU_K60_PHYSICAL_BATTERY=" "@@D@@d/.config"; then
            full+=("@@D@@d")
        fi
    done
    echo "@@D@@d"
}

M=@@D@@(board_dir)

freeze() {
    ( cd "@@D@@REPO" && find board.toml dts patches/xnu scripts -type f \\
        ! -path '*/__pycache__/*' ! -name '*.pyc' -print0 \\
        | sort -z | xargs -0 sha256sum )
}

[ -f "@@D@@M/.config" ] || die "no @@D@@M/.config; generate it first"

if [ -n "@@D@@WIFI_ARCHIVE" ]; then
    "@@D@@NM" "@@D@@KERNEL" | grep -q ' _pong_wifi_start_optional@@D@@"' || die "P-190"
fi
'''.replace('@@D@@', '$')


def check(condition, label, detail=''):
    global CASES, FAILURES
    CASES += 1
    if condition:
        print('ok   %s' % label)
    else:
        FAILURES += 1
        print('FAIL %s%s' % (label, (': ' + detail) if detail else ''))


def clean_env(**extra):
    env = {key: value for key, value in os.environ.items() if not key.startswith('K60_')}
    env.update(extra)
    return env


def run(repo):
    return subprocess.run(
        [sys.executable, str(CHECKER)],
        capture_output=True, text=True, check=False,
        env=clean_env(K60_REPO=str(repo)),
    )


def make_repo(tmp, text):
    repo = tmp / 'repo'
    (repo / 'scripts').mkdir(parents=True, exist_ok=True)
    (repo / 'scripts' / 'build-strict.sh').write_text(text, encoding='utf-8')
    return repo


def drop(text, needle):
    """Remove every line that contains needle; assert it was there."""
    lines = text.split('\n')
    kept = [line for line in lines if needle not in line]
    assert len(kept) != len(lines), 'sentinel %r not found' % needle
    return '\n'.join(kept)


def case_complete_tree_passes(tmp):
    result = run(make_repo(tmp, GOOD))
    check(result.returncode == 0, 'a complete build-strict.sh passes', result.stdout + result.stderr)


def case_missing_board_dir_fails(tmp):
    text = GOOD.replace('board_dir() {', 'board_dir_gone() {')
    result = run(make_repo(tmp, text))
    check(result.returncode == 1 and 'board_dir()' in result.stdout,
          'a missing board_dir() is red', result.stdout)


def case_board_dir_by_age_only_fails(tmp):
    text = drop(GOOD, 'CONFIG_XNU_GPU_ADDON=')
    result = run(make_repo(tmp, text))
    check(result.returncode == 1 and 'P-225' in result.stdout,
          'board_dir() without the key ranking is red', result.stdout)


def case_board_dir_silent_override_fails(tmp):
    text = drop(GOOD, 'has no .config')
    result = run(make_repo(tmp, text))
    check(result.returncode == 1 and 'K60_BOARD_DIR' in result.stdout,
          'board_dir() that ignores a broken K60_BOARD_DIR is red', result.stdout)


def case_pycache_prune_dropped_fails(tmp):
    text = drop(GOOD, '__pycache__')
    result = run(make_repo(tmp, text))
    check(result.returncode == 1 and 'P-224' in result.stdout,
          'freeze() without the bytecode prune is red', result.stdout)


def case_config_guard_dropped_fails(tmp):
    text = drop(GOOD, 'generate it first')
    result = run(make_repo(tmp, text))
    check(result.returncode == 1 and 'P-202' in result.stdout,
          'a missing .config guard is red', result.stdout)


def case_gate_marker_dropped_fails(tmp):
    text = drop(GOOD, 'gate-table:END')
    result = run(make_repo(tmp, text))
    check(result.returncode == 1 and 'P-205' in result.stdout,
          'a missing gate-table marker is red', result.stdout)


def case_wifi_archive_without_proof_fails(tmp):
    text = drop(GOOD, '_pong_wifi_start_optional')
    result = run(make_repo(tmp, text))
    check(result.returncode == 1 and 'P-190' in result.stdout,
          'a wifi archive without the kernel proof is red', result.stdout)


def case_absent_file_skips(tmp):
    repo = tmp / 'repo'
    (repo / 'scripts').mkdir(parents=True, exist_ok=True)
    result = run(repo)
    check(result.returncode == 0 and 'skip' in result.stdout,
          'an absent build-strict.sh skips instead of failing', result.stdout)


CASES_LIST = [
    case_complete_tree_passes,
    case_missing_board_dir_fails,
    case_board_dir_by_age_only_fails,
    case_board_dir_silent_override_fails,
    case_pycache_prune_dropped_fails,
    case_config_guard_dropped_fails,
    case_gate_marker_dropped_fails,
    case_wifi_archive_without_proof_fails,
    case_absent_file_skips,
]


def main() -> int:
    for case in CASES_LIST:
        with tempfile.TemporaryDirectory() as name:
            case(Path(name))
    print()
    print('CASES %d  FAILURES %d' % (CASES, FAILURES))
    if FAILURES:
        print('TESTS FAILED')
        return 1
    print('TESTS OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
