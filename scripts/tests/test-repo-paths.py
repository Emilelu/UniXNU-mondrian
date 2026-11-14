#!/usr/bin/env python3
"""Tests for scripts/check-repo-paths.py and the six scripts it guards (hard-39).

每条用例都在临时目录里造一棵树，不碰真实检出。

Run: python3 scripts/tests/test-repo-paths.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / 'scripts' / 'check-repo-paths.py'
GUARDED_PY = [
    ROOT / 'scripts/research-gate.py',
    ROOT / 'scripts/render-eight-step-table.py',
    ROOT / 'scripts/pick-upstream.py',
    ROOT / 'scripts/repair-resource-forks-k60.py',
]
GUARDED_SH = [
    ROOT / 'scripts/flash.sh',
    ROOT / 'scripts/repair-worktrees.sh',
]

# 路径片段拼出来：本文件在 scripts/ 下，不能被自己的规则判红。
HACKIOS = '/mnt/e/' + 'hackios/'
DEVICE = HACKIOS + 'UniXNU-mondrian'
SIBLING = HACKIOS + 'UniXNU'

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


def run(args, cwd=None, env=None):
    return subprocess.run(
        [str(arg) for arg in args],
        cwd=str(cwd) if cwd else None,
        capture_output=True, text=True, check=False,
        env=env if env is not None else clean_env(),
    )


def write_source(repo, name, text):
    path = repo / 'scripts' / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


IMPORT_DRIVER = '''import importlib.util
import sys

spec = importlib.util.spec_from_file_location('k60_script', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(module.REPO)
'''


def imported_root(script, cwd, env):
    driver = Path(cwd) / '_probe.py'
    driver.write_text(IMPORT_DRIVER, encoding='utf-8')
    result = run([sys.executable, driver, script], cwd=cwd, env=env)
    lines = result.stdout.strip().splitlines()
    return result, (lines[-1] if lines else '')


def test_env_override(tmp):
    repo = tmp / 'override'
    (repo / 'scripts').mkdir(parents=True)
    for source in GUARDED_PY[:3]:
        copied = repo / 'scripts' / source.name
        shutil.copy2(source, copied)
        result, root = imported_root(copied, tmp, clean_env(K60_REPO=str(repo)))
        check(result.returncode == 0 and Path(root).resolve() == repo.resolve(),
              'K60_REPO overrides the root: %s' % source.name,
              (result.stderr or result.stdout)[-300:])


def test_fallback(tmp):
    repo = tmp / 'fallback'
    (repo / 'scripts').mkdir(parents=True)
    for source in GUARDED_PY[:3]:
        copied = repo / 'scripts' / source.name
        shutil.copy2(source, copied)
        result, root = imported_root(copied, tmp, clean_env())
        check(result.returncode == 0 and Path(root).resolve() == repo.resolve(),
              'without K60_REPO the root is the script checkout: %s' % source.name,
              (result.stderr or result.stdout)[-300:])


def test_shell_fallback(tmp):
    repo = tmp / 'shell-fallback'
    (repo / 'scripts').mkdir(parents=True)
    copied = repo / 'scripts' / 'repair-worktrees.sh'
    shutil.copy2(GUARDED_SH[1], copied)
    result = run(['bash', copied], cwd=tmp, env=clean_env())
    out = result.stdout + result.stderr
    check(result.returncode == 0 and str(repo.resolve()) in out,
          'repair-worktrees.sh derives its root from its own path', out[-300:])


def test_shell_override(tmp):
    repo = tmp / 'shell-override'
    (repo / 'scripts').mkdir(parents=True)
    other = tmp / 'shell-target'
    other.mkdir(parents=True, exist_ok=True)
    copied = repo / 'scripts' / 'repair-worktrees.sh'
    shutil.copy2(GUARDED_SH[1], copied)
    result = run(['bash', copied], cwd=tmp, env=clean_env(K60_REPO=str(other)))
    out = result.stdout + result.stderr
    check(result.returncode == 0 and str(other.resolve()) in out,
          'repair-worktrees.sh honours K60_REPO', out[-300:])


APFS_STUB = '''print('APFS_TOOLS=' + __file__)
raise SystemExit(0)
'''


def apfs_repo(tmp, name):
    repo = tmp / name
    (repo / 'scripts').mkdir(parents=True)
    stub = repo / 'tools' / 'apfs' / 'apfs.py'
    stub.parent.mkdir(parents=True)
    stub.write_text(APFS_STUB, encoding='utf-8')
    copied = repo / 'scripts' / GUARDED_PY[3].name
    shutil.copy2(GUARDED_PY[3], copied)
    return repo, copied, stub


def test_resource_env(tmp):
    repo, copied, stub = apfs_repo(tmp, 'resource-env')
    result = run([sys.executable, copied], cwd=tmp, env=clean_env(K60_REPO=str(repo)))
    out = result.stdout + result.stderr
    check(result.returncode == 0 and str(stub.resolve()) in out,
          'repair-resource-forks-k60.py imports apfs from K60_REPO', out[-300:])


def test_resource_fallback(tmp):
    repo, copied, stub = apfs_repo(tmp, 'resource-fallback')
    result = run([sys.executable, copied], cwd=tmp, env=clean_env())
    out = result.stdout + result.stderr
    check(result.returncode == 0 and str(stub.resolve()) in out,
          'repair-resource-forks-k60.py falls back to its own checkout', out[-300:])


def test_rejects_hardcode(tmp):
    repo = tmp / 'bad'
    write_source(repo, 'bad.py', 'REPO = %r' % DEVICE + chr(10))
    result = run([sys.executable, CHECKER, '--repo', repo], cwd=tmp, env=clean_env())
    out = result.stdout + result.stderr
    check(result.returncode == 1 and 'ERROR' in out and 'bad.py:1' in out,
          'a hardcoded checkout path is an error', out[-400:])


def test_allows_prose(tmp):
    repo = tmp / 'prose'
    body = ('"""这里以前写死过 %s，在 worktree 里跑就写错树。"""' % DEVICE + chr(10)
            + '# %s 是主检出，不能写死' % DEVICE + chr(10)
            + 'REPO = None' + chr(10))
    write_source(repo, 'doc.py', body)
    result = run([sys.executable, CHECKER, '--repo', repo], cwd=tmp, env=clean_env())
    out = result.stdout + result.stderr
    check(result.returncode == 0 and '0 error(s)' in out,
          'docstrings and comments may mention the path', out[-400:])


def test_sibling_warning(tmp):
    repo = tmp / 'sibling'
    write_source(repo, 'sib.py', 'FW = %r' % SIBLING + chr(10))
    lenient = run([sys.executable, CHECKER, '--repo', repo], cwd=tmp, env=clean_env())
    strict = run([sys.executable, CHECKER, '--repo', repo, '--strict'], cwd=tmp, env=clean_env())
    check(lenient.returncode == 0 and '1 warning(s)' in lenient.stdout,
          'a sibling checkout path is only a warning', lenient.stdout[-300:])
    check(strict.returncode == 1,
          '--strict turns the sibling warning into a failure', strict.stdout[-300:])


def test_three_worktrees(tmp):
    repo = tmp / 'wt-main'
    (repo / 'scripts').mkdir(parents=True)
    shutil.copy2(CHECKER, repo / 'scripts' / 'check-repo-paths.py')
    probe = ('import os' + chr(10) + 'from pathlib import Path' + chr(10)
             + "REPO = Path(os.environ.get('K60_REPO') or Path(__file__).resolve().parents[1])"
             + chr(10))
    write_source(repo, 'probe.py', probe)
    init = run(['git', '-C', repo, 'init', '-q'])
    run(['git', '-C', repo, 'add', '-A'])
    commit = run(['git', '-C', repo, '-c', 'user.name=t', '-c', 'user.email=t@example.com',
                  'commit', '-q', '-m', 'init'])
    if init.returncode != 0 or commit.returncode != 0:
        check(False, 'three worktrees: git setup',
              (init.stdout + init.stderr + commit.stdout + commit.stderr)[-300:])
        return
    results = []
    for index in (1, 2, 3):
        worktree = tmp / ('wt-%d' % index)
        added = run(['git', '-C', repo, 'worktree', 'add', '-q',
                     '-b', 'wt-%d' % index, worktree])
        if added.returncode != 0:
            check(False, 'three worktrees: git worktree add', added.stderr[-300:])
            return
        result = run([sys.executable, worktree / 'scripts' / 'check-repo-paths.py'],
                     cwd=worktree, env=clean_env())
        results.append((result.returncode, str(worktree.resolve()) in result.stdout))
    check(all(code == 0 for code, _ in results),
          'the checker is green in each of three worktrees', str(results))
    check(all(seen for _, seen in results),
          'each worktree run reports its own root', str(results))


def test_canonical_line():
    canonical_py = "REPO = Path(os.environ.get('K60_REPO') or Path(__file__).resolve().parents[1])"
    for source in GUARDED_PY:
        lines = [row for row in source.read_text(encoding='utf-8').splitlines()
                 if row.startswith('REPO = ')]
        check(len(lines) == 1 and lines[0] == canonical_py,
              'canonical REPO line: %s' % source.name, str(lines[:2]))
    for source in GUARDED_SH:
        lines = [row for row in source.read_text(encoding='utf-8').splitlines()
                 if row.startswith('REPO=')]
        ok = (len(lines) == 1 and 'K60_REPO:-' in lines[0]
              and 'BASH_SOURCE' in lines[0] and 'dirname' in lines[0])
        check(ok, 'canonical REPO line: %s' % source.name, str(lines[:2]))


def test_real_repo():
    result = run([sys.executable, CHECKER], cwd=ROOT, env=clean_env())
    out = (result.stdout + result.stderr).strip()
    check(result.returncode == 0 and '0 error(s)' in out,
          'the real checkout is green', out[-400:])


def main():
    tmp = Path(tempfile.mkdtemp(prefix='k60-repo-paths-'))
    try:
        test_env_override(tmp)
        test_fallback(tmp)
        test_shell_fallback(tmp)
        test_shell_override(tmp)
        test_resource_env(tmp)
        test_resource_fallback(tmp)
        test_rejects_hardcode(tmp)
        test_allows_prose(tmp)
        test_sibling_warning(tmp)
        test_three_worktrees(tmp)
        test_canonical_line()
        test_real_repo()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print()
    if FAILURES:
        print('TESTS FAILED: %d case(s), %d failure(s)' % (CASES, FAILURES))
        return 1
    print('TESTS OK %d cases' % CASES)
    return 0


if __name__ == '__main__':
    sys.exit(main())
