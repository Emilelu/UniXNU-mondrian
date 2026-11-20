#!/usr/bin/env python3
"""Which DarwinBoot does the 27 firmware actually compile, and can it read a fileset?

`check-ios27-artifacts.py` judges the kernel collection. This judges the other
half of the same handshake: the loader that the platform DSC puts in the volume.
Those are separate questions with separate answers, and on 2026-11-20 we spent a
day treating them as one -- the collection check said "one member's cpusubtype is
wrong", which was true, and everyone read it as "the loader is nearly fine",
which was not: `[firmware].packages` puts `{uefi}/Platforms/Xiaomi` ahead of any
catalog driver, so the source that gets compiled is the vendored copy whose first
test is `cpusubtype == 0 && filetype == 2`. A collection with every child header
correct is still refused by it, because it never reaches the children.

So this gate answers one question by reading the files that the build would read:

    walk PACKAGES_PATH in order, take the first `mondrian.dsc`, take the first
    `DarwinBootPkg/Driver/DarwinBoot.c` the search path provides, and report
    whether that source has an `MH_FILESET` path.

Verdicts:
  0  the selected source reads filetype 12 / LC_FILESET_ENTRY
  1  it does not: the shipped loader cannot accept our kernel, whatever its headers
  2  the question could not be answered (no DSC, no provider, unreadable input)
     -- "I could not tell" is not "it is fine" (P-279)

`--strict` turns verdict 1 into a non-zero exit, for a caller that wants to stop
the build rather than record the blocker. The default is to report and exit 0,
because a structural build should keep producing artifacts for the other gates
while this defect is open; the flight gate is where it becomes fatal.
"""
import argparse
import re
import sys
from pathlib import Path

PLATFORM = 'Platforms/Xiaomi/mondrianPkg'
DRIVER = Path('DarwinBootPkg/Driver/DarwinBoot.c')
INF = 'DarwinBootPkg/Driver/DarwinBoot.inf'

# Tokens that only appear in a loader that knows about filesets. Kept to what a
# source file must contain to act on one: the constant, its numeric value, or a
# comparison against filetype 12. A comment mentioning "fileset" does not count,
# so the scan runs on code with comments stripped (`strip_comments`).
FILESET_TOKENS = ('LC_FILESET_ENTRY', '0x80000035', '80000035')


def strip_comments(text):
    """Drop /* */ and //, so a comment cannot satisfy a token check (P-245's cousin)."""
    text = re.sub(r'/\*.*?\*/', ' ', text, flags=re.S)
    return re.sub(r'//[^\n]*', ' ', text)


def has_fileset_path(source_text):
    """True when the loader can branch on MH_FILESET (filetype 12).

    Two shapes count, because a loader can be written either way: naming the
    load-command constant, or comparing the header's filetype against 12.
    """
    code = strip_comments(source_text)
    if any(token in code for token in FILESET_TOKENS):
        return True
    # `U32 (Data + 12) != 12` / `FileType != MH_FILESET` style tests.
    return re.search(r'(?i)filetype[^\n]{0,40}\b12\b', code) is not None or \
        re.search(r'\+\s*12\s*\)\s*!=\s*12', code) is not None


def find_platform(search):
    """First `<dir>/PLATFORM/mondrian.dsc` in search order, plus the dir that provided it.

    EDK II takes the first match on PACKAGES_PATH, so the first hit here is the
    one the build compiles -- that is the whole point of walking in order.
    """
    for root in search:
        candidate = Path(root) / PLATFORM / 'mondrian.dsc'
        if candidate.is_file():
            return candidate, Path(root)
    return None, None


def selected_provider(search, name=DRIVER):
    """First provider of `name` along the search path, the same way EDK II picks one."""
    for root in search:
        candidate = Path(root) / name
        if candidate.is_file():
            return candidate, Path(root)
    return None, None


def describes_driver(dsc_path):
    """Whether the DSC names the DarwinBoot driver at all (a DSC that does not is a wrong answer)."""
    try:
        text = Path(dsc_path).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return False
    return INF in text or 'DarwinBoot' in text


