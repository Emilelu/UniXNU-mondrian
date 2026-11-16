#!/usr/bin/env python3
"""The Metal seed markers must land where the plugin looks for them.

PongMetalPlugin.mm formats "%s/PongAdrenoMetal.publish" with the addons directory,
and 0610 creates /private/var/ngpu/addons. A bare marker name therefore lands one
level too high, the plugin never publishes, and the userland Metal device stays nil
(measured: usblog-20261117-000745 published on the kernel side, fallback 18 times).
"""

import io
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
GENERATOR = os.path.join(ROOT, 'scripts', 'gen-k60-metal-blob.py')
PLUGIN = os.path.join(ROOT, 'drivers', 'PongMetal', 'PongMetalPlugin.mm')
DEPLOY = os.path.join(ROOT, 'patches', 'xnu', '0610-k60-metal-plugin-deploy.patch')

SEEDS = re.compile(r"\('([^']*PongAdrenoMetal\.(?:clients|publish))',\s*0o\d+\)")


class MetalSeedPathTest(unittest.TestCase):
    def setUp(self):
        self.generator = io.open(GENERATOR, encoding='utf-8').read()
        self.plugin = io.open(PLUGIN, encoding='utf-8').read()
        self.deploy = io.open(DEPLOY, encoding='utf-8').read()

    def test_the_generator_embeds_every_marker_under_addons(self):
        names = SEEDS.findall(self.generator)
        self.assertEqual(len(names), 2, names)
        for name in names:
            self.assertTrue(name.startswith('addons/'),
                            'marker %r must be relative to the addons directory' % name)

    def test_the_plugin_reads_the_marker_from_the_addons_directory(self):
        self.assertIn('"%s/PongAdrenoMetal.publish"', self.plugin)

    def test_the_deploy_patch_creates_the_addons_directory(self):
        self.assertIn('K60_METAL_ROOT "/addons"', self.deploy)

    def test_the_generator_resolves_sources_without_the_prefix(self):
        # The staged build writes the markers at the top level, so the embedded
        # name may carry addons/ but the source path must not.
        self.assertIn('.replace("addons/", "")', self.generator)


if __name__ == '__main__':
    unittest.main(verbosity=2)
