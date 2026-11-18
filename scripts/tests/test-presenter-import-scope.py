#!/usr/bin/env python3
"""The source import must not outlive the mapping it points at.

The kernel offers a fresh IOMemoryMap per frame (PongAdrenoScanout.cpp
createMappingInTask, kIOMapAnywhere) and releases it immediately after the copy
retires. The render server's import is a raw-pointer no-copy buffer: the runtime
keeps reading the pointer until the buffer is released (NativeMetalObjects.rs
"stays mapped until the buffer is released"). So an import that survives the
present() call is an import pointing into a mapping the kernel already dropped.

A previous version cached the last import keyed on (address, length). That key
cannot distinguish "same pages" from "same virtual address reused", neither of
which this tree can prove, and the failure direction is a GPU DMA from pages
nobody owns. It was removed rather than mitigated; this guard keeps it removed.

The guard also pins the diagnostic that made the risk invisible in the first
place: report() formatted into a 256 byte buffer, so the tail of the rate line -
including the fields that would have shown the import count - was silently cut.
"""
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PRESENTER = os.path.join(REPO, 'drivers', 'PongMetal', 'GpuScanoutPresenter.h')
PLUGIN = os.path.join(REPO, 'drivers', 'PongMetal', 'PongMetalPlugin.mm')

FAILED = []
CASES = 0


def check(name, ok, detail=''):
    global CASES
    CASES += 1
    if ok:
        print('  ok   %s' % name)
    else:
        print('  FAIL %s%s' % (name, (': ' + detail) if detail else ''))
        FAILED.append(name)


def read(path):
    with open(path, encoding='utf-8') as handle:
        return handle.read()


def main():
    presenter = read(PRESENTER)
    plugin = read(PLUGIN)

    # Slice present() precisely, up to the next member. Slicing to end of file counted every
    # method added later: the 2026-11-19 pitched-copy agreement check imports the frame once
    # more, inside its own method, and made this case report "3 call sites inside present()".
    # A rule about one function has to be scoped to that function.
    start = presenter.find('Result present(const Frame &frame)')
    end = presenter.find('bool runBlitProbe(const Frame &frame)')
    check('the present() slice ends at the next member',
          start >= 0 and end > start,
          'a slice that runs to end of file silently widens with every new method')
    body = presenter[start:end]
    private = presenter[presenter.find('private:'):]

    check('no import is kept between frames',
          not re.search(r'\bimported_\b', presenter),
          'a cached MTLBuffer outlives the IOKit mapping that backs it')
    check('no reuse counter survives',
          not re.search(r'\b(reuses_|reuses)\b', presenter),
          'a reuse count would mean the removal was reverted')
    check('no cached address or length key survives',
          not re.search(r'\b(importedBase_|importedBytes_)\b', presenter),
          '(address, length) cannot prove the pages are the same pages')

    found = body.count('newBufferWithBytesNoCopy')
    check('the frame source is imported exactly once per call', found == 1,
          'found %d call sites inside present()' % found)
    check('the scanout target is created once, outside the frame loop',
          presenter.count('[device newBufferWithBytesNoCopy:scanout.base') == 1,
          'the destination is stable; only the source is per-frame')

    import_at = body.find('newBufferWithBytesNoCopy')
    commit_at = body.find('[commands commit];')
    return_at = body.rfind('return')
    check('the import is inside present()', import_at > 0,
          'an import outside present() has an unbounded lifetime')
    check('the import is made before the copy is committed', 0 < import_at < commit_at,
          'the buffer has to exist when the blit is encoded')
    check('the import is re-made for every frame', '++imports_;' in body,
          'the count is how a flight proves one import per frame')
    check('the local import is not stored on the object',
          not re.search(r'^\s*id<MTLBuffer>\s+source_?\s*;', private, re.M),
          'a strong member would keep the mapping alive past the frame')

    check('the removal is documented where the next reader looks',
          'already gone' in body or 'mapping that is already gone' in presenter,
          'without the reason someone will add the cache back')

    check('report() sizes for the longest caller', 'char line[768]' in plugin,
          'the rate line plus prefix and suffix is longer than 256 bytes')
    check('report() keeps the record on one line',
          "line[length-1]='\\n';" in plugin and "if(length && line[length-1]!='\\n')line[length++]='\\n';" in plugin,
          'a truncated diagnostic without a newline merges into the next record')
    check('report() writes the length it formatted',
          'write(2,line,length)' in plugin,
          'strlen after truncation is not the formatted length')

    print('TESTS %s %d case(s) (%d failure(s))'
          % ('OK' if not FAILED else 'FAILED', CASES, len(FAILED)))
    return 0 if not FAILED else 1


if __name__ == '__main__':
    sys.exit(main())
