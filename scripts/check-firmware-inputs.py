#!/usr/bin/env python3
"""Guard that build_uefi.py names only Resources/ inputs that exist (P-227).

On 2026-11-16 a full run of `build_uefi.py -d mondrian -r DEBUG` died at
`The Device DTB is Missing in "Resources/DTBs"!` on every single run, so the
next statement in the same function -- `"--ramdisk", "Resources/ramdisk"` --
had never executed since the line was written in f92c387.  The tree has never
carried a `Resources/ramdisk`; the first time the DTB was in place the run got
one statement further and mkbootimg.py aborted on the missing file.

A path that a build hands to a tool has to be one of two things: present in the
checkout, or named behind an explicit `is_file () / exists () / is_dir ()`
guard that turns "not here" into a decision.  This gate reads the sibling
uefi-mondrian checkout and reports every `Resources/...` literal that is
neither.

It is deliberately static: it does not run the build, so it cannot tell you
whether a guarded path is *also* missing at runtime.  What it can tell you is
that no unguarded input in that script is imaginary -- which is exactly the
class of bug that hides behind a failing earlier check.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = 'build_uefi.py'
RESOURCE = re.compile(r'^Resources/[^"\\]*$')
GUARD = r'\b{name}\s*\.\s*(?:is_file|exists|is_dir)\s*\('


def uefi_root(repo: Path) -> Path:
    """Locate the sibling uefi checkout."""
    override = os.environ.get('K60_UEFI_REPO')
    if override:
        return Path(override)
    return repo.parent / 'uefi-mondrian'


def _path_call(node: ast.AST) -> str | None:
    """The literal inside `Path ("Resources/...") `, if this is that call."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if not (isinstance(func, ast.Name) and func.id == 'Path'):
        return None
    if len(node.args) != 1:
        return None
    arg = node.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value if RESOURCE.match(arg.value) else None
    return None


def resource_literals(source: str) -> list[tuple[int, str, str | None]]:
    """Every Resources/ literal, with the variable it is bound to (if any)."""
    tree = ast.parse(source)
    aliases: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            literal = _path_call(node.value)
            if literal and isinstance(target, ast.Name):
                aliases.setdefault(literal, set()).add(target.id)

    found: list[tuple[int, str, str | None]] = []
    seen: set[tuple[str, int]] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        literal = node.value
        if not RESOURCE.match(literal):
            continue
        line = getattr(node, 'lineno', 0)
        if (literal, line) in seen:
            continue
        seen.add((literal, line))
        names = sorted(aliases.get(literal, ()))
        found.append((line, literal, names[0] if names else None))
    return sorted(found)


def guarded(source: str, literal: str, names: set[str]) -> bool:
    """Does any variable bound to this literal get an existence check?"""
    for name in names:
        if re.search(GUARD.format(name=re.escape(name)), source):
            return True
    return False


def check(repo: Path = REPO, uefi: Path | None = None) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    notes: list[str] = []
    uefi = uefi_root(repo) if uefi is None else uefi
    script = uefi / SCRIPT
    if not script.is_file():
        notes.append(f'skip: {script} is not present')
        return problems, notes

    source = script.read_text(encoding='utf-8', errors='replace')
    try:
        literals = resource_literals(source)
    except SyntaxError as error:
        problems.append(f'{SCRIPT}: cannot parse ({error}); the inputs are unverified (P-227)')
        return problems, notes

    aliases: dict[str, set[str]] = {}
    for _line, literal, name in literals:
        if name:
            aliases.setdefault(literal, set()).add(name)

    for line, literal, name in literals:
        path = uefi / literal
        if path.exists():
            continue
        if guarded(source, literal, aliases.get(literal, set())):
            notes.append(f'guarded: {SCRIPT}:{line} "{literal}" is absent but checked')
            continue
        problems.append(
            f'{SCRIPT}:{line}: "{literal}" is handed to the build but does not exist in '
            f'{uefi}, and nothing checks for it; the run will die here the first time an '
            f'earlier check lets it through (P-227)'
        )
    return problems, notes


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default=str(REPO), help='device repository root')
    parser.add_argument('--uefi', default=None, help='uefi checkout (default: sibling)')
    args = parser.parse_args(argv)
    problems, notes = check(Path(args.repo), None if args.uefi is None else Path(args.uefi))
    for note in notes:
        print(f'note: {note}')
    if problems:
        print('FAIL: the firmware build names inputs that are not in the checkout', file=sys.stderr)
        for problem in problems:
            print(f'  - {problem}', file=sys.stderr)
        return 1
    print('✅ firmware inputs: every Resources/ path build_uefi.py names exists or is guarded')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
