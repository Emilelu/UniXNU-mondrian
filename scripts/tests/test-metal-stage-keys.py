#!/usr/bin/env python3
"""The staged bundle must carry the keys before the blob generator sees it."""
import pathlib
import subprocess
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
STAGE = REPO / 'scripts' / 'stage-metal-plugin.sh'

PLIST = b'''<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
\t<key>CFBundleExecutable</key><string>PongAdrenoMetal</string>
\t<key>NSPrincipalClass</key><string>PongAdrenoMetalDevice</string>
</dict>
</plist>
'''


class StagedPluginKeys(unittest.TestCase):
    def stage(self, plist: bytes) -> pathlib.Path:
        tmp = pathlib.Path(tempfile.mkdtemp())
        src = tmp / 'src'
        bundle = src / 'PongAdrenoMetal.bundle'
        bundle.mkdir(parents=True)
        (bundle / 'Info.plist').write_bytes(plist)
        for name in ('PongAdrenoMetal', 'PongMetalBridge.dylib', 'libvulkan_freedreno.dylib'):
            (bundle / name).write_bytes(b'\0' * 8)
        (src / 'PongAdrenoMetal.clients').write_bytes(b'backboardd\n')
        (src / 'PongAdrenoMetal.publish').write_bytes(b'1\n')
        dest = tmp / 'dest'
        subprocess.run(['bash', str(STAGE), str(src), str(dest)],
                       check=True, capture_output=True)
        return dest

    def test_staging_adds_the_keys(self):
        dest = self.stage(PLIST)
        text = (dest / 'Info.plist').read_bytes().decode()
        self.assertIn('<key>MetalPluginName</key><string>PongAdrenoMetal</string>', text)
        self.assertIn('<key>MetalPluginClassName</key><string>PongAdrenoMetalDevice</string>', text)

    def test_staging_is_idempotent(self):
        first = self.stage(PLIST) / 'Info.plist'
        text = first.read_bytes()
        staged_twice = self.stage(text) / 'Info.plist'
        self.assertEqual(staged_twice.read_bytes().count(b'MetalPluginName'), 1)

    def test_staging_keeps_six_files(self):
        dest = self.stage(PLIST)
        self.assertEqual(len(list(dest.iterdir())), 6)


if __name__ == '__main__':
    unittest.main(verbosity=2)
