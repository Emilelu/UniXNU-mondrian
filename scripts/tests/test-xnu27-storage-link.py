#!/usr/bin/env python3
"""Tests for scripts/check-xnu27-storage-link.py."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/check-xnu27-storage-link.py'

CONTROL = '''Undefined symbols for architecture arm64e:
  "_version_minor", referenced from:
      _kernel_bootstrap in startup.o
ld: symbol(s) not found for architecture arm64e
'''

STORAGE = CONTROL + '''Undefined symbols for architecture arm64e:
  "__ZTV20IOBlockStorageDevice", referenced from:
      __ZN12PongUfsBlock5startEP9IOService in libNativeUfs.a(PongUfsTransport.o)
  "_armcpu_timer_interrupts", referenced from:
      __ZN12_GLOBAL__N_118registrationReportEPvi in libNativeUfs.a(NativeUfs.o)
ld: symbol(s) not found for architecture arm64e
'''

OTHER = CONTROL + '''Undefined symbols for architecture arm64e:
  "_something_else", referenced from:
      _caller in other.o
ld: symbol(s) not found for architecture arm64e
'''


class Harness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.tree = self.dir / 'obj'
        self.tree.mkdir()
        (self.tree / '.LDFLAGS').write_bytes(
            b'/opt/unixnu-linux/llvm/bin/clang++\x00-Wl,-static\x00-o\x00kernel\x00')
        (self.tree / 'link.filelist').write_text('a.o\n')
        self.archive = self.dir / 'libNativeUfs.a'
        self.archive.write_bytes(b'!<arch>\n')
        self.control = self.dir / 'control.txt'
        self.control.write_text(CONTROL)
        self.archived = self.dir / 'archive.txt'
        self.archived.write_text(STORAGE)

    def tearDown(self):
        self.tmp.cleanup()

    def run_check(self, *extra, control_rc='1', archive_rc='1'):
        env = dict(os.environ)
        env['CONTROL_RC'] = control_rc
        env['ARCHIVE_RC'] = archive_rc
        args = [sys.executable, str(SCRIPT), '--tree', str(self.tree),
                '--archive', str(self.archive),
                '--control-stderr', str(self.control),
                '--archive-stderr', str(self.archived)] + list(extra)
        return subprocess.run(args, capture_output=True, text=True, env=env)

    def test_reports_the_storage_imports(self):
        run = self.run_check()
        self.assertEqual(run.returncode, 0)
        self.assertIn('the archive needs 1 IOBlockStorageDevice import(s)', run.stdout)
        self.assertIn('IOStorageFamily fileset entry', run.stdout)
        self.assertIn('bluetooth-storage-link: gap', run.stdout)

    def test_names_every_new_symbol_with_its_class(self):
        run = self.run_check()
        self.assertIn('storage-class  __ZTV20IOBlockStorageDevice', run.stdout)
        self.assertIn('other          _armcpu_timer_interrupts', run.stdout)
        self.assertIn('from __ZN12PongUfsBlock5startEP9IOService', run.stdout)

    def test_a_linked_archive_is_ok(self):
        self.archived.write_text('')
        out = self.dir / 'success-report.json'
        run = self.run_check('--out', str(out), control_rc='0', archive_rc='0')
        self.assertEqual(run.returncode, 0)
        self.assertIn('bluetooth-storage-link: OK', run.stdout)
        report = json.loads(out.read_text())
        self.assertEqual(report['archive_rc'], 0)
        self.assertEqual(report['new_symbols'], [])
        self.assertEqual(report['storage_imports'], [])

    def test_unchanged_undefined_symbols_are_not_new(self):
        self.archived.write_text(CONTROL)
        run = self.run_check()
        self.assertIn('new=0', run.stdout)
        self.assertIn('the recorded link already fails on its own', run.stdout)

    def test_a_non_storage_symbol_is_not_blamed_on_the_class(self):
        self.archived.write_text(OTHER)
        run = self.run_check()
        self.assertIn('not from the storage class', run.stdout)
        self.assertNotIn('IOStorageFamily', run.stdout)

    def test_require_linkable_turns_the_gap_into_a_failure(self):
        run = self.run_check('--require-linkable')
        self.assertEqual(run.returncode, 1)
        self.assertIn('bluetooth-storage-link: FAILED', run.stdout)

    def test_report_records_the_class_and_the_referrers(self):
        out = self.dir / 'report' / 'report.json'
        self.run_check('--out', str(out))
        report = json.loads(out.read_text())
        self.assertEqual(report['control_rc'], 1)
        self.assertEqual(len(report['storage_imports']), 1)
        self.assertFalse(report['hardware_verified'])
        row = next(r for r in report['new_symbols'] if r['symbol'] == '_armcpu_timer_interrupts')
        self.assertEqual(row['class'], 'other')
        self.assertTrue(row['referenced_from'][0].startswith('__ZN12_GLOBAL__N_1'))

    def test_a_missing_archive_fails_before_linking(self):
        self.archive.unlink()
        run = self.run_check()
        self.assertEqual(run.returncode, 1)
        self.assertIn('FAIL archive', run.stdout)

    def test_dry_run_prints_both_link_commands(self):
        run = subprocess.run([sys.executable, str(SCRIPT), '--tree', str(self.tree),
                              '--archive', str(self.archive), '--dry-run'],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0)
        lines = [l for l in run.stdout.splitlines() if l.startswith('/opt/unixnu-linux')]
        self.assertEqual(len(lines), 2)
        self.assertNotIn('-force_load', lines[0])
        self.assertIn('-force_load,' + str(self.archive), lines[1])
        self.assertIn('-target arm64e-apple-ios27.0', lines[0])

    def test_the_parse_ignores_the_intro_and_the_ld_trailer(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        import importlib.util
        spec = importlib.util.spec_from_file_location('slink', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        parsed = module.parse_undefined(STORAGE)
        self.assertEqual(sorted(parsed), ['__ZTV20IOBlockStorageDevice', '_armcpu_timer_interrupts', '_version_minor'])
        self.assertNotIn('ld: symbol(s) not found', ' '.join(parsed))

    def test_a_tree_without_a_link_line_says_so(self):
        (self.tree / '.LDFLAGS').unlink()
        run = self.run_check()
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('FAIL no recorded link line', run.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
