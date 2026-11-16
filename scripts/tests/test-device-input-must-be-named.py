#!/usr/bin/env python3
"""The three input-comparing gates must refuse when K60_DEVICE_INPUT is unset.

2026-11-16 incident: an unset variable did not fail; each script silently fell
back to /opt/k60/trees/usb-cdc-mainline/device and graded the caller's tree
against a mirror the caller never named.  check-rules then reported five reds
(iron-4, iron-5, hard-33, P-165, P-166) that vanished as soon as the variable
was exported.  A verdict about the caller's mirror may only be produced from the
caller's mirror.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
GATES = ['scripts/sync-device-input.py', 'scripts/porting-gate.py', 'scripts/check-build-applied.py']


def run(gate: str, extra: list[str]) -> subprocess.CompletedProcess:
    environment = dict(os.environ)
    environment.pop('K60_DEVICE_INPUT', None)
    return subprocess.run([sys.executable, str(ROOT / gate), *extra],
                          capture_output=True, text=True, env=environment, check=False)


class InputMustBeNamed(unittest.TestCase):
    def test_each_gate_refuses_without_the_variable(self) -> None:
        for gate in GATES:
            with self.subTest(gate=gate):
                result = run(gate, ['--check'] if gate.endswith('sync-device-input.py') else [])
                self.assertNotEqual(result.returncode, 0, f'{gate} accepted an unset K60_DEVICE_INPUT')
                message = result.stdout + result.stderr
                self.assertIn('K60_DEVICE_INPUT', message, f'{gate} did not name the missing variable')

    def test_the_refusal_forbids_the_shared_mirror(self) -> None:
        for gate in GATES:
            with self.subTest(gate=gate):
                result = run(gate, ['--check'] if gate.endswith('sync-device-input.py') else [])
                message = result.stdout + result.stderr
                self.assertIn('refusing', message)
                self.assertNotIn('usb-cdc-mainline', message,
                                 f'{gate} still advertises the shared fallback path')

    def test_no_gate_still_hardcodes_the_shared_default(self) -> None:
        for gate in GATES:
            with self.subTest(gate=gate):
                text = (ROOT / gate).read_text(encoding='utf-8')
                self.assertNotIn("os.environ.get('K60_DEVICE_INPUT')\n       or '/opt",
                                 text.replace('  ', ' '), f'{gate} still substitutes a default')

    def test_the_variable_still_switches_the_gate_on(self) -> None:
        environment = dict(os.environ)
        environment['K60_DEVICE_INPUT'] = '/opt/k60/trees/gates-device'
        environment['K60_AGENT_ID'] = 'lead'
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/sync-device-input.py'), '--check'],
                                capture_output=True, text=True, cwd=str(ROOT), env=environment, check=False)
        self.assertNotIn('K60_DEVICE_INPUT is not set', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
