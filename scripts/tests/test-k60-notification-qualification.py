#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
# Copyright (c) 2026, UniXNU contributors.
"""Offline capture-qualification regressions; no device, build or real captures.

Synthetic frames below exercise validation only. They are not measured K60 ACK
values and must never be used as hardware qualification evidence.
Run: python3 -B scripts/tests/test-k60-notification-qualification.py
"""
import hashlib
from pathlib import Path
import runpy
import struct
import sys
import unittest

sys.dont_write_bytecode = True
BUILDER = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                            'build-k60-physical-battery.py'))
qualification = BUILDER['qualification']
wire_messages = BUILDER['wire_messages']
OWNER = BUILDER['OWNER']


class Capture:
    """The Path read interface, without filesystem fixture writes."""
    def __init__(self, text):
        self.text = text

    def read_text(self, *, errors):
        assert errors == 'strict'
        return self.text

    def read_bytes(self):
        return self.text.encode('utf-8')

    def __str__(self):
        return '<synthetic-test-capture>'


def frame(kind=2, opcode=4, size=28, owner=OWNER, payload=0):
    return struct.pack('<III', owner, kind, opcode) + bytes([payload]) * (size - 12)


def line(direction, data):
    return '[test] %s data: %s\n' % (direction, data.hex(' '))


def capture(*messages):
    return Capture(''.join(line(direction, data) for direction, data in messages))


