#!/usr/bin/env python3
"""Execute the scanout stage arithmetic instead of matching its text.

Two authoring mistakes in this file's history both produced plausible numbers:

  * `(uint64_t)(b.tv_nsec - a.tv_nsec)` on a span that crosses a whole second.
    The negative difference wrapped, so a 17 ms copy was reported as ~1.8e13 us.
    Nothing looked broken; the criterion comparing the stages against the outer
    copy could simply never pass.
  * Dividing the seconds and nanoseconds fields separately, which mis-rounds a
    cross-second sub-microsecond span by a microsecond.

Neither is visible in a source assertion, so this test compiles
drivers/PongMetal/PongScanoutTiming.h with the host compiler and runs real cases
through it. A host compiler is required, the same way
scripts/tests/test-k60-handoff-integration.py requires one for its call-site
assertions: a text match would pass on the broken arithmetic.
"""
import pathlib
import shutil
import subprocess
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[2]
HEADER = REPO / 'drivers/PongMetal/PongScanoutTiming.h'

FIXTURE = r'''
#include <cstdint>
#include <cstdio>
#include <ctime>
#include "PongScanoutTiming.h"

static unsigned failures;

static struct timespec at(time_t seconds, long nanoseconds)
{
    struct timespec value;
    value.tv_sec = seconds;
    value.tv_nsec = nanoseconds;
    return value;
}

static void expect(const char *what, uint64_t actual, uint64_t wanted)
{
    if (actual != wanted) {
        std::printf("FAIL %s: got %llu wanted %llu\n", what,
                    (unsigned long long)actual, (unsigned long long)wanted);
        ++failures;
    }
}

int main()
{
    using pongscanout::absoluteUs;
    using pongscanout::elapsedUs;
    using pongscanout::stamped;

    /* The historical bug: 2 ns across a second boundary must not wrap. */
    expect("cross-second sub-microsecond", elapsedUs(at(1, 999999999), at(2, 1)), 0);
    /* Ordinary sub-second advances. */
    expect("sub-microsecond", elapsedUs(at(0, 500), at(0, 1500)), 1);
    expect("half a second", elapsedUs(at(5, 0), at(5, 500000000)), 500000);
    /* The borrow case: exactly 200 ms across a second boundary. */
    expect("cross-second 200ms", elapsedUs(at(1, 900000000), at(2, 100000000)), 200000);
    /* The second historical bug: separate divisions gave 1 us too many here. */
    expect("cross-second 17ms", elapsedUs(at(100, 999000000), at(101, 16000000)), 17000);
    /* A backwards clock reports nothing rather than a huge positive number. */
    expect("reversed", elapsedUs(at(5, 0), at(4, 0)), 0);
    expect("identical", elapsedUs(at(0, 0), at(0, 0)), 0);
    /* Whole seconds keep their microseconds. */
    expect("whole seconds", elapsedUs(at(7, 250000), at(10, 750000)), 3000500);

    if (stamped(at(0, 0))) { std::printf("FAIL a zeroed stamp is not a reading\n"); ++failures; }
    if (!stamped(at(0, 1))) { std::printf("FAIL a real stamp must be recognised\n"); ++failures; }
    expect("absolute", absoluteUs(at(3, 500000)), 3000500);

    if (!failures) std::printf("ALL OK\n");
    return failures ? 1 : 0;
}
'''


def main():
    if not HEADER.is_file():
        raise SystemExit('missing %s' % HEADER)
    text = HEADER.read_text(encoding='utf-8')
    for needle in ('nanoseconds += 1000000000LL;', 'if (seconds < 0) return 0;'):
        if needle not in text:
            raise SystemExit('the helper lost its borrow or its guard: %r' % needle)
    if '(uint64_t)(b.tv_sec - a.tv_sec)' in text:
        raise SystemExit('the wrapped-difference form is back')

    compiler = shutil.which('c++') or shutil.which('clang++')
    if not compiler:
        raise SystemExit('a host C++ compiler is required for the timing assertions')

    with tempfile.TemporaryDirectory() as work:
        source = pathlib.Path(work) / 'timing.cpp'
        binary = pathlib.Path(work) / 'timing'
        source.write_text(FIXTURE, encoding='utf-8')
        build = subprocess.run(
            [compiler, '-std=c++17', '-O1', '-Wall', '-Wextra', '-Werror',
             '-I', str(HEADER.parent), str(source), '-o', str(binary)],
            capture_output=True, text=True)
        if build.returncode:
            raise SystemExit('the timing header does not compile:\n%s%s'
                             % (build.stdout, build.stderr))
        run = subprocess.run([str(binary)], capture_output=True, text=True)
        if run.returncode or 'ALL OK' not in run.stdout:
            raise SystemExit('the timing assertions failed:\n%s%s'
                             % (run.stdout, run.stderr))
    print('TESTS OK 11 case(s) (0 failure(s))')


if __name__ == '__main__':
    main()
