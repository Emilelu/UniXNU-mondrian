#!/usr/bin/env python3
"""Tests for scripts/audit-boot-args.py."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / 'scripts' / 'audit-boot-args.py'

BOARD_OURS = '''[payload]
kernel_args = ["alpha=1", "beta=2"]
'''
BOARD_THEIRS = '''[payload]
kernel_args = ["alpha=1", "beta=2", "gamma=3", "delta=4"]
'''
SOURCE = '''int
probe(void)
{
	int value = 0;
	if (PE_parse_boot_argn("gamma", &value, sizeof(value))) {
		return value;
	}
	return 0;
}
'''


def run(ours: Path, theirs: Path, tree: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECK), '--ours', str(ours), '--theirs', str(theirs),
         '--tree', str(tree)],
        capture_output=True, text=True)


def main() -> int:
    cases = 0
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ours = root / 'ours'
        theirs = root / 'theirs'
        tree = root / 'tree'
        ours.mkdir()
        theirs.mkdir()
        (tree / 'bsd' / 'kern').mkdir(parents=True)
        (ours / 'board.toml').write_text(BOARD_OURS)
        (theirs / 'board.toml').write_text(BOARD_THEIRS)
        (tree / 'bsd' / 'kern' / 'probe.c').write_text(SOURCE)

        result = run(ours, theirs, tree)
        assert result.returncode == 0, result.stdout + result.stderr
        assert 'ARGS candidates=2 reader=1 mention=0 absent=1' in result.stdout, result.stdout
        assert '| reader | `gamma`' in result.stdout, result.stdout
        assert '| absent | `delta`' in result.stdout, result.stdout
        cases += 1

        result = run(ours, theirs, root / 'not-a-tree')
        assert result.returncode == 2, result.stdout
        cases += 1

    print(f'TESTS OK {cases} cases')
    return 0


if __name__ == '__main__':
    sys.exit(main())
