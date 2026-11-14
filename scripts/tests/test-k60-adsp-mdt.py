#!/usr/bin/env python3
"""Pure ELF32LE MDT preparation tests. No SMC, physical memory or device.
--output is a durable test directory; --firmware adds captured split-image checks.
"""
import argparse
import ctypes as C
import hashlib
from pathlib import Path
import struct
import subprocess
import unittest

REPO = Path(__file__).resolve().parents[2]
MAX = 64
RELOC = 1 << 27
HASH = 2 << 24
class Segment(C.Structure):
    _fields_ = [(n, C.c_uint32) for n in ('index', 'flags', 'file_offset',
        'link_address', 'copy_bytes', 'zero_bytes', 'source_is_piece')] + [('destination', C.c_uint64)]
class Plan(C.Structure):
    _fields_ = [(n, C.c_uint32) for n in ('headers', 'count', 'hash_index', 'relocatable',
        'prefix_bytes', 'hash_bytes')] + [(n, C.c_uint64) for n in
        ('link_base', 'span', 'region_base', 'region_bytes')] + [('segment', Segment * MAX)]
Piece = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_uint32, C.POINTER(C.c_void_p), C.POINTER(C.c_size_t))

def put(data, offset, value, fmt='I'):
    struct.pack_into('<' + fmt, data, offset, value)

def fixture(mode='packed'):
    prefix = 52 + 4 * 32
    image = bytearray(prefix)
    image[:7] = b'\x7fELF\x01\x01\x01'
    for at, value, fmt in [(16, 2, 'H'), (18, 164, 'H'), (20, 1, 'I'),
        (28, 52, 'I'), (40, 52, 'H'), (42, 32, 'H'), (44, 4, 'H')]:
        put(image, at, value, fmt)
    headers = [(0, 0, 0, 0, prefix, 0, 7 << 24, 0),
        (1, 0x1000, 0x100000, 0x100000, 5, 0x1000, RELOC | 5, 0x1000),
        (1, 0x2000, 0x101000, 0x101000, 0, 0x1000, RELOC | 4, 0x1000),
        (0, 0x3000, 0, 0, 16, 16, HASH, 0x1000)]
    for i, h in enumerate(headers):
        struct.pack_into('<8I', image, 52 + 32 * i, *h)
    pieces = {1: b'abcde', 3: bytes(range(16))}
    if mode == 'packed':
        image += pieces[3]
    elif mode == 'contained':
        image += bytes(0x3010 - len(image))
        image[0x1000:0x1005] = pieces[1]
        image[0x3000:0x3010] = pieces[3]
    return image, pieces

class MdtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        OPT.output.mkdir(parents=True, exist_ok=True)
        so = OPT.output / 'libK60AdspMdt.so'
        command = ['cc', '-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
            '-fPIC', '-shared', '-I', str(REPO / 'drivers/PongPower'),
            str(REPO / 'drivers/PongPower/K60AdspMdt.c'), '-o', str(so)]
        subprocess.run(command, check=True)
        cls.lib = C.CDLL(str(so))
        cls.lib.k60_adsp_mdt_prepare.argtypes = [C.c_void_p, C.c_size_t,
            C.c_uint64, C.c_uint64, Piece, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(Plan)]
        cls.lib.k60_adsp_mdt_prepare.restype = C.c_int

    def run_image(self, image, pieces, expected=0, base=0x9fd00000, region=0x2000, capacity=65536):
        keep = []
        calls = []
        def read(_ctx, index, out, length):
            calls.append(index)
            if index not in pieces:
                return -1
            buf = C.create_string_buffer(bytes(pieces[index]))
            keep.append(buf)
            out[0] = C.addressof(buf)
            length[0] = len(pieces[index])
            return 0
        cb = Piece(read)
        source = C.create_string_buffer(bytes(image))
        meta = (C.c_ubyte * 65536)(*[0xa5] * 65536)
        plan = Plan()
        C.memset(C.addressof(plan), 0x5a, C.sizeof(plan))
        rc = self.lib.k60_adsp_mdt_prepare(source, len(image), base, region,
            cb, None, meta, capacity, C.byref(plan))
        self.assertEqual(rc, expected)
        if expected:
            self.assertEqual(bytes(plan), bytes(C.sizeof(plan)))
            self.assertEqual(bytes(meta), bytes([0xa5]) * 65536)
        return plan, bytes(meta), calls

    def test_packed_relocatable(self):
        image, pieces = fixture()
        p, meta, calls = self.run_image(image, pieces)
        self.assertEqual((p.count, p.headers, p.hash_index, p.link_base, p.span), (2, 4, 3, 0x100000, 0x2000))
        self.assertEqual(meta[:len(image)], bytes(image))
        self.assertEqual(calls, [1])  # pure BSS has no piece file
        self.assertEqual((p.segment[0].destination, p.segment[1].destination), (0x9fd00000, 0x9fd01000))
        self.assertEqual((p.segment[0].copy_bytes, p.segment[0].zero_bytes), (5, 4091))
        self.assertEqual(p.segment[1].zero_bytes, 4096)
        self.assertEqual(p.segment[0].flags, RELOC | 5)

    def test_external_hash(self):
        image, pieces = fixture('external')
        p, meta, calls = self.run_image(image, pieces)
        self.assertEqual(calls, [3, 1])
        self.assertEqual(meta[:p.prefix_bytes + p.hash_bytes], bytes(image) + pieces[3])

    def test_contained_monolithic(self):
        image, pieces = fixture('contained')
        p, meta, calls = self.run_image(image, {})
        self.assertEqual(calls, [])
        self.assertEqual(p.segment[0].source_is_piece, 0)
        self.assertEqual(meta[:p.prefix_bytes + 16], bytes(image[:p.prefix_bytes]) + pieces[3])

    def test_fixed_addresses(self):
        image, pieces = fixture()
        for i in (1, 2):
            put(image, 52 + 32*i + 24, 5)
        p, _, _ = self.run_image(image, pieces, base=0x100000)
        self.assertEqual((p.relocatable, p.segment[1].destination), (0, 0x101000))
        self.run_image(image, pieces, expected=-6)

    def test_reject_header_and_format_mutations(self):
        for at, value, fmt, expected in [(0, 0, 'B', -2), (4, 2, 'B', -2),
            (5, 2, 'B', -2), (6, 0, 'B', -2), (16, 1, 'H', -2),
            (18, 183, 'H', -2), (20, 0, 'I', -2), (28, 0xffffffff, 'I', -3),
            (40, 51, 'H', -3), (42, 31, 'H', -3), (44, 0, 'H', -3),
            (44, 65, 'H', -3), (52, 1, 'I', -3), (56, 1, 'I', -3),
            (68, 1, 'I', -3), (68, 0xffffffff, 'I', -3)]:
            with self.subTest(offset=at, value=value):
                image, pieces = fixture()
                put(image, at, value, fmt)
                self.run_image(image, pieces, expected)
        for length in (0, 6, 51, 52, 179):
            image, pieces = fixture()
            self.run_image(image[:length], pieces, -2 if length < 52 else -3)

    def test_reject_hash_and_segments(self):
        cases = [(52+3*32+24, 0, -4), (52+3*32+16, 0, -4),
            (52+2*32+24, HASH, -4), (52+1*32+16, 4097, -5),
            (52+1*32+12, 0xfffff000, -6), (52+1*32+20, 0x2000, -7),
            (52+2*32+24, 4, -5), (52+1*32+28, 3, -6),
            (52+1*32+4, 0xffffffff, -6), (52+2*32+12, 0x100000, -7)]
        for at, value, expected in cases:
            with self.subTest(offset=at, value=value):
                image, pieces = fixture()
                if at == 52+1*32+12:
                    put(image, 52+1*32+20, 0x2000)
                put(image, at, value)
                self.run_image(image, pieces, expected)

    def test_reject_missing_or_wrong_size_piece(self):
        for mode, pieces in [('packed', {}), ('packed', {1: b'abcd'}),
            ('packed', {1: b'abcdef'}), ('external', {1: b'abcde'}),
            ('external', {1: b'abcde', 3: b'x'})]:
            image, _ = fixture(mode)
            self.run_image(image, pieces, -8)

    def test_capacity_and_carveout(self):
        image, pieces = fixture()
        self.run_image(image, pieces, -9, capacity=len(image)-1)
        self.run_image(image, pieces, -6, region=0x1000)
        self.run_image(image, pieces, -1, base=0x9fd00001)
        self.run_image(image, pieces, -1, region=0x2001)
        self.run_image(image, pieces, -1, base=0xfffffffffffff000)
        self.run_image(image, pieces, -1, region=0)

    def test_packed_hash_precedes_declared_offset(self):
        image, pieces = fixture()
        put(image, 52 + 3*32 + 4, 0)
        p, meta, calls = self.run_image(image, pieces)
        self.assertEqual(meta[:p.prefix_bytes + p.hash_bytes], bytes(image))
        self.assertEqual(calls, [1])

    def test_contained_hash_cannot_overlap_prefix(self):
        image, pieces = fixture('contained')
        put(image, 52 + 3*32 + 4, 52)
        self.run_image(image, pieces, -4)

    def test_partial_contained_ranges_use_exact_pieces(self):
        image, pieces = fixture('contained')
        p, meta, calls = self.run_image(image[:-1], pieces)
        self.assertEqual(calls, [3])
        self.assertEqual(meta[:p.prefix_bytes + p.hash_bytes], bytes(image[:p.prefix_bytes]) + pieces[3])
        image, pieces = fixture('contained')
        p, _, calls = self.run_image(image[:0x1002], pieces)
        self.assertEqual(calls, [3, 1])
        self.assertEqual(p.segment[0].source_is_piece, 1)

    def test_address_endpoints_and_adjacent_loads(self):
        image, pieces = fixture()
        for i, address in ((1, 0xffffe000), (2, 0xfffff000)):
            put(image, 52 + i*32 + 12, address)
        p, _, _ = self.run_image(image, pieces, base=0xffffffffffffd000)
        last = p.segment[p.count-1]
        self.assertEqual(last.destination + last.zero_bytes, 0xfffffffffffff000)
        self.assertEqual(p.link_base + p.span, 1 << 32)
        put(image, 52 + 2*32 + 20, 0x1001)
        self.run_image(image, pieces, -6)
        image, pieces = fixture()
        put(image, 52 + 2*32 + 12, 0x100fff)
        self.run_image(image, pieces, -7)

    def test_null_callback_and_invalid_callback_results(self):
        image, pieces = fixture()
        source = C.create_string_buffer(bytes(image))
        meta = (C.c_ubyte * 65536)(*[0xa5] * 65536)
        plan = Plan()
        callbacks = [Piece(), Piece(lambda _c, _i, _p, _n: 1)]
        def null_piece(_c, _i, out, length):
            out[0] = None
            length[0] = 5
            return 0
        callbacks.append(Piece(null_piece))
        for cb in callbacks:
            C.memset(C.addressof(plan), 0x5a, C.sizeof(plan))
            rc = self.lib.k60_adsp_mdt_prepare(source, len(image), 0x9fd00000,
                0x2000, cb, None, meta, len(meta), C.byref(plan))
            self.assertEqual(rc, -8)
            self.assertEqual(bytes(plan), bytes(C.sizeof(plan)))
            self.assertEqual(bytes(meta), bytes([0xa5]) * len(meta))
        for src, destination, output in [(None, meta, C.byref(plan)),
            (source, None, C.byref(plan)), (source, meta, None)]:
            rc = self.lib.k60_adsp_mdt_prepare(src, len(image), 0x9fd00000,
                0x2000, Piece(), None, destination, len(meta), output)
            self.assertEqual(rc, -1)

    def test_maximum_header_table(self):
        image, pieces = fixture('external')
        image += bytes(52 + MAX*32 - len(image))
        put(image, 44, MAX, 'H')
        put(image, 68, len(image))
        p, _, calls = self.run_image(image, pieces)
        self.assertEqual((p.headers, p.count), (64, 2))
        self.assertEqual(calls, [3, 1])

    def test_physical_relocation_does_not_impose_elf_virtual_alignment(self):
        image, pieces = fixture()
        put(image, 52 + 2*32 + 12, 0x101001)
        p, _, _ = self.run_image(image, pieces, region=0x3000)
        self.assertEqual(p.segment[1].destination, 0x9fd01001)
        image, pieces = fixture()
        put(image, 52 + 1*32 + 28, 0x2000)
        put(image, 52 + 1*32 + 8, 0x101000)
        p, _, _ = self.run_image(image, pieces, base=0x9fd01000)
        self.assertEqual(p.segment[0].destination, 0x9fd01000)
        put(image, 52 + 1*32 + 8, 0x100000)
        self.run_image(image, pieces, -6, base=0x9fd01000)

    def test_captured_k60_image(self):
        if not OPT.firmware:
            self.skipTest('captured firmware path not requested')
        root = OPT.firmware
        image = (root / 'adsp.mdt').read_bytes()
        self.assertEqual(hashlib.sha256(image).hexdigest(),
            '1238098817957c4d3cd0995fd413332751ac8082ea315e6e1d9bdb247cadc694')
        pieces = {i: (root / ('adsp.b%02d' % i)).read_bytes()
            for i in range(26) if (root / ('adsp.b%02d' % i)).is_file()}
        p, meta, calls = self.run_image(image, pieces, region=0x3100000)
        self.assertEqual((p.headers, p.count, p.hash_index, p.prefix_bytes, p.hash_bytes), (26, 24, 25, 884, 4520))
        self.assertEqual((p.link_base, p.span, p.relocatable), (0x86300000, 0x3100000, 1))
        self.assertEqual(meta[:5404], image)
        self.assertEqual(image[884:], pieces[25])
        self.assertNotIn(24, calls)
        self.assertEqual(len(calls), 23)
        self.assertEqual(p.segment[0].destination, 0x9fd00000)
        last = p.segment[p.count-1]
        self.assertEqual(last.destination + last.copy_bytes + last.zero_bytes, 0xa2e00000)
        self.assertEqual(last.copy_bytes, 0)
        self.assertEqual(last.zero_bytes, 7245824)
        self.assertTrue(all(p.segment[i].source_is_piece == bool(p.segment[i].copy_bytes) for i in range(p.count)))
        self.run_image(image, pieces, -6, region=0x30ff000)
        print('Captured MDT: 26 headers, 24 loads, metadata 5404, relocated [0x9fd00000,0xa2e00000)')

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', required=True, type=Path)
    ap.add_argument('--firmware', type=Path)
    OPT, rest = ap.parse_known_args()
    unittest.main(argv=[__file__, *rest], verbosity=2)
