#!/usr/bin/env python3
"""The presenter must not rebuild the source import when the pages are the same.

Measured on 2026-11-18: `present()` cost 16.8 ms of a 17 ms frame while copying
18.4 MB, which is about 1.1 GB/s -- far below what an A730 blit reaches. The
suspicion is that `newBufferWithBytesNoCopy` re-maps every page into the GPU
context on every frame. The cache is only correct if it keys on the pages
themselves, releases the previous import, and reports both counts.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PRESENTER = ROOT / 'drivers/PongMetal/GpuScanoutPresenter.h'
SCANOUT = ROOT / 'drivers/PongMetal/PongMetalScanout.h'

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    presenter = PRESENTER.read_text(encoding='utf-8')
    scanout = SCANOUT.read_text(encoding='utf-8')

    # The import is cached, keyed on both the pointer and the length.
    check('importedBase_ == frame.base && importedBytes_ == frame.bytes' in presenter,
          'the import cache does not key on the pages and their length')
    # A fresh import still happens when the pages change.
    check('newBufferWithBytesNoCopy' in presenter,
          'the presenter never imports the source at all')
    # The replaced import is released. This binary is built with -fobjc-arc, so an explicit
    # release is a compile error; assigning to the strong ivar is what releases the old buffer.
    presenter_arc = '-fobjc-arc' in (ROOT / 'scripts/build-pong-metal-plugin.py').read_text(encoding='utf-8')
    if presenter_arc:
        check('[imported_ release]' not in presenter,
              'the presenter sends release to an ARC object')
        check('imported_ = fresh;' in presenter,
              'the replaced import is never dropped from the strong reference')
    else:
        check('[imported_ release]' in presenter,
              'the replaced source import is never released')
    # Both outcomes are counted, so a flight can tell reuse from rebuild.
    check('++imports_;' in presenter and '++reuses_;' in presenter,
          'the presenter does not count imports and reuses')
    # The counters reach the rendered report, otherwise the flight cannot see them.
    check('imports=%llu reuses=%llu' in scanout,
          'the scanout report does not carry the import counters')
    check('presenter->imports()' in scanout and 'presenter->reuses()' in scanout,
          'the scanout report does not read the presenter counters')
    # The import itself is timed, so the flight can tell a slow mapping from a slow blit.
    check('import=%llu us' in scanout and 'importMicroseconds()' in scanout,
          'the scanout report does not carry the import duration')
    check('lastImportUs_' in presenter,
          'the presenter does not measure how long the import took')
    # The frame still waits for the GPU before it is handed to the scanout.
    check('[commands waitUntilCompleted]' in presenter,
          'the presenter no longer waits for the copy to retire')

    width = presenter.find('imports=%llu reuses=%llu')
    check(width == -1 or 'lastCopy/1000' in scanout,
          'the extended report dropped the copy timing it used to carry')
    # The report buffer has to be big enough for the two extra numbers.
    check('char rate[320]' in scanout,
          'the report buffer was not grown for the import counters')

    for failure in failures:
        print('FAIL:', failure)
    if failures:
        return 1
    print('TESTS OK 7 case(s) (0 failure(s))')
    return 0


if __name__ == '__main__':
    sys.exit(main())
