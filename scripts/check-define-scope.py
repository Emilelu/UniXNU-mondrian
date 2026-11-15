#!/usr/bin/env python3
"""check-define-scope.py -- one define, one scope (P-208).

XNU's build hands out `-D` flags per object through `<obj>_CFLAGS_ADD`. A guard
written in one file therefore stays empty unless *that* object receives the
define. Measured 2026-11-15: `-DXNU_K60_PHYSICAL_BATTERY=1` was attached to
`KernelConfigTables.cpo` only, while the guarded blocks live in
`iokit/bsddev/IOKitBSDInit.cpp`; the battery entry point and the ADSP publisher
were dead code for a day and the link stayed green because `-force_load` keeps
the archive symbols in the kernel (P-208).

This gate reconstructs the mapping from the build script and the patch series:

  * a define is *global* when it is assigned to EXTRA_CFLAGS (which every object
    inherits through RC_NONARCH/CFLAGS),
  * otherwise it reaches exactly the objects named by `<obj>_CFLAGS_ADD`,
  * shell variables are resolved: `PERSONALITY_CFLAGS` accumulates defines and is
    then handed to one object, so `<obj>_CFLAGS_ADD=$PERSONALITY_CFLAGS` gives
    that object every define the variable can hold,
  * a guard in file F must be reachable by F's object.

Defines that never appear in the build script are reported as unknown, not as
failures: they come from somewhere this gate does not model (a config header, a
makefile), and inventing a verdict there would be the P-194 mistake again.

P-213: the first version of this gate did not resolve variables and therefore
reported `XNU_NATIVE_RAM_BLOCK` as reaching only `kern_exec.o` -- a false
positive, because the define is accumulated into `PERSONALITY_CFLAGS` and handed
to `KernelConfigTables.cpo`. A gate that reads only the literal text of an
assignment models the shell badly and cries wolf; the fix is to follow the
variable, which is what the shell does.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

BUILD_SCRIPT = 'scripts/build-xnu-4k-baseline.sh'
SERIES = 'patches/xnu/series'

# VAR=...            (plain assignment, may also append: VAR="$VAR -D...")
ASSIGN = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)=(.+)$')
# <obj>_CFLAGS_ADD=<expr>
OBJECT_FLAGS = re.compile(r'([A-Za-z0-9_.+-]+)_CFLAGS_ADD=')
DEFINE_TOKEN = re.compile(r'-DXNU_([A-Z0-9_]+)')
VAR_REF = re.compile(r'\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?')
GUARD = re.compile(r'#\s*(?:if|elif)\s+(?:defined\s*\(\s*XNU_([A-Z0-9_]+)|XNU_([A-Z0-9_]+))')
HUNK_FILE = re.compile(r'^\+\+\+ b/(\S+)')

C_SUFFIXES = {'.c': '.o', '.cpp': '.cpo', '.cc': '.cpo', '.cxx': '.cpo',
              '.s': '.o', '.S': '.o', '.m': '.o', '.mm': '.o'}


def object_name(path: str) -> str:
    p = Path(path)
    return p.stem + C_SUFFIXES.get(p.suffix, '.o')


def _strip_comment(line: str) -> str:
    """Drop a trailing shell comment so `VAR=x  # -DFOO` is not counted."""
    out = []
    quote = None
    for index, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
            out.append(ch)
            continue
        if ch in ('"', "'"):
            quote = ch
            out.append(ch)
            continue
        if ch == '#' and (index == 0 or line[index - 1] in ' \t'):
            break
        out.append(ch)
    return ''.join(out)


def read_variables(text: str) -> dict[str, set[str]]:
    """Map every shell variable to the XNU defines it can carry.

    Handles both `VAR=-DXNU_A` and `VAR="$VAR -DXNU_B"`; the second form makes
    the define set grow, which is exactly how PERSONALITY_CFLAGS is built.
    """
    variables: dict[str, set[str]] = {}
    for raw in text.splitlines():
        line = _strip_comment(raw)
        match = ASSIGN.match(line)
        if not match:
            continue
        name, value = match.group(1), match.group(2)
        defines = set(DEFINE_TOKEN.findall(value))
        for ref in VAR_REF.findall(value):
            defines |= variables.get(ref, set())
        if defines:
            variables.setdefault(name, set()).update(defines)
        else:
            variables.setdefault(name, set())
    return variables


def read_global_defines(variables: dict[str, set[str]]) -> set[str]:
    return set(variables.get('EXTRA_CFLAGS', set()))


def read_object_defines(text: str, variables: dict[str, set[str]]) -> dict[str, set[str]]:
    table: dict[str, set[str]] = {}
    for raw in text.splitlines():
        line = _strip_comment(raw)
        if 'EXTRA_MAKE_ARGS' not in line or '_CFLAGS_ADD=' not in line:
            continue
        for obj in OBJECT_FLAGS.findall(line):
            chunk = line.split(f'{obj}_CFLAGS_ADD=', 1)[1]
            defines = set(DEFINE_TOKEN.findall(chunk))
            for ref in VAR_REF.findall(chunk):
                defines |= variables.get(ref, set())
            table.setdefault(obj, set()).update(defines)
    return table


def parse_series(series: Path) -> list[str]:
    entries = []
    for raw in series.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        entries.append(line)
    return entries


def scan_patch(path: Path) -> list[tuple[str, str, int]]:
    """Return (define, file, line-number-in-patch) for every guard in the patch."""
    found: list[tuple[str, str, int]] = []
    current = None
    for number, line in enumerate(path.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
        match = HUNK_FILE.match(line)
        if match:
            current = match.group(1)
            continue
        if current is None:
            continue
        body = line[1:] if line[:1] in '+ ' else None
        if body is None:
            continue
        guard = GUARD.search(body)
        if guard:
            found.append((guard.group(1) or guard.group(2), current, number))
    return found


def check(repo: Path = REPO) -> tuple[list[str], list[str], int]:
    text = (repo / BUILD_SCRIPT).read_text(encoding='utf-8')
    variables = read_variables(text)
    global_defines = read_global_defines(variables)
    object_defines = read_object_defines(text, variables)

    reach: dict[str, set[str]] = {}
    for obj, defines in object_defines.items():
        for define in defines:
            reach.setdefault(define, set()).add(obj)

    problems: list[str] = []
    unknowns: list[str] = []
    guards = 0
    for entry in parse_series(repo / SERIES):
        patch = repo / 'patches/xnu' / entry
        if not patch.is_file():
            problems.append(f'series entry {entry} has no patch file')
            continue
        for define, target, number in scan_patch(patch):
            guards += 1
            if define in global_defines:
                continue
            obj = object_name(target)
            objects = reach.get(define)
            if objects is None:
                unknowns.append(f'{entry}:{number} XNU_{define} is not assigned by {BUILD_SCRIPT}')
                continue
            if obj in objects:
                continue
            problems.append(
                f'{entry}:{number} XNU_{define} guards {target} (object {obj}) but the '
                f'define only reaches {", ".join(sorted(objects))}; that block compiles away (P-208)'
            )
    return problems, unknowns, guards


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='one define, one scope (P-208)')
    parser.add_argument('--repo', default=str(REPO))
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    problems, unknowns, guards = check(Path(args.repo))
    if args.json:
        print(json.dumps({'guards': guards, 'problems': problems, 'unknowns': unknowns}, indent=1))
    else:
        for line in unknowns:
            print(f'skip: {line}')
        for line in problems:
            print(f'FAIL: {line}')
        if problems:
            print(f'❌ define scope: {len(problems)} guard(s) cannot see their define')
            return 1
        print(f'✅ define scope: {guards} guard(s) all reachable')
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
