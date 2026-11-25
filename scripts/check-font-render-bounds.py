#!/usr/bin/env python3
"""Guard the glyph renderer against a scaling bug that corrupts every glyph.

`iso_font` stores one glyph as ISO_CHAR_HEIGHT (16) bytes, one byte per row.
`vc_render_char()` walks those bytes; its loop bound therefore has to stay
ISO_CHAR_HEIGHT no matter what the on-screen cell height is.  The K60 font
scale macro VC_CH is (ISO_CHAR_HEIGHT * vc_k60_sy): using it as the loop bound
reads three glyphs' worth of bytes for one glyph and writes 1,536 bytes into a
512-byte slot at scale 3, so the rendered font becomes solid blocks and the
heap behind it is overwritten.

The reverse-cursor and scroll helpers do walk screen rows, so VC_CH is correct
there.  This check enforces that split.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SCREEN_ROW_USERS = {
    'vc_reverse_cursor',
    'vc_scroll_down',
    'vc_scroll_up',
}

LOOP = re.compile(r'for\s*\(\s*line\s*=\s*0\s*;\s*line\s*<\s*([A-Za-z_][A-Za-z0-9_]*)\s*;')


def find_source(root: Path) -> Path | None:
    candidates = [
        root / 'osfmk' / 'console' / 'video_console.c',
        root / '.cache' / 'xnu-work' / 'osfmk' / 'console' / 'video_console.c',
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def enclosing_function(lines: list[str], index: int) -> str | None:
    """Return the name of the function whose body contains this line."""
    for back in range(index, -1, -1):
        match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*\(', lines[back])
        if match:
            return match.group(1)
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--tree', default='.', help='XNU source tree or assembled tree')
    args = parser.parse_args()

    source = find_source(Path(args.tree))
    if source is None:
        print(f'FONT: cannot find osfmk/console/video_console.c under {args.tree}')
        return 2

    lines = source.read_text(errors='replace').splitlines()
    problems: list[str] = []
    checked = 0
    for number, line in enumerate(lines, start=1):
        match = LOOP.search(line)
        if not match:
            continue
        bound = match.group(1)
        function = enclosing_function(lines, number - 1)
        if function == 'vc_render_char':
            checked += 1
            if bound != 'ISO_CHAR_HEIGHT':
                problems.append(
                    f'{source}:{number}: vc_render_char walks the font bitmap with '
                    f'"{bound}", which is the scaled cell height, not the 16-byte glyph')
        elif bound == 'VC_CH' and function not in SCREEN_ROW_USERS:
            problems.append(
                f'{source}:{number}: VC_CH used in {function or "an unknown function"}, '
                'which is neither a screen-row helper nor vc_render_char')

    if checked == 0:
        print(f'FONT: vc_render_char not found in {source}')
        return 2
    if problems:
        for problem in problems:
            print('FAIL ' + problem)
        return 1
    print(f'FONT OK {checked} glyph loop(s) walk ISO_CHAR_HEIGHT; VC_CH only in screen-row helpers')
    return 0


if __name__ == '__main__':
    sys.exit(main())
