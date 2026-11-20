#!/usr/bin/env python3
"""`fastboot boot` must live in scripts/flash.sh and nowhere else (iron rule 14).

Typing `fastboot boot` by hand skips the porting gate, the eight-step gate, the
boot-procedure gate, the argument audit and the capture supervisor -- three
flights in 2026-11-14 produced a 0-byte console exactly that way. Any other file
that calls fastboot is listed here with the reason it is allowed.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {
    'scripts/flash.sh': 'the one entry point',
    'AGENTS.md': 'documents the command',
    'docs/engineering': 'documents the command',
    'docs/research': 'documents the command',
    'README.md': 'documents the command',
    'README_EN.md': 'documents the command',
}
# an INVOCATION, not a mention: in command position at line start or after a separator
PATTERN = re.compile(r'(?:^|[|;&(]\s*|sudo\s+)fastboot(?:\.exe)?\s+boot\b')


def main():
    listed = subprocess.run(['git', '-C', str(ROOT), 'ls-files'], capture_output=True, text=True)
    if listed.returncode:
        print('FAIL: not a git checkout')
        return 2
    problems = []
    for relative in listed.stdout.splitlines():
        # only executables can be typed by mistake; docs explain the command
        if not relative.endswith(('.sh', '.ps1', '.py', '.cmd', '.bat')):
            continue
        if any(relative == key or relative.startswith(key.rstrip('/') + '/') for key in ALLOWED):
            continue
        path = ROOT / relative
        try:
            text = path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if PATTERN.search(line):
                problems.append('%s:%d calls fastboot boot outside flash.sh: %s'
                                % (relative, number, line.strip()[:80]))
    for problem in problems:
        print('FAIL: ' + problem)
    print('checked %d tracked file(s), %d stray caller(s)' % (len(listed.stdout.splitlines()), len(problems)))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
