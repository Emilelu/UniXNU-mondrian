#!/usr/bin/env python3
"""Guard: the K60 open trace must never dereference the namei name pointer.

`open1()` prints a diagnostic when `vn_open_auth` returns EACCES. On that path the
namei buffer can already be recycled, so `printf("... path=%s",
ndp->ni_cnd.cn_nameptr)` faulted the kernel:

    K60KEXC msg=Kernel data abort. pc=0xfffffff0072f9ed8 far=0xfffffff14d513c27 esr=0x96000007
    _vprintf_internal+0xd50 <- _printf+0x24 <- _open1+0x200 <- _open1at+0xb4 <- _openat_nocancel+0xe8
    (E:/k60-work/evidence/usblog-20261116-232947/console.log, 2026-11-16 23:29)

The trace may print `cn_namelen` (an integer) but never the string. This test pins
that in the patch that carries the trace, so a later edit cannot reintroduce it.
"""

import io
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PATCH = os.environ.get('K60_OPEN_TRACE_PATCH') or os.path.join(
    HERE, '..', '..', 'patches', 'xnu', '0399-k60-shared-cache-root-layout.patch')


def added_lines(text):
    return [line for line in text.splitlines() if line.startswith('+') and not line.startswith('+++')]


class OpenTraceTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.exists(PATCH), 'missing %s' % PATCH)
        self.text = io.open(PATCH, encoding='utf-8').read()
        self.added = added_lines(self.text)

    def test_the_trace_is_still_present(self):
        joined = '\n'.join(self.added)
        self.assertIn('K60POPEN err=13', joined)

    @staticmethod
    def _code_lines(lines):
        """Only real code: a comment may name the field to explain the hazard."""
        out = []
        for line in lines:
            body = line[1:].strip()
            if body.startswith('*') or body.startswith('/*') or body.startswith('//'):
                continue
            out.append(line)
        return out

    def test_the_trace_does_not_format_the_name_pointer(self):
        for line in self._code_lines(self.added):
            self.assertNotIn('cn_nameptr', line,
                             'the open trace may not touch cn_nameptr: %r' % line)

    def test_the_trace_has_no_path_format_specifier(self):
        block = '\n'.join(self._code_lines(self.added))
        self.assertNotIn('path=%s', block,
                         'path=%s reintroduces the recycled-pointer read')

    def test_the_trace_reports_the_name_length_instead(self):
        block = '\n'.join(self.added)
        self.assertIn('namelen=%u', block)
        self.assertIn('cn_namelen', block)


if __name__ == '__main__':
    unittest.main(verbosity=2)
