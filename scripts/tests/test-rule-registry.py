#!/usr/bin/env python3
"""Tests for scripts/check-rule-registry.py.

Every case builds a throwaway tree in a temporary directory and points the
checker at it with K60_REPO, so the real registry is never touched.

Run: python3 scripts/tests/test-rule-registry.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / 'scripts' / 'check-rule-registry.py'

CASES = 0
FAILURES = 0


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


def run(repo, **extra):
    return subprocess.run(
        [sys.executable, str(CHECKER)],
        capture_output=True, text=True, check=False,
        env=clean_env(K60_REPO=str(repo), **extra),
    )


def make_repo(tmp, rules_text, hard_text=None):
    repo = tmp / 'repo'
    (repo / 'docs' / 'engineering').mkdir(parents=True, exist_ok=True)
    (repo / 'docs' / 'engineering' / 'RULES.toml').write_text(
        rules_text, encoding='utf-8')
    if hard_text is not None:
        (repo / 'docs' / 'engineering' / 'HARD-RULES.md').write_text(
            hard_text, encoding='utf-8')
    return repo


RULES_HEAD = '''schema = 1
grandfather_through = 151

[[rule]]
id = "iron-1"
kind = "iron"
statement = "No /tmp as durable storage"
waiver = "covered by the eight-step evidence gate"
'''


def case_unique_ids_pass(tmp):
    repo = make_repo(tmp, RULES_HEAD + '''
[[rule]]
id = "hard-34"
kind = "hard"
source = "docs/engineering/HARD-RULES.md:★34"
statement = "protocol and model must be measured"
waiver = "covered by step 1"
''', hard_text='## ★34（HR-69）protocol and model\n')
    result = run(repo)
    check(result.returncode == 0, 'a registry with unique ids passes', result.stdout + result.stderr)
    check('unique id' in result.stdout, 'it reports the unique id count', result.stdout)


def case_duplicate_id_fails(tmp):
    repo = make_repo(tmp, RULES_HEAD + '''
[[rule]]
id = "hard-34"
kind = "hard"
source = "docs/engineering/HARD-RULES.md:★34"
statement = "protocol and model must be measured"
waiver = "covered by step 1"

[[rule]]
id = "hard-34"
kind = "hard"
statement = "line endings must not flip"
check = "python3 scripts/check-line-endings.py"
''', hard_text='## ★34（HR-69）protocol and model\n')
    result = run(repo)
    check(result.returncode == 1, 'a duplicate id fails', result.stdout)
    check('duplicate rule id' in result.stdout, 'it names the duplicate', result.stdout)
    check('hard-34' in result.stdout, 'the message names hard-34', result.stdout)


def case_pitfall_source_mismatch_fails(tmp):
    repo = make_repo(tmp, RULES_HEAD + '''
[[rule]]
id = "hard-35"
kind = "hard"
source = "docs/engineering/PITFALLS.md:P-186"
statement = "line endings must not flip"
check = "python3 scripts/check-line-endings.py"
''', hard_text='## ★34（HR-69）protocol and model\n')
    result = run(repo)
    check(result.returncode == 1, 'a pitfall source under a hard id fails', result.stdout)
    check('names P-186' in result.stdout, 'it explains the mismatch', result.stdout)


def case_hard_id_without_heading_fails(tmp):
    repo = make_repo(tmp, RULES_HEAD + '''
[[rule]]
id = "hard-40"
kind = "hard"
source = "docs/engineering/HARD-RULES.md:★40"
statement = "a rule whose heading does not exist"
waiver = "none yet"
''', hard_text='## ★34（HR-69）protocol and model\n')
    result = run(repo)
    check(result.returncode == 1, 'a hard id with no matching heading fails', result.stdout)
    check('no ★40' in result.stdout, 'it names the missing heading', result.stdout)


def case_missing_registry_is_skipped(tmp):
    repo = tmp / 'empty'
    repo.mkdir(parents=True)
    result = run(repo)
    check(result.returncode == 0, 'a tree without RULES.toml is skipped, not failed',
          result.stdout + result.stderr)
    check('skip' in result.stdout, 'it says it skipped', result.stdout)


def case_real_registry_passes():
    result = subprocess.run(
        [sys.executable, str(CHECKER)],
        capture_output=True, text=True, check=False,
        env=clean_env(K60_REPO=str(ROOT)),
    )
    check(result.returncode == 0, 'the real registry passes', result.stdout + result.stderr)


def main():
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        case_unique_ids_pass(tmp / 'a')
        case_duplicate_id_fails(tmp / 'b')
        case_pitfall_source_mismatch_fails(tmp / 'c')
        case_hard_id_without_heading_fails(tmp / 'd')
        case_missing_registry_is_skipped(tmp / 'e')
    case_real_registry_passes()

    print()
    if FAILURES:
        print('TESTS FAILED %d case(s) (%d failure(s))' % (CASES, FAILURES))
        return 1
    print('TESTS OK %d case(s) (0 failure(s))' % CASES)
    return 0


if __name__ == '__main__':
    sys.exit(main())