def check(search, platform=None):
    """Return a dict with the verdict, the files it read, and why."""
    if platform:
        global PLATFORM
        PLATFORM = platform
    dsc, dsc_root = find_platform(search)
    result = {'dsc': dsc, 'dsc_root': dsc_root, 'source': None, 'source_root': None,
              'fileset': False, 'kind': 'unknown', 'note': ''}
    if dsc is None:
        result['kind'] = 'no-dsc'
        result['note'] = ('no %s along the search path, so which loader the build compiles '
                          'is unknown' % (PLATFORM + '/mondrian.dsc'))
        return result
    source, source_root = selected_provider(search)
    result['source'], result['source_root'] = source, source_root
    if source is None:
        result['kind'] = 'no-provider'
        result['note'] = ('%s names a DarwinBoot driver but no %s exists along the search '
                          'path, so the compiled source is unknown' % (dsc, DRIVER))
        return result
    text = Path(source).read_text(encoding='utf-8', errors='replace')
    result['fileset'] = has_fileset_path(text)
    result['split_roots'] = source_root != dsc_root
    result['kind'] = 'fileset' if result['fileset'] else 'execute-only'
    if result['fileset']:
        result['note'] = ('%s branches on filetype 12 / LC_FILESET_ENTRY' % source)
    else:
        result['note'] = ('%s accepts only cpusubtype 0 with filetype 2: a 27 collection '
                          'never reaches its children' % source)
    return result


def search_from_board(device, fields):
    """The PACKAGES_PATH order the build will use, read from board.toml itself.

    A gate that hardcoded this order would be testing its own copy: the whole
    reason `{uefi}/Platforms/Xiaomi` wins today is that it sits third in this
    list, so the list has to come from the file the build reads.
    """
    import tomllib
    board = Path(device) / 'board.toml'
    data = tomllib.loads(board.read_text(encoding='utf-8'))
    packages = (data.get('firmware') or {}).get('packages') or []

    class Missing(dict):
        def __missing__(self, key):
            raise SystemExit('board.toml uses {%s} but no value was given for it; '
                             'pass --%s' % (key, key))

    return [item.format_map(Missing(fields)) for item in packages]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--search', action='append', default=None, metavar='DIR',
                        help='one PACKAGES_PATH entry, in build order; repeat for each')
    parser.add_argument('--board', type=Path, default=None,
                        help='device repository: take the order from its [firmware].packages')
    parser.add_argument('--uefi', default=None, help='value for the {uefi} placeholder')
    parser.add_argument('--tree', default=None, help='value for the {tree} placeholder')
    parser.add_argument('--soc', default=None, help='value for the {soc} placeholder')
    parser.add_argument('--edk2', default=None, help='value for the {edk2} placeholder')
    parser.add_argument('--dsc', type=Path, default=None,
                        help='use this DSC instead of walking the search path')
    parser.add_argument('--platform', default=None,
                        help='platform subdirectory under each search root')
    parser.add_argument('--strict', action='store_true',
                        help='exit 1 when the selected loader has no fileset path')
    args = parser.parse_args(argv)

    search = list(args.search or [])
    if args.board:
        search = search_from_board(args.board, {
            'uefi': args.uefi, 'tree': args.tree, 'soc': args.soc, 'edk2': args.edk2,
            'device': args.board, 'framework': '', 'build': ''})
    if args.dsc:
        search = [str(args.dsc.parents[2])] if len(args.dsc.parents) >= 3 else search
    if not search:
        print('FAIL: no --search or --board; pass the [firmware].packages order', file=sys.stderr)
        return 2

    result = check(search, platform=args.platform)
    if result['kind'] in ('no-dsc', 'no-provider'):
        print('FAIL: %s' % result['note'])
        return 2
    if result['fileset']:
        print('ok firmware: %s' % result['note'])
        print('ok firmware: loader source %s, search root %s' % (result['source'], result['source_root']))
        if result.get('split_roots'):
            print('note firmware: the DSC came from %s but the driver from %s; EDK II resolves '
                  'each package separately, so this pairing is what the build would compile'
                  % (result['dsc_root'], result['source_root']))
        return 0
    print('note firmware: %s' % result['note'])
    if result.get('split_roots'):
        print('note firmware: the DSC came from %s but the driver from %s; EDK II resolves '
              'each package separately, so this pairing is what the build would compile'
              % (result['dsc_root'], result['source_root']))
    print('note firmware: this is the firmware-fileset-provider blocker, not a collection-header '
          'defect; fixing the child cpusubtype does not help while this source is selected')
    return 1 if args.strict else 0


if __name__ == '__main__':
    sys.exit(main())
