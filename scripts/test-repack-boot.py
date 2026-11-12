#!/usr/bin/env python3
"""Exercise Android v4 repacking with the offsets used by the bootloader."""
import gzip
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib


REPACK = Path(__file__).with_name('repack-boot.py')


class RepackBootTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix='k60-repack-test-')
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.firmware = bytes(range(256)) * 19
        self.dtb = struct.pack('>10I', 0xd00dfeed, 40, 40, 40, 40, 17, 16, 0, 0, 0)
        self.kernel = gzip.compress(self.firmware, mtime=0) + self.dtb
        self.header = bytearray(4096)
        self.header[:8] = b'ANDROID!'
        struct.pack_into('<4I', self.header, 8, len(self.kernel), 4700, 0x12345678, 1584)
        struct.pack_into('<I', self.header, 40, 4)
        struct.pack_into('<I', self.header, 1580, 4096)
        self.header[1584:1600] = b'kept-header-page'
        self.original = (bytes(self.header) + self.kernel.ljust(4096, b'\0') +
                         (b'original payload' * 294)[:4700].ljust(8192, b'\0') + b'\0' * 4096)
        self.template = self.root / 'template.img'
        self.template.write_bytes(self.original)
        self.payload = self.root / 'payload.img'
        self.payload.write_bytes(b'new payload' * 819)
        self.output = self.root / 'repacked.img'

    def run_repack(self, *options):
        return subprocess.run([sys.executable, str(REPACK), '--template', str(self.template),
                               '--ramdisk', str(self.payload), '--output', str(self.output),
                               *options], capture_output=True, text=True, timeout=20)

    def test_replacement_keeps_firmware_and_v4_page_offsets(self):
        result = self.run_repack()
        self.assertEqual(result.returncode, 0, result.stderr)
        image = self.output.read_bytes()
        expected_header = bytearray(self.header)
        struct.pack_into('<I', expected_header, 12, self.payload.stat().st_size)
        self.assertEqual(image[:4096], expected_header)
        self.assertEqual(image[4096:4096 + len(self.kernel)], self.kernel)
        decoder = zlib.decompressobj(31)
        self.assertEqual(decoder.decompress(image[4096:4096 + len(self.kernel)]), self.firmware)
        self.assertTrue(decoder.eof)
        self.assertEqual(decoder.unused_data, self.dtb)
        self.assertEqual(image[8192:8192 + self.payload.stat().st_size], self.payload.read_bytes())
        self.assertEqual(len(image), 8192 + 12288 + 4096)
        self.assertEqual(image[8192 + 12288:], b'\0' * 4096)

    def test_corrupt_firmware_is_rejected_before_output(self):
        corrupted = bytearray(self.original)
        corrupted[4096 + len(self.kernel) - len(self.dtb) - 8] ^= 1
        self.template.write_bytes(corrupted)
        result = self.run_repack()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('invalid compressed firmware', result.stderr)
        self.assertFalse(self.output.exists())

    def test_truncated_signature_is_rejected_before_output(self):
        self.template.write_bytes(self.original[:-1])
        result = self.run_repack()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('truncated sections', result.stderr)
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
