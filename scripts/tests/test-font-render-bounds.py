#!/usr/bin/env python3
"""Tests for scripts/check-font-render-bounds.py."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / 'scripts' / 'check-font-render-bounds.py'

GOOD = '''\
static void
vc_render_char(unsigned char ch, unsigned char *renderptr, short newdepth)
{
	int line;

	for (line = 0; line < ISO_CHAR_HEIGHT; line++) {
		unsigned char mask = 1;
	}
}

static void
vc_scroll_up(int num, unsigned int scrreg_top, unsigned int scrreg_bottom)
{
	int line;

	while (1) {
		for (line = 0; line < VC_CH; line++) {
		}
	}
}
'''

BAD_RENDER = GOOD.replace(
    'for (line = 0; line < ISO_CHAR_HEIGHT; line++) {',
    'for (line = 0; line < VC_CH; line++) {', 1)

BAD_OTHER = GOOD.replace(
    'vc_scroll_up(int num, unsigned int scrreg_top, unsigned int scrreg_bottom)',
    'vc_clear_screen(int num, unsigned int scrreg_top, unsigned int scrreg_bottom)')


def run(tree: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECK), '--tree', str(tree)],
        capture_output=True, text=True)


def write_tree(root: Path, body: str) -> None:
    path = root / 'osfmk' / 'console'
    path.mkdir(parents=True)
    (path / 'video_console.c').write_text(body)


def main() -> int:
    cases = 0
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        good = root / 'good'
        write_tree(good, GOOD)
        result = run(good)
        assert result.returncode == 0, result.stdout + result.stderr
        assert 'FONT OK' in result.stdout, result.stdout
        cases += 1

        bad = root / 'bad'
        write_tree(bad, BAD_RENDER)
        result = run(bad)
        assert result.returncode == 1, result.stdout
        assert 'vc_render_char' in result.stdout, result.stdout
        cases += 1

        other = root / 'other'
        write_tree(other, BAD_OTHER)
        result = run(other)
        assert result.returncode == 1, result.stdout
        assert 'vc_clear_screen' in result.stdout, result.stdout
        cases += 1

        missing = root / 'missing'
        missing.mkdir()
        result = run(missing)
        assert result.returncode == 2, result.stdout
        cases += 1

    print(f'TESTS OK {cases} cases')
    return 0


if __name__ == '__main__':
    sys.exit(main())
