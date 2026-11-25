#!/usr/bin/env python3
"""Fail when a blocked problem has no reading of the reference sources behind it.

Iron rule 16. The rule is not "try to remember to read the references": it is that a
blocker which is still open must carry, in the repository, at least two readings of
registered reference sources that say what that source does about *this* problem and
what we did with it (copied it, adapted it, or rejected it with a reason).

Why a separate file rather than prose in a report: prose is written once and goes
stale, while a file with `path` and `line` breaks the moment the reference moves, and
that breakage is the reminder. Same shape as P-259/P-279: a claim that cannot be
re-resolved is not evidence.

Exit codes: 0 the readings are there and resolve, 1 a reading is missing or does not
resolve, 2 the question cannot be answered (no entries file, no sources file).
"""

import argparse
import sys
import tomllib
from pathlib import Path

VERDICTS = ('copied', 'adapted', 'rejected')
MIN_SOURCES = 2
MIN_WHAT = 30
MIN_WHY_NOT = 40


def load(path, what):
    if not path.is_file():
        return None
    try:
        return tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as error:
        print(f'FAIL: {what} at {path} is not valid TOML: {error}')
        return None


def open_blockers(document):
    return [blocker['id'] for blocker in document.get('blocker', [])
            if blocker.get('state') == 'open']


def sources_by_name(document):
    return {repo['name']: Path(repo['path'])
            for repo in document.get('repo', [])
            if repo.get('name') and repo.get('path')}


def reading_problems(entry, roots):
    problems = []
    name = entry.get('source', '')
    root = roots.get(name)
    if root is None:
        problems.append(f'{name or "(no source)"}: not a registered reference source')
        return problems
    relative = entry.get('path')
    if not relative:
        problems.append(f'{name}: no path')
        return problems
    path = root / relative
    if not path.is_file():
        problems.append(f'{name}: {relative} does not exist under {root}')
        return problems
    line = entry.get('line')
    if not isinstance(line, int) or line < 1:
        problems.append(f'{name}: {relative} has no positive line number')
        return problems
    total = len(path.read_text(errors='replace').splitlines())
    if line > total:
        problems.append(f'{name}: {relative}:{line} is past the end ({total} lines)')
    what = (entry.get('what') or '').strip()
    if len(what) < MIN_WHAT:
        problems.append(f'{name}: {relative}:{line} does not say what the source does '
                        f'({len(what)} chars, need {MIN_WHAT})')
    verdict = entry.get('verdict')
    if verdict not in VERDICTS:
        problems.append(f'{name}: {relative}:{line} has verdict {verdict!r}, '
                        f'expected one of {", ".join(VERDICTS)}')
    return problems


def check(blockers_path, entries_path, sources_path):
    sources = load(sources_path, 'the reference source list')
    if sources is None:
        return 2, [f'{sources_path} is missing; the gate cannot tell what a reference is (P-251)']
    entries = load(entries_path, 'the reference readings')
    if entries is None:
        return 2, [f'{entries_path} is missing; nothing has been read (P-279)']
    blockers = load(blockers_path, 'the flight blockers')
    if blockers is None:
        return 2, [f'{blockers_path} is missing']

    roots = sources_by_name(sources)
    by_id = {}
    for entry in entries.get('entry', []):
        by_id.setdefault(entry.get('id', ''), []).append(entry)

    problems = []
    for blocker in open_blockers(blockers):
        readings = by_id.get(blocker, [])
        if not readings:
            problems.append(f'{blocker}: no reference reading; this is the closed-door '
                            f'case iron-16 exists to stop')
            continue
        names = {entry.get('source') for entry in readings}
        if len(names) < MIN_SOURCES:
            problems.append(f'{blocker}: {len(names)} source(s), need {MIN_SOURCES} '
                            f'(one reference agreeing with itself is not a comparison)')
        for entry in readings:
            problems.extend(f'{blocker}: {problem}' for problem in reading_problems(entry, roots))

    unknown = sorted(set(by_id) - set(open_blockers(blockers)))
    for blocker in unknown:
        problems.append(f'{blocker}: readings recorded for a blocker that is not open '
                        f'(either reopen it or delete the readings)')
    return (1 if problems else 0), problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    here = Path(__file__).resolve().parents[1]
    parser.add_argument('--blockers', type=Path,
                        default=here / 'docs/engineering/IOS27-FLIGHT-BLOCKERS.toml')
    parser.add_argument('--entries', type=Path,
                        default=here / 'docs/engineering/IOS27-REFERENCE-FIRST.toml')
    parser.add_argument('--sources', type=Path,
                        default=here / 'docs/engineering/UPSTREAM-REPOS.toml')
    arguments = parser.parse_args(argv)

    code, problems = check(arguments.blockers, arguments.entries, arguments.sources)
    for problem in problems:
        print(f'{"FAIL" if code == 1 else "note"}: {problem}')
    if code == 0:
        print(f'OK reference-first: every open blocker cites '
              f'{MIN_SOURCES}+ registered sources with resolvable file:line readings')
    elif code == 2:
        print('note: the gate could not judge, which is not the same as passing (P-279)')
    return code


if __name__ == '__main__':
    sys.exit(main())
