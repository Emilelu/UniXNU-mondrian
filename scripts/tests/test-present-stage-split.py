#!/usr/bin/env python3
"""The scanout copy is split into encode, submit and GPU wait (official gpu porting guide).

The guide asks a slow frame to be attributed to a stage instead of guessed at: "提交到 GPU 完成"
is a different owner from "运行时 commit 到提交". A single `copy=` number cannot tell them apart,
so the presenter records the three spans separately and the report prints all three.

This guard pins the shape: the three clocks must bracket exactly the calls they claim to, the
report must print them, and the copy itself must keep both pitch branches.
"""
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PRESENTER = os.path.join(REPO, 'drivers', 'PongMetal', 'GpuScanoutPresenter.h')
SCANOUT = os.path.join(REPO, 'drivers', 'PongMetal', 'PongMetalScanout.h')

FAILED = []


def check(name, ok, detail=''):
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

    check('the microsecond helper exists once',
          presenter.count('inline uint64_t _k60Us(') == 1,
          'found %d' % presenter.count('inline uint64_t _k60Us('))
    check('the helper treats the nanosecond field as a difference',
          '/ 1000u;' in presenter and '(b.tv_nsec - a.tv_nsec)' in presenter,
          'the helper must divide a nanosecond difference, not an absolute value')

    body = presenter[presenter.find('Result present(const Frame &frame)'):]
    ok, missing = order(body, [
        'clock_gettime(CLOCK_MONOTONIC,&e0)',
        'id<MTLCommandBuffer> commands = [queue_ commandBuffer];',
        '[blit endEncoding];',
        'clock_gettime(CLOCK_MONOTONIC,&e1)',
        '[commands commit];',
        'clock_gettime(CLOCK_MONOTONIC,&e2)',
        '[commands waitUntilCompleted];',
        'clock_gettime(CLOCK_MONOTONIC,&e3)',
    ])
    check('the four clocks bracket the calls they name', ok, 'missing %r' % missing)

    check('e1 and e2 are derived, not copied',
          'lastEncodeUs_=_k60Us(e0,e1);' in body and 'lastSubmitUs_=_k60Us(e1,e2);' in body
          and 'lastWaitUs_=_k60Us(e2,e3);' in body,
          'each span must come from its own pair of clocks')

    for name in ('encodeMicroseconds', 'submitMicroseconds', 'waitMicroseconds'):
        check('the presenter exposes %s()' % name,
              re.search(r'uint64_t %s\(\) const \{ return last\w+Us_; \}' % name, presenter) is not None)

    check('the report prints encode, submit and gpu in that order',
          order(scanout, ['encode=%llu us submit=%llu us gpu=%llu us'])[0],
          'the three fields must be adjacent and in stage order')
    ok, missing = order(scanout, [
        'context->presenter->importMicroseconds()',
        'context->presenter->encodeMicroseconds()',
        'context->presenter->submitMicroseconds()',
        'context->presenter->waitMicroseconds()',
    ])
    check('the report passes the three accessors in the same order', ok, 'missing %r' % missing)
    check('the report buffer is large enough for the extra fields',
          'char rate[448]' in scanout,
          'three more fields do not fit in the old 320 byte buffer')

    check('the equal pitch path is still one run',
          'copyFromBuffer:source sourceOffset:0 toBuffer:target_ destinationOffset:0 size:frame.stride * (frame.height - 1) + row' in presenter,
          'the fast path must not have been replaced by a loop')
    check('the differing pitch path still exists',
          'copyFromTexture:texture sourceSlice:0 sourceLevel:0' in presenter,
          'the texture path is what carries a pitch change')
    check('the copy is still waited for', '[commands waitUntilCompleted];' in presenter,
          'an unwaiting present would report frames the GPU never retired')

    print('TESTS %s %d case(s) (%d failure(s))'
          % ('OK' if not FAILED else 'FAILED', 13, len(FAILED)))
    return 0 if not FAILED else 1


if __name__ == '__main__':
    sys.exit(main())
