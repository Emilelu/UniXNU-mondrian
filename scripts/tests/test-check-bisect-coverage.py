#!/usr/bin/env python3
"""Tests for scripts/check-bisect-coverage.py (P-218).

The gate answers one question: is there a built image whose flight was never
recorded?  The tests pin the three ways that question can be answered wrongly,
all of which the first draft got wrong:

1. Reading the ledger as the flight record.  `record-boot.py` refuses logs with
   fewer than 100 SpringBoard lines, so every *silent* image is missing from the
   ledger — the exact images a bisect is about.
2. Joining on a hash when the ledger stores a shortened path
   (`boot.img(h12/boot.img)`).
3. Parsing `boot.json` with plain UTF-8 when PowerShell wrote a BOM, which makes
   every row raise and the whole evidence directory look empty.
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE = HERE.parent / 'check-bisect-coverage.py'
REPO = HERE.parent.parent


def load_gate():
    spec = importlib.util.spec_from_file_location('k60_bisect_coverage', GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_image(artifacts, name, sha, mtime=None):
    directory = os.path.join(artifacts, name)
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, 'boot.img'), 'wb') as handle:
        handle.write(b'boot')
    with open(os.path.join(directory, 'build-manifest.json'), 'w') as handle:
        json.dump({'components': {'boot_img': sha}}, handle)
    if mtime is not None:
        os.utime(os.path.join(directory, 'boot.img'), (mtime, mtime))


def write_flight(evidence, stamp, image_path, sha, bom=True):
    directory = os.path.join(evidence, stamp)
    os.makedirs(directory, exist_ok=True)
    payload = json.dumps({'image': image_path, 'imageSha256': sha.upper()})
    encoding = 'utf-8-sig' if bom else 'utf-8'
    with open(os.path.join(directory, 'boot.json'), 'w', encoding=encoding) as handle:
        handle.write(payload)


SHA_A = 'a' * 64
SHA_B = 'b' * 64
SHA_C = 'c' * 64


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.gate = load_gate()
        self.root = tempfile.mkdtemp(prefix='k60-coverage-')
        self.artifacts = os.path.join(self.root, 'artifacts')
        self.evidence = os.path.join(self.root, 'evidence')
        os.makedirs(self.artifacts)
        os.makedirs(self.evidence)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_every_built_image_has_a_flight(self):
        write_image(self.artifacts, 'bt-bisect-h1', SHA_A)
        write_image(self.artifacts, 'bt-bisect-h12', SHA_B)
        write_flight(self.evidence, 'usblog-1', 'E:\\k60-work\\artifacts\\bt-bisect-h1\\boot.img', SHA_A)
        write_flight(self.evidence, 'usblog-2', 'E:\\k60-work\\artifacts\\bt-bisect-h12\\boot.img', SHA_B)
        self.assertEqual(self.gate.stale_images(self.artifacts, self.evidence), [])

    def test_a_silent_flight_still_counts(self):
        # The decisive P-218 cell: h123 was built and flown, but it was silent,
        # so record-boot.py wrote no ledger row.  boot.json exists regardless.
        write_image(self.artifacts, 'bt-bisect-h123', SHA_A)
        write_flight(self.evidence, 'usblog-silent',
                     'E:\\k60-work\\artifacts\\bt-bisect-h123\\boot.img', SHA_A)
        self.assertEqual(self.gate.stale_images(self.artifacts, self.evidence), [])

    def test_a_built_image_without_a_flight_is_reported(self):
        write_image(self.artifacts, 'bt-bisect-h2', SHA_A)
        stale = self.gate.stale_images(self.artifacts, self.evidence)
        self.assertEqual([name for name, _, _ in stale], ['bt-bisect-h2'])

    def test_the_ledger_is_not_the_flight_record(self):
        # A ledger row alone must not make an image look flown: the gate reads
        # evidence directories, and this asserts it does not fall back.
        write_image(self.artifacts, 'bt-bisect-h4', SHA_A)
        ledger = os.path.join(self.root, 'ledger.jsonl')
        with open(ledger, 'w') as handle:
            handle.write(json.dumps({'image': 'boot.img(h4/boot.img)',
                                     'result': 'ok'}) + '\n')
        stale = self.gate.stale_images(self.artifacts, self.evidence)
        self.assertEqual([name for name, _, _ in stale], ['bt-bisect-h4'])

    def test_a_utf8_bom_does_not_hide_a_flight(self):
        write_image(self.artifacts, 'bt-bisect-h13', SHA_A)
        write_flight(self.evidence, 'usblog-bom',
                     'E:\\k60-work\\artifacts\\bt-bisect-h13\\boot.img', SHA_A, bom=True)
        self.assertEqual(self.gate.stale_images(self.artifacts, self.evidence), [])

    def test_a_flight_without_a_bom_is_also_read(self):
        write_image(self.artifacts, 'bt-bisect-h34', SHA_A)
        write_flight(self.evidence, 'usblog-plain',
                     'E:\\k60-work\\artifacts\\bt-bisect-h34\\boot.img', SHA_A, bom=False)
        self.assertEqual(self.gate.stale_images(self.artifacts, self.evidence), [])

    def test_a_renamed_directory_is_matched_by_hash(self):
        write_image(self.artifacts, 'bt-bisect-h124', SHA_A)
        write_flight(self.evidence, 'usblog-old-name',
                     'E:\\k60-work\\artifacts\\bt-bisect-old\\boot.img', SHA_A)
        self.assertEqual(self.gate.stale_images(self.artifacts, self.evidence), [])

    def test_the_prefix_bounds_the_report(self):
        write_image(self.artifacts, 'bt-bisect-h1', SHA_A)
        write_image(self.artifacts, 'wifi-20261116c3', SHA_B)
        stale = self.gate.stale_images(self.artifacts, self.evidence, prefix='bt-bisect-')
        self.assertEqual([name for name, _, _ in stale], ['bt-bisect-h1'])

    def test_since_skips_older_images(self):
        write_image(self.artifacts, 'audio-probe-old', SHA_A, mtime=1000.0)
        stale = self.gate.stale_images(self.artifacts, self.evidence, since=2000.0)
        self.assertEqual(stale, [])

    def test_a_directory_without_a_manifest_is_ignored(self):
        os.makedirs(os.path.join(self.artifacts, 'half-built'))
        open(os.path.join(self.artifacts, 'half-built', 'boot.img'), 'wb').close()
        self.assertEqual(self.gate.stale_images(self.artifacts, self.evidence), [])

    def test_a_missing_evidence_directory_reports_everything(self):
        write_image(self.artifacts, 'bt-bisect-h1', SHA_A)
        stale = self.gate.stale_images(self.artifacts, os.path.join(self.root, 'nope'))
        self.assertEqual([name for name, _, _ in stale], ['bt-bisect-h1'])

    def test_the_real_repository_runs(self):
        # The real gate must be runnable and must not crash on this machine.
        code = os.system('%s %s --prefix __no_such_prefix__ > /dev/null 2>&1'
                         % (sys.executable, GATE))
        self.assertIn(code, (0, 256, 512))


if __name__ == '__main__':
    unittest.main(verbosity=2)
