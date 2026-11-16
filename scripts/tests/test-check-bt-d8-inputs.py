#!/usr/bin/env python3
"""Synthetic fixtures for explicit, fail-closed recorded-input checking.

No fixture represents a real build or device. Fixtures use their own reviewed
profile, never change the live D8 profile, and run entirely in temporary repos.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'check-bt-d8-inputs.py'
spec = importlib.util.spec_from_file_location('bt_d8_inputs', SCRIPT)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class RecordedInputs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='bt-d8-inputs-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repo'
        self.artifact = self.root / 'artifact'
        (self.repo / 'patches/xnu').mkdir(parents=True)
        (self.artifact / 'logs').mkdir(parents=True)
        self.names = ['a.patch', 'b.patch']
        self.bodies = {'a.patch': b'first patch\n', 'b.patch': b'second patch\n'}
        self.series = ('\n'.join(self.names) + '\n').encode()
        (self.repo / 'patches/xnu/series').write_bytes(self.series)
        for name, data in self.bodies.items():
            (self.repo / 'patches/xnu' / name).write_bytes(data)
        self.git('init', '-q')
        self.git('add', '.')
        self.git('-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid',
                 'commit', '-q', '-m', 'fixture')
        head = self.git('rev-parse', 'HEAD').strip().decode()
        frozen = ''.join(gate.sha(self.bodies[n]) + '  patches/xnu/' + n + '\n' for n in self.names).encode()
        for suffix in ('before', 'after'):
            (self.artifact / f'frozen-{suffix}.txt').write_bytes(frozen)
        self.log = b'== kernel: patch a.patch\n== kernel: patch b.patch\n'
        (self.artifact / 'logs/kernel.log').write_bytes(self.log)
        (self.artifact / 'boot.img').write_bytes(b'synthetic image, not bootable')
        # This fixture equation is independent of the imported fingerprint helper.
        fp_bytes = b''.join(n.encode() + str(len(self.bodies[n])).encode() for n in self.names)
        self.manifest = {
            'repo': {'head': head, 'dirty_files': 0},
            'frozen': {'file': 'frozen-before.txt', 'list_sha256': gate.sha(frozen)},
            'series': {'file_sha256': gate.sha(self.series), 'count': 2,
                       'namespace': 'names+sizes', 'sha256': gate.sha(fp_bytes)[:16]},
            'components': {'boot_img': gate.file_sha(self.artifact / 'boot.img')},
        }
        self.profile = {'head': head, 'kernel_log': gate.sha(self.log),
                        'patches': {n: gate.sha(b) for n, b in self.bodies.items()}}
        self.save_manifest()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True,
                              capture_output=True).stdout

    def save_manifest(self):
        data = json.dumps(self.manifest, sort_keys=True).encode()
        (self.artifact / 'build-manifest.json').write_bytes(data)
        self.profile['manifest'] = gate.sha(data)

    def check(self):
        return gate.check(self.repo, self.artifact, self.profile)

    def assertFails(self, message):
        result = self.check()
        self.assertEqual(result['state'], 'FAIL')
        self.assertTrue(any(message in error for error in result['errors']), result)

    def test_exact_recorded_inputs_match_with_explicit_limitations(self):
        result = self.check()
        self.assertEqual(result['state'], 'RECORDED_INPUTS_MATCH', result)
        self.assertIn('flash-gate coverage', result['not_proven'])
        self.assertIn('hardware function', result['not_proven'])

    def test_missing_artifact_fails_not_skip(self):
        (self.artifact / 'frozen-before.txt').unlink()
        self.assertFails('unavailable')

    def test_malformed_manifest_fails(self):
        (self.artifact / 'build-manifest.json').write_bytes(b'{')
        self.assertFails('malformed')

    def test_manifest_change_is_not_accepted_by_its_own_hash_fields(self):
        (self.artifact / 'build-manifest.json').write_bytes(b'{}')
        self.assertFails('manifest sha256 differs')

    def test_frozen_after_must_equal_before(self):
        (self.artifact / 'frozen-after.txt').write_bytes(b'changed')
        self.assertFails('before/after differ')

    def test_patch_bytes_not_just_name_and_size_are_checked(self):
        body = self.bodies['a.patch'].replace(b'first', b'other')
        self.assertEqual(len(body), len(self.bodies['a.patch']))
        (self.repo / 'patches/xnu/a.patch').write_bytes(body)
        self.assertFails('patch bytes differ')

    def test_selected_patch_must_belong_to_the_series(self):
        self.profile['patches']['absent.patch'] = '0' * 64
        self.assertFails('absent from series')

    def test_application_log_substring_does_not_count(self):
        changed = self.log.replace(b'== kernel: patch b.patch', b'comment mentions b.patch')
        (self.artifact / 'logs/kernel.log').write_bytes(changed)
        self.profile['kernel_log'] = gate.sha(changed)
        self.assertFails('exactly once: b.patch')

    def test_duplicate_application_log_fails(self):
        changed = self.log + b'== kernel: patch b.patch\n'
        (self.artifact / 'logs/kernel.log').write_bytes(changed)
        self.profile['kernel_log'] = gate.sha(changed)
        self.assertFails('exactly once: b.patch')

    def test_application_order_is_checked(self):
        changed = b'== kernel: patch b.patch\n== kernel: patch a.patch\n'
        (self.artifact / 'logs/kernel.log').write_bytes(changed)
        self.profile['kernel_log'] = gate.sha(changed)
        self.assertFails('application order differs')

    def test_boot_bytes_are_independently_hashed(self):
        (self.artifact / 'boot.img').write_bytes(b'different image')
        self.assertFails('boot image sha256 differs')

    def test_unknown_namespace_is_rejected(self):
        self.manifest['series']['namespace'] = 'file'
        self.save_manifest()
        self.assertFails('unknown series fingerprint namespace')

    def test_duplicate_frozen_paths_are_rejected(self):
        data = (self.artifact / 'frozen-before.txt').read_bytes()
        data += data.splitlines(keepends=True)[0]
        for suffix in ('before', 'after'):
            (self.artifact / f'frozen-{suffix}.txt').write_bytes(data)
        self.manifest['frozen']['list_sha256'] = gate.sha(data)
        self.save_manifest()
        self.assertFails('duplicate frozen entry')

    def test_single_backslash_is_not_a_plain_basename(self):
        with self.assertRaisesRegex(ValueError, 'plain patch basenames'):
            gate.patch_names(('folder' + chr(92) + 'a.patch\n').encode())

    def test_dirty_manifest_is_rejected_even_in_a_reviewed_fixture(self):
        self.manifest['repo']['dirty_files'] = 1
        self.save_manifest()
        self.assertFails('dirty source')

    def test_missing_recorded_commit_fails_without_a_latest_fallback(self):
        self.profile['head'] = '0' * 40
        self.manifest['repo']['head'] = self.profile['head']
        self.save_manifest()
        self.assertFails('cannot read committed source')

    def test_cli_has_no_implicit_latest_or_other_tree(self):
        result = subprocess.run([os.sys.executable, str(SCRIPT)], capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn(b'--repo', result.stderr)
        self.assertIn(b'--artifact', result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
