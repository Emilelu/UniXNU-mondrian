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
        self.assertIn('lastCopy=uint64_t(t2.tv_sec-t1.tv_sec)', text,
                      'the copy number must be t2 - t1, not a guess')

    def test_neither_report_is_unconditional(self):
        kernel = KERNEL.read_text(encoding='utf-8')
        server = SERVER.read_text(encoding='utf-8')
        self.assertRegex(kernel, r'if\(ok && \(completed<=4 \|\| !\(completed%60\)\)\)',
                         'the kernel report must be sampled, not每帧')
        self.assertIn('if(!(copies%60))', server,
                      'the render server report must stay on its 60-frame cadence')

    def test_the_report_fits_its_buffer(self):
        kernel = KERNEL.read_text(encoding='utf-8')
        server = SERVER.read_text(encoding='utf-8')
        self.assertIn('snprintf(text,sizeof(text)', kernel,
                      'the kernel report must be bounded by its own buffer')
        self.assertIn('snprintf(rate,sizeof(rate)', server,
                      'the render server report must be bounded by its own buffer')


if __name__ == '__main__':
    unittest.main(verbosity=2)
