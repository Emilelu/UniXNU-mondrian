#!/usr/bin/env python3
"""ccache front end that also writes clang's -MJ compile record.

XNU's make rules pass `-MJ <obj>.json` so that later steps can read the compile
arguments (bootstrap detection, archive builders, P-301 evidence).  ccache 4.9
refuses any command line containing `-MJ` ("Compiler option -MJ is
unsupported"), so every compile bypasses the cache and a 500-object rebuild
costs ten minutes.

This wrapper sits between make and ccache: it removes `-MJ <file>` from the
command line, runs the real compiler through ccache, and writes the same JSON
record clang would have written.  The record's `arguments` keep the original
flags (minus -MJ) so consumers see exactly what the compiler saw.

Usage from make (MakeInc.def: KCC = $(CCACHE) $(CC)):
    CCACHE="python3 scripts/k60-ccache.py /usr/bin/ccache"
"""
from __future__ import annotations

import json
import os
import subprocess
import sys


def split_mj(argv: list[str]) -> tuple[list[str], str | None]:
    out: list[str] = []
    record = None
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == '-MJ' and index + 1 < len(argv):
            record = argv[index + 1]
            index += 2
            continue
        if arg.startswith('-MJ') and len(arg) > 3:
            record = arg[3:]
            index += 1
            continue
        out.append(arg)
        index += 1
    return out, record


def source_and_output(argv: list[str]) -> tuple[str | None, str | None]:
    source = output = None
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == '-o' and index + 1 < len(argv):
            output = argv[index + 1]
            index += 2
            continue
        if arg == '-c' and index + 1 < len(argv):
            source = argv[index + 1]
            index += 2
            continue
        if arg.endswith('.c') or arg.endswith('.cpp') or arg.endswith('.m') or arg.endswith('.mm') or arg.endswith('.s') or arg.endswith('.S'):
            if not arg.startswith('-'):
                source = arg
        index += 1
    return source, output


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        print('k60-ccache: no command', file=sys.stderr)
        return 2
    compiler = argv[0]
    cleaned, record = split_mj(argv[1:])
    if compiler.endswith('ccache'):
        command = [compiler] + cleaned
    else:
        command = [compiler] + cleaned
    status = subprocess.call(command)
    if status == 0 and record:
        source, output = source_and_output(cleaned)
        payload = {
            'directory': os.getcwd(),
            'file': os.path.abspath(source) if source else '',
            'output': os.path.abspath(output) if output else '',
            'arguments': command,
        }
        try:
            with open(record, 'w', encoding='utf-8') as handle:
                json.dump(payload, handle)
                handle.write('\n')
        except OSError as error:
            print(f'k60-ccache: cannot write {record}: {error}', file=sys.stderr)
            return status
    return status


if __name__ == '__main__':
    sys.exit(main())