class NotificationQualificationTests(unittest.TestCase):
    def qualify(self, fixture):
        return qualification(None, None, fixture)

    def assert_rejected(self, fixture, message=None):
        with self.assertRaisesRegex(ValueError, message or '.'):
            self.qualify(fixture)

    def test_no_capture_preserves_unqualified_defaults(self):
        self.assertEqual(qualification(None, None, None), (0, 0, 0, None, None))

    def test_each_supported_measured_shape_and_capture_hash(self):
        for kind in (1, 2):
            for size in (12, 16, 24, 28):
                with self.subTest(kind=kind, size=size):
                    fixture = capture(('Tx', frame()), ('Rx', frame(kind, size=size)))
                    sign, reply_type, reply_bytes, current, evidence = self.qualify(fixture)
                    self.assertEqual((sign, reply_type, reply_bytes, current),
                                     (0, kind, size, None))
                    self.assertEqual(evidence, dict(capture=str(fixture),
                        sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),
                        type=kind, bytes=size))

    def test_repeated_complete_pairs_with_same_shape(self):
        fixture = capture(*[message for _ in range(3) for message in
                            (('Tx', frame()), ('Rx', frame(1, size=24)))])
        self.assertEqual(self.qualify(fixture)[1:3], (1, 24))

    def test_interleaved_properties_and_notifications_are_not_acks(self):
        fixture = capture(('Tx', frame()),
                          ('Rx', frame(opcode=7, size=16)),
                          ('Tx', frame(1, opcode=0x30, size=24)),
                          ('Rx', frame(1, opcode=0x30, size=24)),
                          ('Rx', frame(2, size=16)))
        self.assertEqual(self.qualify(fixture)[1:3], (2, 16))

    def test_property_request_and_runtime_notification_do_not_qualify(self):
        self.assert_rejected(capture(('Tx', frame(1, opcode=0x30, size=24)),
                                     ('Rx', frame(opcode=7, size=16))), 'unambiguous')

    def test_empty_capture_does_not_qualify(self):
        self.assert_rejected(Capture('ordinary log line\n'), 'unambiguous')

    def test_request_without_reply_is_rejected(self):
        self.assert_rejected(capture(('Tx', frame())), 'unanswered')

    def test_final_unanswered_request_after_valid_pair_is_rejected(self):
        self.assert_rejected(capture(('Tx', frame()), ('Rx', frame()),
                                     ('Tx', frame())), 'unanswered')

    def test_repeated_request_before_reply_is_ambiguous(self):
        self.assert_rejected(capture(('Tx', frame()), ('Tx', frame()),
                                     ('Rx', frame())), 'Repeated')

    def test_reply_before_request_is_rejected_even_if_valid_pair_follows(self):
        self.assert_rejected(capture(('Rx', frame()), ('Tx', frame()),
                                     ('Rx', frame())), 'without a pending')

    def test_duplicate_reply_is_rejected(self):
        self.assert_rejected(capture(('Tx', frame()), ('Rx', frame()),
                                     ('Rx', frame())), 'without a pending')

    def test_invalid_opcode4_request_cannot_be_skipped(self):
        invalid = (frame(1), frame(size=12), frame(size=16), frame(size=24),
                   frame(size=32), frame(payload=1))
        for request in invalid:
            with self.subTest(request=request.hex()):
                self.assert_rejected(capture(('Tx', request), ('Tx', frame()),
                                             ('Rx', frame())), 'subscription request')

    def test_invalid_ack_type_length_or_payload(self):
        invalid = (frame(0), frame(3), frame(size=20), frame(size=32),
                   frame(size=52), frame(size=144), frame(payload=1))
        for reply in invalid:
            with self.subTest(reply=reply.hex()):
                self.assert_rejected(capture(('Tx', frame()), ('Rx', reply)),
                                     'subscription ACK')

    def test_inconsistent_reply_shapes_are_rejected(self):
        for reply in (frame(1), frame(2, size=24)):
            with self.subTest(reply=reply.hex()):
                self.assert_rejected(capture(('Tx', frame()), ('Rx', frame()),
                                             ('Tx', frame()), ('Rx', reply)), 'unambiguous')

    def test_wrong_owner_anywhere_in_capture_is_rejected(self):
        for direction in ('Tx', 'Rx'):
            for opcode in (4, 7):
                with self.subTest(direction=direction, opcode=opcode):
                    self.assert_rejected(capture(('Tx', frame()), ('Rx', frame()),
                        (direction, frame(opcode=opcode, owner=OWNER + 1))), 'owner')

    def test_truncated_frame_anywhere_is_rejected(self):
        for size in (0, 1, 4, 8, 11, 13, 15, 27):
            with self.subTest(size=size):
                broken = frame()[:size]
                self.assert_rejected(capture(('Tx', frame()), ('Rx', frame()),
                                             ('Rx', broken)), 'Malformed|Truncated')

    def test_malformed_hex_cannot_hide_after_a_valid_pair(self):
        valid = line('Tx', frame()) + line('Rx', frame())
        for text in ('', '0', 'gg', '0a 8', '0a80', frame().hex(' ') + ' zz',
                     frame().hex(' ') + ' 0', frame().hex(' ') + ' # truncated'):
            with self.subTest(text=text):
                self.assert_rejected(Capture(valid + 'Rx data: ' + text + '\n'), 'Malformed')

    def test_logging_prefixes_whitespace_and_uppercase_hex(self):
        fixture = Capture('unrelated diagnostic\n' +
            '[1.25] battery: Tx data:	' + frame().hex(' ').upper() + '  \n' +
            'battery: Rx data: ' + frame(1, size=12).hex(' ').upper() + '\t\n')
        self.assertEqual(self.qualify(fixture)[1:3], (1, 12))

    def test_crlf_and_no_final_newline_are_supported(self):
        text = line('Tx', frame()) + line('Rx', frame(1, size=16))
        for variant in (text.replace('\n', '\r\n'), text.rstrip('\n')):
            with self.subTest(text=repr(variant)):
                self.assertEqual(self.qualify(Capture(variant))[1:3], (1, 16))

    def test_legacy_current_capture_parsing_remains_unchanged(self):
        fixture = Capture('Rx data: not-hex\n' +
                          line('Rx', frame(owner=OWNER + 1)) +
                          line('Rx', frame()[:8]) + line('Rx', frame()))
        self.assertEqual(wire_messages(fixture), [('Rx', frame())])

    def test_current_polarity_still_requires_both_capture_directions(self):
        def current_capture(status, current):
            def property_frame(prop, value, response):
                tail = (prop, value & 0xffffffff, 0) if response else (0, prop, 0)
                return struct.pack('<6I', OWNER, 1, 0x30, *tail)
            return capture(('Tx', property_frame(0, 0, False)),
                           ('Rx', property_frame(0, status, True)),
                           ('Tx', property_frame(9, 0, False)),
                           ('Rx', property_frame(9, current, True)))
        charging, draining = current_capture(1, 100000), current_capture(2, -200000)
        result = qualification(charging, draining, None)
        self.assertEqual(result[:3], (1, 0, 0))
        self.assertIsNone(result[4])
        with self.assertRaisesRegex(ValueError, 'both'):
            qualification(charging, None, None)


if __name__ == '__main__':
    unittest.main()
