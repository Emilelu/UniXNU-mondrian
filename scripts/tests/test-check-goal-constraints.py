#!/usr/bin/env python3
"""Tests for check-goal-constraints.py.

Each case builds a throwaway tree; the checker is invoked as a module so the
test exercises the same code the build runs.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import textwrap

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / 'scripts/check-goal-constraints.py'

PARITY_OK = """\
[[repo]]
name = "asteroids"
measured_items = 1

  [[repo.item]]
  id = "zzzzz-video-console-physical-fb"
  verdict = "copied"
  where = "patches/xnu-12377/0552-k60-video-console-physical-fb.patch"
"""

LEDGER_OK = """\
[hardware.console]
status = "active"

  [hardware.console.step.same-model]
  done = true
  evidence = ["docs/example.md:1"]

  [hardware.console.step.official]
  done = true
  evidence = ["docs/example.md:1"]

  [hardware.console.step.decompile]
  done = true
  evidence = ["docs/example.md:1"]

  [hardware.console.step.wide]
  done = true
  evidence = ["https://example.com/page"]

  [hardware.console.step.plan]
  done = true
  evidence = ["kb:abc123"]

  [hardware.console.step.deep]
  done = true
  evidence = ["docs/example.md:1"]

  [hardware.console.step.verify]
  done = true
  evidence = ["docs/example.md:1"]

  [hardware.console.step.device]
  done = false
  evidence = ["docs/example.md:1"]
"""


def tree(parity: str | None = PARITY_OK, ledger: str | None = LEDGER_OK) -> pathlib.Path:
    root = pathlib.Path(tempfile.mkdtemp(prefix='goal-constraints-'))
    (root / 'docs/research/ios27').mkdir(parents=True)
    (root / 'docs/example.md').write_text('one\ntwo\n', encoding='utf-8')
    if parity is not None:
        (root / 'docs/research/ios27/PRECEDENT-PARITY.toml').write_text(parity, encoding='utf-8')
    if ledger is not None:
        (root / 'docs/research/EIGHT-STEPS-27.toml').write_text(ledger, encoding='utf-8')
    return root


def run(root: pathlib.Path) -> tuple[int, str]:
    result = subprocess.run([sys.executable, str(SCRIPT), '--repo', str(root)],
                            capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def main() -> int:
    failures = 0

    def check(name: str, condition: bool, detail: str = '') -> None:
        nonlocal failures
        print(('ok   ' if condition else 'FAIL ') + name + (f'  {detail}' if detail and not condition else ''))
        if not condition:
            failures += 1

    rc, out = run(tree())
    check('both hold', rc == 0, out)

    rc, out = run(tree(parity=None))
    check('missing parity file refuses', rc == 2 and 'PRECEDENT-PARITY.toml is missing' in out, out)

    unknown = PARITY_OK.replace('verdict = "copied"', 'verdict = "unknown"')
    rc, out = run(tree(parity=unknown))
    check('unknown verdict refuses', rc == 2 and 'builds stay refused' in out, out)

    short = PARITY_OK.replace('measured_items = 1', 'measured_items = 3')
    rc, out = run(tree(parity=short))
    check('unclassified items refuse', rc == 2 and '2 unclassified' in out, out)

    no_reason = PARITY_OK.replace('verdict = "copied"', 'verdict = "not-applicable"')
    rc, out = run(tree(parity=no_reason))
    check('not-applicable without reason refuses', rc == 2 and 'without a reason' in out, out)

    bad_line = LEDGER_OK.replace('docs/example.md:1', 'docs/example.md:99', 1)
    rc, out = run(tree(ledger=bad_line))
    check('evidence past end of file refuses', rc == 2 and 'no longer resolves' in out, out)

    missing_step = LEDGER_OK.replace('[hardware.console.step.verify]', '[hardware.console.step.verifyX]')
    rc, out = run(tree(ledger=missing_step))
    check('missing step refuses', rc == 2 and 'step verify is missing' in out, out)

    parked = LEDGER_OK.replace('status = "active"', 'status = "parked"')
    rc, out = run(tree(ledger=parked))
    check('no active item refuses', rc == 2 and 'no active hardware item' in out, out)

    print(f'\nTESTS OK {8 - failures}/8 cases' if not failures else f'\nTESTS FAILED {failures} case(s)')
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main())
