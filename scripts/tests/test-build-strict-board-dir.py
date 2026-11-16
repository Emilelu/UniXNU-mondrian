#!/usr/bin/env python3
"""P-225: build-strict.sh must pick the board directory that changes the kernel.

M drives .config, kernel.macho, payload.img, hardware.dtb and the metal blob.
Two board dirs can sit under one OUT (out-wifi has mondrian/ and
mondrian_wifi/), and mondrian_wifi/.config names neither
CONFIG_XNU_GPU_ADDON nor CONFIG_XNU_K60_PHYSICAL_BATTERY.  Both reads in
build-strict.sh are `sed -n 's/^KEY=y$/1/p'`, so picking the wrong directory
silently drops the Metal plugin and the battery archive and the build still
reports success (P-202).

The test runs the shipped board_dir() against synthetic OUT trees.
"""

import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
BUILD_STRICT = os.path.join(REPO, 'scripts', 'build-strict.sh')

FULL = 'CONFIG_XNU_GPU_ADDON=y\nCONFIG_XNU_K60_PHYSICAL_BATTERY=y\nCONFIG_XNU_WIFI=y\n'
PARTIAL = 'CONFIG_XNU_WIFI=y\nCONFIG_XNU_TOUCH=y\n'


def board_dir_source():
    with open(BUILD_STRICT, encoding='utf-8') as handle:
        lines = handle.read().split('\n')
    start = None
    for index, line in enumerate(lines):
        if line.startswith('board_dir() {'):
            start = index
            break
    if start is None:
        raise AssertionError('build-strict.sh has no board_dir()')
    depth = 0
    for index in range(start, len(lines)):
        depth += lines[index].count('{') - lines[index].count('}')
        if depth == 0:
            return '\n'.join(lines[start:index + 1])
    raise AssertionError('board_dir() is not closed')


def make_board(out, name, config, mtime=None):
    path = os.path.join(out, 'mondrian', 'ipados-16.6.1-20G81', name)
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, '.config'), 'w', encoding='utf-8') as handle:
        handle.write(config)
    if mtime is not None:
        os.utime(os.path.join(path, '.config'), (mtime, mtime))
    return path


def run_board_dir(out, override=None):
    script = (
        'die() { echo "DIE: $*"; exit 9; }\n'
        + board_dir_source()
        + '\nboard_dir\n'
    )
    env = dict(os.environ)
    env['OUT'] = out
    env.pop('K60_BOARD_DIR', None)
    if override:
        env['K60_BOARD_DIR'] = override
    result = subprocess.run(['bash', '-c', script], capture_output=True,
                            text=True, env=env)
    return result


class BoardDirTest(unittest.TestCase):
    def setUp(self):
        self.out = tempfile.mkdtemp(prefix='k60-board-')

    def tearDown(self):
        shutil.rmtree(self.out, ignore_errors=True)

    def test_a_full_config_beats_a_newer_partial_one(self):
        """The regression: newest-wins would pick the partial config here."""
        make_board(self.out, 'mondrian', FULL, mtime=1_700_000_000)
        make_board(self.out, 'mondrian_wifi', PARTIAL, mtime=1_800_000_000)
        result = run_board_dir(self.out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.strip().endswith('/mondrian'),
                        'picked %r, expected the config that names the keys'
                        % result.stdout.strip())

    def test_two_full_configs_fall_back_to_newest(self):
        """Among equals, age is the tiebreak."""
        make_board(self.out, 'mondrian', FULL, mtime=1_700_000_000)
        make_board(self.out, 'mondrian_other', FULL, mtime=1_800_000_000)
        result = run_board_dir(self.out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.strip().endswith('/mondrian_other'),
                        result.stdout.strip())

    def test_a_single_board_is_returned_unchanged(self):
        make_board(self.out, 'mondrian', PARTIAL)
        result = run_board_dir(self.out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.strip().endswith('/mondrian'))

    def test_the_override_wins_outright(self):
        make_board(self.out, 'mondrian', FULL, mtime=1_800_000_000)
        partial = make_board(self.out, 'mondrian_wifi', PARTIAL, mtime=1_700_000_000)
        result = run_board_dir(self.out, override=partial)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), partial)

    def test_an_override_without_a_config_fails_loudly(self):
        make_board(self.out, 'mondrian', FULL)
        missing = os.path.join(self.out, 'nowhere')
        result = run_board_dir(self.out, override=missing)
        self.assertNotEqual(result.returncode, 0,
                            'a missing override must not be silently ignored')
        self.assertIn('K60_BOARD_DIR', result.stdout + result.stderr)

    def test_the_empty_out_falls_back_to_the_default_path(self):
        """First build: no board dir yet, so name the default instead of dying."""
        result = run_board_dir(self.out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.strip().endswith('/mondrian'),
                        result.stdout.strip())

    def test_two_partial_configs_warn_about_the_lost_features(self):
        """Neither candidate names the keys: say so, do not just pick one."""
        make_board(self.out, 'mondrian', PARTIAL, mtime=1_700_000_000)
        make_board(self.out, 'mondrian_wifi', PARTIAL, mtime=1_800_000_000)
        result = run_board_dir(self.out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('P-202', result.stderr,
                      'a pick that drops the Metal plugin and battery archive '
                      'must say so: %r' % result.stderr)

    def test_more_than_one_candidate_is_announced(self):
        make_board(self.out, 'mondrian', FULL, mtime=1_700_000_000)
        make_board(self.out, 'mondrian_wifi', PARTIAL, mtime=1_800_000_000)
        result = run_board_dir(self.out)
        self.assertIn('K60_BOARD_DIR', result.stderr,
                      'the choice must name the override that settles it')


if __name__ == '__main__':
    unittest.main(verbosity=2)
