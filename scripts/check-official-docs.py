"""Check that every official documentation page is accounted for.

The zh documentation mirror under E:/hackios/UniXNU/docs/zh is the contract we
port against. Reading it once is not compliance, so docs/engineering/
OFFICIAL-REQUIREMENTS.toml carries one entry per page:

  mapped   - a named gate enforces the page (and that gate must exist)
  unmapped - nobody has checked this page yet; counted as debt, not as done
  na       - the page does not constrain this board, with `why`

This gate fails on: a page with no entry, an entry with no page, a stale sha256
(the page changed after we read it), a bad state, a mapped entry whose gate does
not exist in scripts/, a mapped entry without an assertion, and an na entry
without a why. Unmapped pages alone do not fail: the debt is printed.
"""
import argparse
import hashlib
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / 'docs/engineering/OFFICIAL-REQUIREMENTS.toml'
DEFAULT_DOCS = Path('/mnt/e/hackios/UniXNU/docs/zh')
STATES = {'mapped', 'unmapped', 'na'}
EXEMPT_DIRECTORIES = {'devices'}      # one page per device; not this board's contract


class Failure(Exception):
    pass


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pages(docs):
    if not docs.is_dir():
        raise Failure(f'no documentation mirror at {docs}')
    found = []
    for path in sorted(docs.rglob('*.md')):
        relative = path.relative_to(docs)
        if EXEMPT_DIRECTORIES & set(relative.parts):
            continue
        found.append(relative.as_posix())
    return found


def load(path):
    if not path.is_file():
        raise Failure(f'no requirement registry at {path}: silence is not compliance')
    document = tomllib.loads(path.read_text(encoding='utf-8'))
    entries = document.get('page')
    if not entries:
        raise Failure(f'{path} has no [[page]] entries')
    return entries


def gate_exists(name):
    target = name.split()[0]
    return any((ROOT / folder / target).is_file() for folder in ('scripts', 'scripts/tests'))


def check(docs, registry=REGISTRY):
    found = pages(docs)
    entries = load(registry)
    seen = {}
    problems = []
    debt = []
    for entry in entries:
        relative = entry.get('path')
        if not relative:
            problems.append('an entry has no path')
            continue
        if relative in seen:
            problems.append(f'{relative} appears twice')
            continue
        seen[relative] = entry
        state = entry.get('state')
        if state not in STATES:
            problems.append(f'{relative}: state {state!r} is not one of {sorted(STATES)}')
            continue
        page = docs / relative
        if not page.is_file():
            problems.append(f'{relative}: listed but not in the mirror')
            continue
        if digest(page) != entry.get('sha256'):
            problems.append(f'{relative}: the page changed since it was read; re-read it and update sha256')
        if state == 'mapped':
            name = entry.get('gate', '')
            if not name:
                problems.append(f'{relative}: mapped without a gate')
            elif not gate_exists(name):
                problems.append(f'{relative}: gate {name.split()[0]} is not in scripts/')
            if not entry.get('assertion'):
                problems.append(f'{relative}: mapped without an assertion to check')
        elif state == 'na' and not entry.get('why'):
            problems.append(f'{relative}: na without a why')
        elif state == 'unmapped':
            debt.append(relative)
    for relative in found:
        if relative not in seen:
            problems.append(f'{relative}: no entry in the registry')
    for relative in sorted(seen):
        if relative not in found:
            problems.append(f'{relative}: in the registry but not in the mirror')
    return {'pages': len(found), 'mapped': sum(1 for e in seen.values() if e.get('state') == 'mapped'),
            'na': sum(1 for e in seen.values() if e.get('state') == 'na'),
            'debt': debt, 'problems': problems}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--docs', type=Path, default=DEFAULT_DOCS, help='the zh documentation mirror')
    parser.add_argument('--registry', type=Path, default=REGISTRY)
    parser.add_argument('--list-debt', action='store_true', help='print every unmapped page')
    options = parser.parse_args()
    try:
        result = check(options.docs, options.registry)
    except Failure as error:
        print(f'FAIL: {error}')
        return 2
    for problem in result['problems']:
        print(f'FAIL: {problem}')
    if options.list_debt:
        for relative in result['debt']:
            print(f'debt: {relative}')
    print(f'documented pages {result["pages"]}, mapped {result["mapped"]}, na {result["na"]}, '
          f'unmapped {len(result["debt"])}')
    return 1 if result['problems'] else 0


if __name__ == '__main__':
    sys.exit(main())
