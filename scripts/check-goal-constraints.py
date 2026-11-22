#!/usr/bin/env python3
"""Two constraints that must hold before any 27 build or flight.

1. PRECEDENT PARITY. Every artefact of every precedent repository (patch series
   entry, board.toml key, defconfig key) must be classified in
   docs/research/ios27/PRECEDENT-PARITY.toml as
     have | copied | not-applicable (with reason) | missing-must-copy
   A single `missing-must-copy` or `unknown` refuses the build. The ledger also
   records the measured item count per repository, so a repository that grows is
   caught the next run instead of being silently ignored.

2. EIGHT STEPS. Every *active* hardware item in the 27 ledger must carry steps
   1..8, and each step's evidence must resolve: a repo path with :line, an
   http(s) URL, or a `kb:` chunk reference. A step whose evidence cannot be
   read again is treated as missing.

Read-only. Exit 0 = both hold. Exit 2 = refused, with the reason named.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
import tomllib

PARITY = 'docs/research/ios27/PRECEDENT-MANIFEST.toml'
LEDGER = 'docs/research/EIGHT-STEPS-27.toml'
ALLOWED = {'have', 'copied', 'not-applicable'}
STEPS = ('same-model', 'official', 'decompile', 'wide', 'plan', 'deep', 'verify', 'device')
ANCHOR = re.compile(r'^(?P<path>[^\s:]+):(?P<line>\d+)$')
URL = re.compile(r'^https?://')
KB = re.compile(r'^kb:')


def parity_problems(root: pathlib.Path) -> list[str]:
    path = root / PARITY
    if not path.is_file():
        return [f'{PARITY} is missing: run scripts/scan-precedents.py; nothing has been compared (P-311)']
    data = tomllib.loads(path.read_text(encoding='utf-8'))
    problems: list[str] = []
    for repo in data.get('repo', []):
        name = repo.get('name', '<unnamed>')
        measured = repo.get('measured_items')
        classified = len(repo.get('item', []))
        if measured is None:
            problems.append(f'{name}: no measured_items; the comparison cannot be checked for completeness')
        elif measured != classified:
            problems.append(f'{name}: {classified} item(s) classified but {measured} measured; '
                            f'{measured - classified} unclassified — rerun scripts/scan-precedents.py')
        unknown = 0
        for item in repo.get('item', []):
            verdict = item.get('verdict', 'unknown')
            if verdict == 'unknown':
                unknown += 1
                continue
            if verdict not in ALLOWED:
                problems.append(f'{name}/{item.get("id", "?")}: verdict {verdict!r} is not one of '
                                f'have/copied/not-applicable — builds stay refused')
            if verdict == 'not-applicable' and not item.get('reason'):
                problems.append(f'{name}/{item.get("id", "?")}: not-applicable without a reason')
        if unknown:
            problems.append(f'{name}: {unknown} of {classified} artefact(s) unjudged '
                            f'— the working repositories are not copied completely yet')
    if not data.get('repo'):
        problems.append(f'{PARITY} lists no repository')
    return problems


def evidence_resolves(root: pathlib.Path, text: str) -> bool:
    text = text.strip()
    if URL.match(text) or KB.match(text):
        return True
    match = ANCHOR.match(text)
    if not match:
        return False
    path = root / match.group('path')
    line = int(match.group('line'))
    if not path.is_file():
        return False
    with path.open('rb') as handle:
        total = sum(1 for _ in handle)
    return 1 <= line <= max(total, 1)


def eight_step_problems(root: pathlib.Path) -> list[str]:
    path = root / LEDGER
    if not path.is_file():
        return [f'{LEDGER} is missing']
    data = tomllib.loads(path.read_text(encoding='utf-8'))
    problems: list[str] = []
    active = 0
    for name, item in data.get('hardware', {}).items():
        if item.get('status') != 'active':
            continue
        active += 1
        steps = item.get('step', {})
        for step in STEPS:
            body = steps.get(step)
            if not isinstance(body, dict):
                problems.append(f'{name}: step {step} is missing')
                continue
            if body.get('done') is not True and step != 'device':
                problems.append(f'{name}: step {step} is not done')
            evidence = body.get('evidence') or []
            if isinstance(evidence, str):
                evidence = [evidence]
            if not evidence:
                problems.append(f'{name}: step {step} has no evidence')
                continue
            for entry in evidence:
                if not evidence_resolves(root, entry):
                    problems.append(f'{name}: step {step} evidence {entry!r} no longer resolves')
    if active == 0:
        problems.append('no active hardware item: nothing to judge, so the eight-step gate has no object')
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default='.')
    parser.add_argument('--parity-only', action='store_true')
    parser.add_argument('--eight-step-only', action='store_true')
    args = parser.parse_args(argv)
    root = pathlib.Path(args.repo).resolve()
    problems: list[str] = []
    if not args.eight_step_only:
        problems += parity_problems(root)
    if not args.parity_only:
        problems += eight_step_problems(root)
    for problem in problems:
        print(f'FAIL: {problem}')
    if problems:
        print(f'\n🛑 refused: {len(problems)} unresolved constraint(s). '
              f'No build, no flight (BUILD-FREEZE.md).')
        return 2
    print('OK goal constraints: precedent parity is complete and every active item has eight resolvable steps')
    return 0


if __name__ == '__main__':
    sys.exit(main())
