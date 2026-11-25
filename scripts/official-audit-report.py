#!/usr/bin/env python3
"""Report what the official-page audit covers against the page registry.

Iron rule 13 says every page under the documentation site has to be read and
turned into a requirement with a gate.  The audit itself arrives as one JSON
file per batch; this reader turns those files into a coverage table so that
"how many pages are still unread" is a number instead of a feeling.

It is deliberately a *report*, not a gate on the requirements themselves: a
page can be read and still legitimately have no assertion we can run offline
(``na``), and a page can be judged and still be waiting for the registry entry
to be written by hand.  What it does refuse is a JSON that names a page the
registry does not know, because that means the two lists have drifted apart.

Usage:
    python3 scripts/official-audit-report.py [--audit-dir DIR] [--json]
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / 'docs/engineering/OFFICIAL-REQUIREMENTS.toml'
DEFAULT_AUDIT_DIR = Path('/mnt/e/iOS Port/Work/scratch')
STATUSES = ('satisfied', 'unknown', 'na')
KINDS = ('config', 'build', 'artifact', 'runtime', 'doc', 'process')


class Failure(Exception):
    """A condition the report refuses to paper over."""


def registry_pages(path=REGISTRY):
    """Return {page path relative to docs/zh: state} from the registry."""
    try:
        import tomllib
    except ModuleNotFoundError:  # python 3.10 and older
        raise Failure('python 3.11 or newer is needed for tomllib')

    text = Path(path).read_text(encoding='utf-8')
    data = tomllib.loads(text)
    pages = data.get('page') or []
    if not pages:
        raise Failure(f'{path} has no [[page]] entries')

    seen = {}
    for entry in pages:
        name = entry.get('path')
        if not name:
            raise Failure(f'{path}: an entry has no path')
        if name in seen:
            raise Failure(f'{path}: {name} appears twice')
        state = entry.get('state')
        if state not in ('mapped', 'unmapped', 'na'):
            raise Failure(f'{path}: {name} has state {state!r}')
        seen[name] = state
    return seen


def audit_files(directory):
    """Return the audit JSON files that look like ours."""
    root = Path(directory)
    if not root.is_dir():
        raise Failure(f'no audit directory at {root}')
    files = sorted(p for p in root.glob('audit-*.json'))
    if not files:
        raise Failure(f'no audit-*.json files in {root}')
    return files


def page_name(raw):
    """Reduce a page reference to its path below docs/zh.

    Batches were asked for paths relative to ``docs/zh``; one of them wrote the
    absolute path of the checkout instead.  Both have to land on the same key,
    because the registry is the list of pages and two spellings of one page
    would look like two pages -- and silently leave one of them unmapped.
    """
    text = str(raw).replace('\\', '/')
    marker = 'docs/zh/'
    if marker in text:
        text = text.split(marker, 1)[1]
    return text.lstrip('./')


def load_audit(path):
    """Return {page: [requirement dicts]} for one audit file."""
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except json.JSONDecodeError as error:
        raise Failure(f'{path}: not JSON ({error})')
    pages = data.get('pages')
    if not isinstance(pages, list) or not pages:
        raise Failure(f'{path}: no "pages" list')

    out = {}
    for page in pages:
        name = page.get('path')
        if not name:
            raise Failure(f'{path}: a page has no path')
        name = page_name(name)
        if name in out:
            raise Failure(f'{path}: {name} appears twice in one batch')
        rows = page.get('requirements')
        if not isinstance(rows, list):
            raise Failure(f'{path}: {name} has no "requirements" list')
        for row in rows:
            status = row.get('status')
            if status not in STATUSES:
                raise Failure(f'{path}: {name} has status {status!r}')
            kind = row.get('kind')
            if kind is not None and kind not in KINDS:
                raise Failure(f'{path}: {name} has kind {kind!r}')
            if not row.get('gate_idea'):
                raise Failure(f'{path}: {name} has a row without gate_idea')
        out[name] = rows
    return out


def merge(files):
    """Merge every batch, refusing two batches that claim the same page."""
    pages = {}
    owner = {}
    for path in files:
        for name, rows in load_audit(path).items():
            if name in pages:
                raise Failure(
                    f'{name} is audited twice: {owner[name].name} and '
                    f'{Path(path).name}; delete one before reporting')
            pages[name] = rows
            owner[name] = Path(path)
    return pages


def counts(rows):
    out = {status: 0 for status in STATUSES}
    for row in rows:
        out[row['status']] += 1
    return out


def report(pages, registered):
    """Print the coverage table; return the exit code."""
    unknown_pages = sorted(set(pages) - set(registered))
    lines = []
    total = {status: 0 for status in STATUSES}

    for name in sorted(pages):
        tally = counts(pages[name])
        for status in STATUSES:
            total[status] += tally[status]
        state = registered.get(name, 'NOT-IN-REGISTRY')
        lines.append(f'{name:52s} {len(pages[name]):3d} rows  '
                     f'sat {tally["satisfied"]:3d}  unk {tally["unknown"]:3d}'
                     f'  na {tally["na"]:3d}  registry {state}')

    audited = set(pages)
    unread = sorted(p for p in registered if p not in audited)
    waiting = sorted(p for p in audited
                     if registered.get(p) == 'unmapped')
    print('\n'.join(lines))
    print()
    print(f'pages in the registry     : {len(registered)}')
    print(f'pages audited             : {len(audited)}')
    print(f'audited but still unmapped: {len(waiting)}')
    print(f'never audited             : {len(unread)}')
    print(f'requirement rows          : {sum(total.values())} '
          f'(satisfied {total["satisfied"]}, unknown {total["unknown"]}, '
          f'na {total["na"]})')
    if unknown_pages:
        print()
        print('FAIL the audit names pages the registry does not have: '
              + ', '.join(unknown_pages))
        return 1
    if unread:
        shown = ', '.join(unread[:8])
        more = '' if len(unread) <= 8 else f' … (+{len(unread) - 8})'
        print(f'unread pages: {shown}{more}')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--audit-dir', default=str(DEFAULT_AUDIT_DIR),
                        help='directory holding audit-*.json')
    parser.add_argument('--registry', default=str(REGISTRY))
    parser.add_argument('--json', action='store_true',
                        help='print the coverage as JSON')
    args = parser.parse_args(argv)

    try:
        registered = registry_pages(args.registry)
        pages = merge(audit_files(args.audit_dir))
    except Failure as error:
        print(f'FAIL: {error}')
        return 2

    if args.json:
        payload = {
            'registry': registered,
            'audited': {name: counts(rows) for name, rows in pages.items()},
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if set(pages) <= set(registered) else 1
    return report(pages, registered)


if __name__ == '__main__':
    sys.exit(main())
