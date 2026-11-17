#!/usr/bin/env python3
"""The deployed bundle must declare the two keys Metal reads.

Measured 2026-11-17: the plugin was loaded by dyld (constructor ran) and never
instantiated, because the built Info.plist only declared NSPrincipalClass.
This test parses the blob the kernel will deploy and asserts the keys are there.
"""
import importlib.util
import pathlib
import struct
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
GENERATOR = REPO / 'scripts' / 'gen-k60-metal-blob.py'

HEADER = struct.Struct('<4sI')
ENTRY = struct.Struct('<HII')

PLIST_NO_KEYS = b'''<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
\t<key>CFBundleExecutable</key><string>PongAdrenoMetal</string>
\t<key>NSPrincipalClass</key><string>PongAdrenoMetalDevice</string>
</dict>
</plist>
'''

PLIST_WITH_KEYS = b'''<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
\t<key>MetalPluginClassName</key><string>PongAdrenoMetalDevice</string>
\t<key>MetalPluginName</key><string>PongAdrenoMetal</string>
</dict>
</plist>
'''


def load_generator():
    spec = importlib.util.spec_from_file_location('gen_k60_metal_blob', GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse(blob: bytes) -> dict:
    magic, count = HEADER.unpack_from(blob, 0)
    assert magic == b'K60M', magic
    entries = [ENTRY.unpack_from(blob, HEADER.size + i * ENTRY.size) for i in range(count)]
    names_start = HEADER.size + count * ENTRY.size
    out = {}
    for name_len, size, offset in entries:
        name = blob[names_start:names_start + name_len].decode()
        names_start += name_len
        out[name] = blob[offset:offset + size]
    return out


class MetalBlobInfoPlist(unittest.TestCase):
    def build(self, plist: bytes) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / 'Info.plist').write_bytes(plist)
            for name in ('PongAdrenoMetal', 'PongMetalBridge.dylib', 'libvulkan_freedreno.dylib'):
                (root / name).write_bytes(b'\0' * 16)
            (root / 'PongAdrenoMetal.clients').write_bytes(b'backboardd\n')
            module = load_generator()
            return parse(module.build(root, publish=True))

    def test_the_keys_are_added_when_missing(self):
        files = self.build(PLIST_NO_KEYS)
        plist = files['addons/PongAdrenoMetal.bundle/Info.plist'].decode()
        self.assertIn('<key>MetalPluginName</key><string>PongAdrenoMetal</string>', plist)
        self.assertIn('<key>MetalPluginClassName</key><string>PongAdrenoMetalDevice</string>', plist)
        self.assertTrue(plist.rstrip().endswith('</plist>'))

    def test_an_existing_key_is_not_duplicated(self):
        files = self.build(PLIST_WITH_KEYS)
        plist = files['addons/PongAdrenoMetal.bundle/Info.plist'].decode()
        self.assertEqual(plist.count('MetalPluginName'), 1)
        self.assertEqual(plist.count('MetalPluginClassName'), 1)

    def test_the_other_bundle_files_still_ship(self):
        files = self.build(PLIST_NO_KEYS)
        for name in ('addons/PongAdrenoMetal.bundle/PongAdrenoMetal',
                     'addons/PongAdrenoMetal.bundle/PongMetalBridge.dylib',
                     'addons/PongAdrenoMetal.clients',
                     'addons/PongAdrenoMetal.publish'):
            self.assertIn(name, files)


if __name__ == '__main__':
    unittest.main(verbosity=2)
