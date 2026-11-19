#!/usr/bin/env python3
"""The frame rate argument needs a stage breakdown, not a total.

The porting guide's frame-path table separates page preparation, the render
server taking the offer, and the GPU copy that retires it. A single "it is slow"
number cannot say which of the three to fix, so both sides of the offer have to
report their own stages. This test pins that: the kernel reports prepare and
offer_and_copy, the render server reports wait, copy and done, and neither
report is unconditional.
"""

import pathlib
import re
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
KERNEL = REPO / 'drivers/PongAdreno/PongAdrenoScanout.cpp'
SERVER = REPO / 'drivers/PongMetal/PongMetalScanout.h'


class FrameStageTiming(unittest.TestCase):
    def test_the_kernel_reports_page_preparation_and_the_copy_separately(self):
        text = KERNEL.read_text(encoding='utf-8')
        self.assertIn('prepare=%llu us offer_and_copy=%llu us', text,
                      'the kernel must name page preparation and the copy apart')
        self.assertIn('absolutetime_to_nanoseconds(prepared - began'.replace(' ', ''), text.replace(' ', ''),
                      'the preparation number has to come from a real clock read')

    def test_the_kernel_takes_the_stamps_around_the_real_work(self):
        text = KERNEL.read_text(encoding='utf-8')
        prepare = text.index('const uint64_t prepared')
        finish = text.index('const uint64_t finished')
        call = text.index('memory->prepare()')
        offer = text.index('pending={true,false,false,++sequence')
        self.assertLess(call, prepare, 'prepare() must be inside the preparation stage')
        self.assertLess(prepare, offer, 'the offer starts after preparation ends')
        self.assertLess(offer, finish, 'the copy ends after the offer was posted')

    def test_the_render_server_reports_its_three_stages(self):
        text = SERVER.read_text(encoding='utf-8')
        self.assertIn('wait=%llu us copy=%llu us done=%llu us', text,
                      'the render server must report wait, copy and retire')
        for stamp in ('struct timespec t0={},t1={},t2={};', 'struct timespec t3={};'):
            self.assertIn(stamp, text, 'both sides of the copy need a clock read')

    def test_the_copy_numbers_come_from_the_present_call(self):
        text = SERVER.read_text(encoding='utf-8')
        present = text.index('context->presenter->present(')
        after = text.index('clock_gettime(CLOCK_MONOTONIC,&t2);')
        before = text.index('clock_gettime(CLOCK_MONOTONIC,&t1);')
        self.assertLess(before, present, 'the copy stage starts before present()')
        self.assertLess(present, after, 'the copy stage ends after present()')
        self.assertIn('lastCopy=span(t1,t2);', text,
                      'the copy number must be t2 - t1 through the tested helper, not a guess')
        self.assertIn('lastWait=span(t0,t1);', text, 'the wait number must be t1 - t0')
        self.assertIn('lastDone=span(t2,t3);', text, 'the retire number must be t3 - t2')

    def test_neither_report_is_unconditional(self):
        kernel = KERNEL.read_text(encoding='utf-8')
        server = SERVER.read_text(encoding='utf-8')
        self.assertRegex(kernel, r'if\(ok && \(completed<=4 \|\| !\(completed%60\)\)\)',
                         'the kernel report must be sampled, not每帧')
        self.assertIn('if(copies<=8 || !(copies%10))', server,
                      'the stage line must be sampled early: a 60-frame cadence '
                      'produced zero samples in the 2026-11-18 flight')

    def test_the_report_fits_its_buffer(self):
        kernel = KERNEL.read_text(encoding='utf-8')
        server = SERVER.read_text(encoding='utf-8')
        self.assertIn('snprintf(text,sizeof(text)', kernel,
                      'the kernel report must be bounded by its own buffer')
        self.assertIn('snprintf(rate,sizeof(rate)', server,
                      'the render server report must be bounded by its own buffer')

    def test_a_missing_clock_read_does_not_become_a_stage(self):
        """A failed clock_gettime leaves a zeroed timespec; that is not a span."""
        text = SERVER.read_text(encoding='utf-8')
        self.assertIn('#include "PongScanoutTiming.h"', text,
                      'the render server must use the host-tested arithmetic')
        self.assertIn('return stamped(from) && stamped(to) ? elapsedUs(from,to) : 0;', text,
                      'stage spans must be suppressed when either clock was not read')


if __name__ == '__main__':
    unittest.main(verbosity=2)
