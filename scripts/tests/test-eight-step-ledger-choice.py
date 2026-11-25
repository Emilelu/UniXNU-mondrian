#!/usr/bin/env python3
"""Tests for the eight-step gate's ledger choice (P-302).

The gate used to read `docs/research/EIGHT-STEPS.toml` no matter what the tree
was, so on an iOS 27 tree it judged 18 references to 16-series files and refused
every flight — including a firmware-only diagnostic that never enters XNU. The
cases below pin the three properties that fix needs:

  1. the ledger follows `board.toml`'s `os_profile` (the same key that picks the
     defconfig, so the two cannot disagree);
  2. the 27 ledger's list-valued `evidence` is accepted (16 uses a string);
  3. `K60_EIGHT_STEP_LEDGER` can point at a file, which is how a test or a lane
     exercises a ledger without editing board.toml.
"""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOL = os.path.join(ROOT, 'scripts', 'eight-step-gate.py')

CASES = []


def check(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


def load_gate():
    spec = importlib.util.spec_from_file_location('eight_step_gate', TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def temp_repo(profile, ledger_name, ledger_body, extra=None):
    """Build the smallest tree the gate can judge: board.toml + one ledger."""
    d = tempfile.mkdtemp(prefix='k60-eightstep-')
    with open(os.path.join(d, 'board.toml'), 'w', encoding='utf-8') as f:
        f.write('[board]\nos_profile = "%s"\n' % profile)
    os.makedirs(os.path.join(d, 'docs', 'research'), exist_ok=True)
    with open(os.path.join(d, 'docs', 'research', ledger_name), 'w', encoding='utf-8') as f:
        f.write(ledger_body)
    for name, body in (extra or {}).items():
        path = os.path.join(d, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(body)
    return d


EVIDENCE_FILE = 'K60Probe.c'   # a file the evidence can cite as K60Probe.c:1


def ledger_with_list_evidence():
    return '''
[hardware.probe]
status = "active"

[hardware.probe.steps."1"]
done = true
reference = "K60Probe.c:1"

[hardware.probe.steps."2"]
done = true
evidence = ["K60Probe.c:1"]
'''


def ledger_with_string_evidence():
    return '''
[hardware.probe]
status = "active"

[hardware.probe.steps."1"]
done = true
reference = "K60Probe.c:1"
evidence = "K60Probe.c:1"
'''


@check('choose.27_profile_picks_the_27_ledger')
def _(gate):
    path, why = gate.choose_ledger('ios-27.0.1-24A446', '/repo')
    assert path == '/repo/docs/research/EIGHT-STEPS-27.toml', path
    assert 'ios-27.0.1-24A446' in why, why


@check('choose.ipados_27_also_matches')
def _(gate):
    path, _ = gate.choose_ledger('ipados-27.0.1-24A446', '/repo')
    assert path.endswith('EIGHT-STEPS-27.toml'), path


@check('choose.16_profile_picks_the_16_ledger')
def _(gate):
    path, why = gate.choose_ledger('ipados-16.6.1-20G81', '/repo')
    assert path == '/repo/docs/research/EIGHT-STEPS.toml', path
    assert 'ipados-16.6.1-20G81' in why, why


@check('choose.unset_profile_picks_the_16_ledger')
def _(gate):
    path, why = gate.choose_ledger('', '/repo')
    assert path.endswith('EIGHT-STEPS.toml'), path
    assert 'unset' in why, why


@check('profile.reads_board_toml')
def _(gate):
    d = temp_repo('ios-27.0.1-24A446', 'EIGHT-STEPS-27.toml', '')
    try:
        assert gate.read_os_profile(d) == 'ios-27.0.1-24A446'
    finally:
        shutil.rmtree(d, ignore_errors=True)


@check('profile.missing_board_toml_is_empty_not_fatal')
def _(gate):
    d = tempfile.mkdtemp(prefix='k60-noboard-')
    try:
        assert gate.read_os_profile(d) == ''
    finally:
        shutil.rmtree(d, ignore_errors=True)


def run_validate(gate, repo, ledger_name, mode='build'):
    """Point the module at a temp tree and validate it."""
    gate.REPO = repo
    gate.DATA = os.path.join(repo, 'docs', 'research', ledger_name)
    gate.RULES_TEXT._cache = None
    return gate.validate(mode, verbose=False)


@check('validate.27_ledger_list_evidence_is_accepted')
def _(gate):
    d = temp_repo('ios-27.0.1-24A446', 'EIGHT-STEPS-27.toml', ledger_with_list_evidence(),
                  {EVIDENCE_FILE: 'int main(void) { return 0; }\n'})
    try:
        ok, problems = run_validate(gate, d, 'EIGHT-STEPS-27.toml')
        joined = ' '.join(problems)
        # The list must be joined, not treated as a missing value.
        assert 'no evidence' not in joined, joined
        assert '依据' not in joined, joined
    finally:
        shutil.rmtree(d, ignore_errors=True)


@check('validate.16_ledger_string_evidence_still_works')
def _(gate):
    d = temp_repo('ipados-16.6.1-20G81', 'EIGHT-STEPS.toml', ledger_with_string_evidence(),
                  {EVIDENCE_FILE: 'int main(void) { return 0; }\n'})
    try:
        ok, problems = run_validate(gate, d, 'EIGHT-STEPS.toml')
        joined = ' '.join(problems)
        assert 'no evidence' not in joined, joined
        assert '依据' not in joined, joined
    finally:
        shutil.rmtree(d, ignore_errors=True)


@check('validate.missing_ledger_names_the_choice')
def _(gate):
    d = temp_repo('ios-27.0.1-24A446', 'EIGHT-STEPS-27.toml', '')
    try:
        os.remove(os.path.join(d, 'docs', 'research', 'EIGHT-STEPS-27.toml'))
        ok, problems = run_validate(gate, d, 'EIGHT-STEPS-27.toml')
        joined = ' '.join(problems)
        assert not ok, joined
        assert 'P-302' in joined, joined
        assert 'EIGHT-STEPS-27.toml' in joined, joined
    finally:
        shutil.rmtree(d, ignore_errors=True)


@check('validate.27_ledger_skips_the_renderer')
def _(gate):
    """The 27 ledger has its own renderer; the 16 README check must not judge it."""
    d = temp_repo('ios-27.0.1-24A446', 'EIGHT-STEPS-27.toml', ledger_with_list_evidence(),
                  {EVIDENCE_FILE: 'int main(void) { return 0; }\n'})
    try:
        ok, problems = run_validate(gate, d, 'EIGHT-STEPS-27.toml')
        joined = ' '.join(problems)
        assert 'README 表格' not in joined, joined
    finally:
        shutil.rmtree(d, ignore_errors=True)


@check('cli.env_override_selects_the_file')
def _(gate):
    d = temp_repo('ios-27.0.1-24A446', 'EIGHT-STEPS-27.toml', ledger_with_list_evidence(),
                  {EVIDENCE_FILE: 'int main(void) { return 0; }\n'})
    try:
        env = dict(os.environ)
        env['K60_EIGHT_STEP_LEDGER'] = os.path.join(d, 'docs', 'research', 'EIGHT-STEPS-27.toml')
        env['K60_EIGHT_STEP_LEDGER_SOURCE'] = 'test'
        env.pop('K60_DEVICE_INPUT', None)
        env.pop('K60_OUT', None)
        out = subprocess.run([sys.executable, TOOL, '--build'], env=env,
                             capture_output=True, text=True, timeout=120)
        text = (out.stdout or '') + (out.stderr or '')
        assert '账本' in text, text[-400:]
        assert 'EIGHT-STEPS-27.toml' in text, text[-400:]
        assert 'K60_EIGHT_STEP_LEDGER' not in text.split('账本')[1][:80], text[-400:]
    finally:
        shutil.rmtree(d, ignore_errors=True)


@check('anchor.windows_drive_form_maps_to_mnt')
def _(gate):
    """E:/... is how the ledgers are written; it must become /mnt/e/... on Linux."""
    candidates = [str(c) for c in gate._anchor_candidates('E:/iOS Port/Work/reports/x.dtb')]
    assert '/mnt/e/iOS Port/Work/reports/x.dtb' in candidates, candidates
    assert 'E:/iOS Port/Work/reports/x.dtb' in candidates, candidates


@check('anchor.leading_slash_keeps_the_base')
def _(gate):
    """Path('/root') / '/abs' is '/abs' — the base was being dropped, so every
    stripped-drive anchor pointed at the filesystem root."""
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, 'k60-work'))
        f = os.path.join(d, 'k60-work', 'x.txt')
        open(f, 'w').write('a\n')
        gate.EVIDENCE_ROOTS = [d]
        try:
            assert gate.resolve_file_line('/k60-work/x.txt:1') is None
        finally:
            gate.EVIDENCE_ROOTS = ['/mnt/e/iOS Port/Work/evidence', '/mnt/e/iOS Port/Work/reports',
                                   '/mnt/e/iOS Port/Work', '/mnt/e/iOS Port/Sources']


@check('anchor.repo_relative_still_works')
def _(gate):
    assert gate.resolve_file_line('scripts/eight-step-gate.py:1') is None


@check('anchor.missing_file_is_still_an_error')
def _(gate):
    assert 'no such file' in str(gate.resolve_file_line('nope/absent.c:1'))


def main():
    gate = load_gate()
    failed = 0
    for name, fn in CASES:
        try:
            fn(gate)
            print('ok   %s' % name)
        except AssertionError as e:
            failed += 1
            print('FAIL %s: %s' % (name, e))
        except Exception as e:
            failed += 1
            print('FAIL %s: %s: %s' % (name, type(e).__name__, e))
    print()
    if failed:
        print('FAILED %d of %d' % (failed, len(CASES)))
        return 1
    print('OK %d cases: the ledger follows os_profile, both evidence shapes pass, and drive-letter anchors resolve'
          % len(CASES))
    return 0


if __name__ == '__main__':
    sys.exit(main())
