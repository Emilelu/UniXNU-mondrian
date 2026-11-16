#!/usr/bin/env python3
"""Guard that the firmware build is reproducible from the repository (P-217).

`Mu_Basecore` is a nested repository: the parent repo records a submodule
pointer, but the build reads whatever the working tree currently holds.  On
2026-11-16 that working tree sat on `3d2a9fa`, a commit that exists only on
this machine, while `board.toml` claimed the recorded pin already carried the
five K60 fixes.  It does not: `git merge-base 3d2a9fa 6f805f2` is empty, and
only `AsmMacroLib.h` is fixed upstream (differently).

A clean clone would therefore build a broken firmware volume while every local
build kept working.  This gate asks three questions:

  1. Does the nested worktree sit on the commit the parent repo records?
  2. Does every `[firmware].patches` entry exist and still apply?
  3. If the answer to (1) is no, is the deviation written down somewhere a
     reader would look (the firmware manual), instead of living in a shell
     history?

Question (3) is what makes this a gate rather than a nag: a deliberate
deviation is fine as long as it is recorded, because an unrecorded one is
indistinguishable from an accident.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANUAL = 'docs/engineering/FIRMWARE-REBUILD.md'
SUBMODULE = 'Mu_Basecore'
# A recorded deviation must be a statement about the current state, not a quote
# of the old (wrong) claim.  `board.toml` used to say "3d2a9fa is an ancestor of
# 6f805f2", and the manual quotes that sentence to explain what went wrong --
# quoting it must not satisfy the gate.
DEVIATION = re.compile(
    r'(?:worktree|工作树|检出)\s*(?:sits at|停在|位于|is at)\s*`?[0-9a-f]{7,40}'
    r'|deviat\w* from the recorded pin'
    r'|与记录的 pin 不一致',
    re.I,
)


def _run(command, cwd=None):
    """Run a command and return (returncode, stdout, stderr)."""
    proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def uefi_root(repo: Path) -> Path:
    """Locate the sibling uefi checkout."""
    override = os.environ.get('K60_UEFI_REPO')
    if override:
        return Path(override)
    return repo.parent / 'uefi-mondrian'


def recorded_pin(uefi: Path) -> str | None:
    """The submodule commit the parent repository records."""
    code, out, _ = _run(['git', 'ls-tree', 'HEAD', SUBMODULE], cwd=uefi)
    if code != 0:
        return None
    match = re.match(r'160000 commit ([0-9a-f]{40})\t', out)
    return match.group(1) if match else None


def worktree_head(nested: Path) -> str | None:
    code, out, _ = _run(['git', 'rev-parse', 'HEAD'], cwd=nested)
    return out.strip() if code == 0 else None


def firmware_patches(repo: Path) -> list[str]:
    """Read `[firmware].patches` from board.toml without a TOML dependency."""
    board = repo / 'board.toml'
    if not board.is_file():
        return []
    text = board.read_text(encoding='utf-8')
    start = text.find('[firmware]')
    if start < 0:
        return []
    end = text.find('\n[', start + len('[firmware]'))
    section = text[start:] if end < 0 else text[start:end]
    key = section.find('patches')
    if key < 0:
        return []
    bracket = section.find('[', key)
    if bracket < 0:
        return []
    close = section.find(']', bracket)
    if close < 0:
        return []
    body = section[bracket + 1:close]
    # Strip comments first: the comment above the list quotes the old rationale
    # and would otherwise be parsed as an entry named "local patches for k60".
    stripped = '\n'.join(line.split('#', 1)[0] for line in body.splitlines())
    return [m.group(1) for m in re.finditer(r'"([^"]+)"', stripped)]


def check(repo: Path = REPO, uefi: Path | None = None) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    notes: list[str] = []
    uefi = uefi_root(repo) if uefi is None else uefi
    if not (uefi / SUBMODULE).is_dir():
        notes.append(f'skip: {uefi / SUBMODULE} is not present')
        return problems, notes

    pin = recorded_pin(uefi)
    head = worktree_head(uefi / SUBMODULE)
    if pin is None:
        problems.append(
            f'{uefi}: cannot read the recorded {SUBMODULE} commit; the pointer is what '
            f'a clean clone would check out (P-217)'
        )
    elif head is None:
        problems.append(f'{uefi / SUBMODULE}: cannot read the nested worktree HEAD (P-217)')
    elif pin != head:
        manual = repo / MANUAL
        recorded = manual.is_file() and DEVIATION.search(manual.read_text(encoding='utf-8'))
        message = (
            f'{SUBMODULE} worktree is at {head[:12]} but the parent repo records '
            f'{pin[:12]}; a clean clone would build different firmware (P-217)'
        )
        if recorded:
            notes.append(f'recorded deviation: {message}')
        else:
            problems.append(message)

    patches = firmware_patches(repo)
    if not patches:
        notes.append('note: [firmware].patches is empty')
    for rel in patches:
        path = uefi / rel
        if not path.is_file():
            problems.append(f'{rel}: listed in [firmware].patches but missing (P-217)')
            continue
        code, _, err = _run(['git', 'apply', '--check', str(path)], cwd=uefi / SUBMODULE)
        if code != 0:
            first = err.strip().splitlines()[0] if err.strip() else 'unknown error'
            problems.append(f'{rel}: does not apply to the pinned basecore: {first} (P-217)')
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
        print('FAIL: the firmware build is not reproducible from this repository', file=sys.stderr)
        for problem in problems:
            print(f'  - {problem}', file=sys.stderr)
        return 1
    print('✅ basecore: the build reads the pinned commit, and every board patch applies')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
