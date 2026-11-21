#!/usr/bin/env python3
"""铁则 17 门禁的自测：每一条拒绝方向都要真的能拒绝。

2026-11-21 的教训：一条只会说 OK 的门禁等于没有门禁。这里逐条造出「应该失败」的账本，
断言它确实失败，并且失败原因指向正确的那一行。
"""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE.parent / 'check-official-steps.py'

spec = importlib.util.spec_from_file_location('official_steps', MODULE_PATH)
MODULE = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(MODULE)

PAGE = '# P\n\n## Section  {#good}\n\nunixnu fetch\n'
SCRIPT = 'python3 ./unixnu fetch --device "$ROOT"\n'

ROWS = {
    'id': 'fetch',
    'command': 'unixnu fetch',
    'page': 'page.md',
    'anchor': 'good',
    'what': 'a description that is long enough to pass',
    'evidence': 'docs/engineering/IOS27.md',
}


def ledger_text(**overrides) -> str:
    row = dict(ROWS)
    row.update(overrides)
    body = '\n'.join(f'{k} = "{v}"' for k, v in row.items() if v is not None)
    return 'schema_version = 1\n\n[[step]]\n' + body + '\n'


class Tests:
    def __init__(self) -> None:
        self.passed = 0
        self.failed: list[str] = []

    def check(self, name: str, condition: bool, message: str = '') -> None:
        if condition:
            self.passed += 1
        else:
            self.failed.append(f'{name}: {message}')

    def run(self, ledger: str, script: str = SCRIPT) -> list[str]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            docs = root / 'docs'
            docs.mkdir()
            (docs / 'page.md').write_text(PAGE, encoding='utf-8')
            ledger_path = root / 'steps.toml'
            ledger_path.write_text(ledger, encoding='utf-8')
            script_path = root / 'build.sh'
            script_path.write_text(script, encoding='utf-8')
            return MODULE.check(ledger_path, docs, script_path)


def main() -> int:
    tests = Tests()

    tests.check('pass.clean', tests.run(ledger_text()) == [], str(tests.run(ledger_text())))
    tests.check(
        'fail.missing_anchor',
        any('no {#good} anchor' in p or 'no {#other}' in p for p in tests.run(ledger_text(anchor='other'))),
        'a wrong anchor must fail',
    )
    tests.check(
        'fail.missing_page',
        any('is not in the documentation mirror' in p for p in tests.run(ledger_text(page='absent.md'))),
        'a page outside the mirror must fail',
    )
    tests.check(
        'fail.thin_what',
        any('shorter than' in p for p in tests.run(ledger_text(what='too short'))),
        'a vague description must fail',
    )
    tests.check(
        'fail.missing_evidence',
        any('does not exist' in p for p in tests.run(ledger_text(evidence='docs/nowhere.md'))),
        'an evidence path that does not exist must fail',
    )
    tests.check(
        'fail.empty_field',
        any('anchor is empty' in p for p in tests.run(ledger_text(anchor=''))),
        'an empty field must fail',
    )
    tests.check(
        'fail.command_not_run',
        any('never runs this command' in p
            for p in tests.run(ledger_text(command='unixnu bootimg'))),
        'a row for a command the script never runs must fail',
    )
    tests.check(
        'fail.uncovered_command',
        any('no [[step]] row covers it' in p
            for p in tests.run(ledger_text(), script=SCRIPT + 'python3 ./unixnu bootimg\n')),
        'a command in the script without a row must fail',
    )
    tests.check(
        'fail.empty_ledger',
        tests.run('schema_version = 1\n') == ['the ledger has no [[step]] rows'],
        'an empty ledger must fail',
    )

    print(f'{tests.passed}/{tests.passed + len(tests.failed)} checks passed')
    for failure in tests.failed:
        print(f'  FAIL {failure}')
    if tests.failed:
        return 1
    print('OK the official-steps gate refuses every way of citing nothing')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
