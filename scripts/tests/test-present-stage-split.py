#!/usr/bin/env python3
"""A slow scanout copy has to name its stage, not just its total.

The porting guide asks a slow frame to be attributed to a stage: "提交到 GPU 完成"
belongs to a different owner than "运行时 commit 到提交". A single `copy=` number
cannot tell them apart, so the presenter records import, encode, submit and GPU
wait separately, and the report prints all of them.

This guard pins the shape of that instrumentation: the four clocks bracket exactly
the calls they claim to, every span goes through the shared timing helper (so the
arithmetic itself can be executed by scripts/tests/test-scanout-timing.py), the
report prints the fields in stage order, and both pitch branches of the copy and
the wait itself survive.

The numbers mean nothing if the arithmetic is wrong, which is why this file no
longer accepts an inline helper of its own: the helper moved to
PongScanoutTiming.h where a host compiler runs it.
"""
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PRESENTER = os.path.join(REPO, 'drivers', 'PongMetal', 'GpuScanoutPresenter.h')
SCANOUT = os.path.join(REPO, 'drivers', 'PongMetal', 'PongMetalScanout.h')
TIMING = os.path.join(REPO, 'drivers', 'PongMetal', 'PongScanoutTiming.h')

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


def order(text, needles):
    """Every needle appears, in this order; returns (ok, first missing)."""
    at = 0
    for needle in needles:
        found = text.find(needle, at)
        if found < 0:
            return False, needle
        at = found + len(needle)
    return True, ''


def main():
    presenter = read(PRESENTER)
    scanout = read(SCANOUT)
    timing = read(TIMING)

    check('the timing helper lives in its own host-testable header',
          'inline uint64_t elapsedUs(' in timing and '#include <metal/' not in timing.lower(),
          'the helper must be executable without Metal or Darwin headers')
    check('both translation units use the shared helper',
          '#include "PongScanoutTiming.h"' in presenter and '#include "PongScanoutTiming.h"' in scanout,
          'a local copy would drift from the tested one')
    check('the presenter does not carry a second microsecond helper',
          presenter.count('_k60Us(') == 0,
          'found %d references to the retired helper' % presenter.count('_k60Us('))

    body = presenter[presenter.find('Result present(const Frame &frame)'):]
    ok, missing = order(body, [
        'clock_gettime(CLOCK_MONOTONIC, &e0)',
        'id<MTLCommandBuffer> commands = [queue_ commandBuffer];',
        '[blit endEncoding];',
        'clock_gettime(CLOCK_MONOTONIC, &e1)',
        '[commands commit];',
        'clock_gettime(CLOCK_MONOTONIC, &e2)',
        '[commands waitUntilCompleted];',
        'clock_gettime(CLOCK_MONOTONIC, &e3)',
    ])
    check('the four clocks bracket the calls they name', ok, 'missing %r' % missing)

    check('each span is derived from its own pair of clocks',
          'lastEncodeUs_ = pongscanout::elapsedUs(e0, e1);' in body
          and 'lastSubmitUs_ = pongscanout::elapsedUs(e1, e2);' in body
          and 'lastWaitUs_ = pongscanout::elapsedUs(e2, e3);' in body,
          'a span that does not come from its own clocks is a guess')

    ok, missing = order(body, [
        'clock_gettime(CLOCK_MONOTONIC, &i0)',
        'newBufferWithBytesNoCopy',
        'clock_gettime(CLOCK_MONOTONIC, &i1)',
        'lastImportUs_ = pongscanout::elapsedUs(i0, i1);',
        '++imports_;',
    ])
    check('the import is timed around the real import call', ok, 'missing %r' % missing)

    for name in ('importMicroseconds', 'encodeMicroseconds', 'submitMicroseconds', 'waitMicroseconds'):
        check('the presenter exposes %s()' % name,
              re.search(r'uint64_t %s\(\) const \{ return last\w+Us_; \}' % name, presenter) is not None,
              'the report cannot read a span that has no accessor')

    check('the report prints every stage in stage order',
          order(scanout, ['wait=%llu us copy=%llu us done=%llu us;',
                          'imports=%llu import=%llu us encode=%llu us submit=%llu us gpu=%llu us',
                          'sum=%llu us'])[0],
          'import, encode, submit and gpu must stay adjacent and ordered')
    ok, missing = order(scanout, [
        'context->presenter->importMicroseconds()',
        'context->presenter->encodeMicroseconds()',
        'context->presenter->submitMicroseconds()',
        'context->presenter->waitMicroseconds()',
    ])
    check('the report reads the accessors in the same order', ok, 'missing %r' % missing)
    check('the sum is the four stages this side owns',
          'imported+encoded+submitted+waited' in scanout,
          'the flight compares sum against the kernel copy, so it must be explicit')
    check('the report buffer holds the longer line',
          'char rate[512]' in scanout,
          'four more fields do not fit in the 448 byte buffer')

    check('the equal pitch path is still one run',
          'copyFromBuffer:source sourceOffset:0 toBuffer:target_ destinationOffset:0 size:frame.stride * (frame.height - 1) + row' in presenter,
          'the fast path must not have been replaced by a loop')
    check('the differing pitch path still exists',
          'copyFromTexture:texture sourceSlice:0 sourceLevel:0' in presenter,
          'the texture path is what carries a pitch change')
    check('the copy is still waited for', '[commands waitUntilCompleted];' in presenter,
          'an unwaiting present would report frames the GPU never retired')

    print('TESTS %s %d case(s) (%d failure(s))'
          % ('OK' if not FAILED else 'FAILED', CASES, len(FAILED)))
    return 0 if not FAILED else 1


if __name__ == '__main__':
    sys.exit(main())
