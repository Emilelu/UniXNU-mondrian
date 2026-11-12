#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Offline CLI regression tests; no build, device, framework import, or sync.

Run: python3 scripts/tests/test-config-consistency.py -v
Fixtures are disposable directories beside this test, cleaned after each case.
The checker runs from the fixture directory so explicit paths cannot rely on
its current working directory. Every invocation also verifies input bytes and
mtimes and the set of fixture files remain unchanged.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
CHECKER = TESTS.parent / "check-config-consistency.py"
LIVE_UUID = "1BCD69FF-24A5-48B1-94B6-8FE592B2F597"
SEED_UUID = "6DCCF70A-6FD6-403E-ACED-95313CD7CBB8"
UUID_SYMBOL = "CONFIG_XNU_OWNER_DATA_VOLUME_UUID"


class ConfigConsistencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(
            prefix="config-consistency-", dir=TESTS,
        )
        self.addCleanup(self.directory.cleanup)
        self.work = Path(self.directory.name)
        self.defconfig = self.work / "selected_defconfig"
        self.config = self.work / ".config"

    def inputs(self, expected: str, actual: str) -> None:
        self.defconfig.write_text(expected, encoding="utf-8")
        self.config.write_text(actual, encoding="utf-8")

    def snapshot(self) -> dict[Path, tuple[bytes, int]]:
        return {
            path: (path.read_bytes(), path.stat().st_mtime_ns)
            for path in self.work.rglob("*") if path.is_file()
        }

    def run_check(self, *extra: str, use_config: bool = True) -> subprocess.CompletedProcess:
        args = [sys.executable, str(CHECKER), "--defconfig", str(self.defconfig)]
        if use_config:
            args.extend(["--config", str(self.config)])
        before = self.snapshot()
        result = subprocess.run(
            args + list(extra), cwd=self.work, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(before, self.snapshot(), "checker modified fixture files")
        return result

    def assert_pass(self, result: subprocess.CompletedProcess) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS:", result.stdout)
        self.assertEqual(result.stderr, "")

    def assert_fail(self, result: subprocess.CompletedProcess, *messages: str) -> None:
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("FAIL:", result.stderr)
        self.assertNotIn("PASS:", result.stdout)
        for message in messages:
            self.assertIn(message, result.stderr)

    def test_stale_data_uuid_fails_even_when_comment_has_live_uuid(self) -> None:
        self.inputs(
            f"# CONFIG_XNU_OWNER_DATA_VOLUME_UUID=\"{SEED_UUID}\" old seed\n"
            f"{UUID_SYMBOL}=\"{LIVE_UUID}\"\n",
            f"# CONFIG_XNU_OWNER_DATA_VOLUME_UUID=\"{LIVE_UUID}\" live window\n"
            f"{UUID_SYMBOL}=\"{SEED_UUID}\"\n",
        )
        self.assert_fail(
            self.run_check(), f"{UUID_SYMBOL} mismatch", LIVE_UUID, SEED_UUID,
            f"{self.defconfig}:2", f"{self.config}:2",
        )

    def test_missing_generated_config_fails_without_creating_it(self) -> None:
        self.defconfig.write_text("CONFIG_REQUIRED=y\n", encoding="utf-8")
        self.assert_fail(self.run_check(), "generated config missing", str(self.config))
        self.assertFalse(self.config.exists())

    def test_missing_defconfig_fails(self) -> None:
        self.config.write_text("CONFIG_REQUIRED=y\n", encoding="utf-8")
        self.assert_fail(self.run_check(), "defconfig missing", str(self.defconfig))

    def test_disabled_forms_are_equivalent_in_both_directions(self) -> None:
        self.inputs(
            "CONFIG_A=n\n# CONFIG_B is not set\nCONFIG_ON=y\n",
            "# CONFIG_A is not set\nCONFIG_B=n\nCONFIG_ON=y\n",
        )
        result = self.run_check()
        self.assert_pass(result)
        self.assertIn("3 explicit defconfig symbols", result.stdout)

    def test_strings_numbers_extra_symbols_and_comments(self) -> None:
        self.inputs(
            '# CONFIG_COMMENT=y\nCONFIG_TEXT="hash # and spaces = yes"\n'
            'CONFIG_EMPTY=""\nCONFIG_HEX=0x2a\nCONFIG_NEG=-0x2a\n'
            'CONFIG_LEADING=0016\nCONFIG_LITERAL="a\\nb"\n',
            'CONFIG_EXTRA=y\nCONFIG_TEXT="hash # and spaces = yes"\n'
            'CONFIG_EMPTY=""\nCONFIG_HEX=42\nCONFIG_NEG=-42\n'
            'CONFIG_LEADING=0x10\nCONFIG_LITERAL="a\\nb"\n',
        )
        self.assert_pass(self.run_check())

    def test_missing_disabled_symbol_is_not_implicitly_false(self) -> None:
        self.inputs("CONFIG_REQUIRED=n\nCONFIG_ON=y\n", "CONFIG_ON=y\n")
        self.assert_fail(self.run_check(), "CONFIG_REQUIRED missing", "expected n")

    def test_conflicting_defconfig_duplicates_fail(self) -> None:
        self.inputs("CONFIG_A=y\nCONFIG_A=n\n", "CONFIG_A=n\n")
        self.assert_fail(
            self.run_check(), "duplicate CONFIG_A",
            "line 1 has y", "line 2 has n", f"{self.defconfig}:2",
        )

    def test_generated_duplicates_are_reported_as_notes_not_failures(self) -> None:
        # The generated .config is fragments-then-defconfig and config.py is
        # last-assignment-wins (cli.py:123-135, config.py:82-107). Failing here
        # would fail every real build, so it is a note.
        self.inputs(
            f'{UUID_SYMBOL}="{LIVE_UUID}"\n',
            f'{UUID_SYMBOL}="{SEED_UUID}"\n{UUID_SYMBOL}="{LIVE_UUID}"\n',
        )
        result = self.run_check()
        self.assert_pass(result)
        self.assertIn("note:", result.stdout)
        self.assertIn(SEED_UUID, result.stdout)

    def test_generated_only_duplicate_symbol_is_a_note(self) -> None:
        self.inputs("CONFIG_A=y\n", "CONFIG_A=y\nCONFIG_EXTRA=y\nCONFIG_EXTRA=n\n")
        result = self.run_check()
        self.assert_pass(result)
        self.assertIn("CONFIG_EXTRA", result.stdout)

    def test_stale_last_assignment_still_fails(self) -> None:
        self.inputs(
            f'{UUID_SYMBOL}="{LIVE_UUID}"\n',
            f'{UUID_SYMBOL}="{LIVE_UUID}"\n{UUID_SYMBOL}="{SEED_UUID}"\n',
        )
        self.assert_fail(self.run_check(), "mismatch")

    def test_equivalent_duplicates_are_accepted(self) -> None:
        self.inputs(
            "CONFIG_A=n\n# CONFIG_A is not set\nCONFIG_NUM=42\nCONFIG_NUM=0x2a\n",
            "# CONFIG_A is not set\nCONFIG_A=n\nCONFIG_NUM=0x2a\nCONFIG_NUM=42\n",
        )
        self.assert_pass(self.run_check())

    def test_boolean_number_and_string_types_stay_distinct(self) -> None:
        for expected, actual in (("y", "1"), ("n", "0"), ('"42"', "42")):
            with self.subTest(expected=expected, actual=actual):
                self.inputs(f"CONFIG_A={expected}\n", f"CONFIG_A={actual}\n")
                self.assert_fail(self.run_check(), "CONFIG_A mismatch")

    def test_backslashes_are_literal_not_escape_decoded(self) -> None:
        self.inputs('CONFIG_A="a\\nb"\n', 'CONFIG_A="a\\\\nb"\n')
        self.assert_fail(self.run_check(), "CONFIG_A mismatch")

    def test_malformed_input_fails_even_with_other_matching_assignments(self) -> None:
        for malformed in (
            "CONFIG_BAD=m", "not-an-assignment", 'CONFIG_BAD="unterminated',
            "CONFIG_BAD=y # inline comment", "CONFIG_BAD = y",
        ):
            for source in (True, False):
                with self.subTest(malformed=malformed, source=source):
                    good = "CONFIG_A=y\n"
                    bad = good + malformed + "\n"
                    self.inputs(bad if source else good, good if source else bad)
                    self.assert_fail(self.run_check(), ":2:")

    def test_empty_or_comment_only_files_fail_closed(self) -> None:
        for empty in ("", "# explanation only\n# CONFIG_EXAMPLE=y\n"):
            for source in (True, False):
                with self.subTest(empty=empty, source=source):
                    good = "CONFIG_A=y\n"
                    self.inputs(empty if source else good, good if source else empty)
                    self.assert_fail(self.run_check(), "no explicit CONFIG_ assignments")

    def test_invalid_utf8_reports_read_error(self) -> None:
        self.defconfig.write_text("CONFIG_A=y\n", encoding="utf-8")
        self.config.write_bytes(b"CONFIG_A=y\n\xff\n")
        self.assert_fail(self.run_check(), "cannot read generated config")

    def test_config_directory_reports_read_error(self) -> None:
        self.defconfig.write_text("CONFIG_A=y\n", encoding="utf-8")
        self.config.mkdir()
        self.assert_fail(self.run_check(), "cannot read generated config")

    def test_out_uses_verified_k60_schema_two_layout(self) -> None:
        self.defconfig.write_text("CONFIG_A=y\n", encoding="utf-8")
        out = self.work / "output with spaces"
        config = out / "mondrian/ipados-16.6.1-20G81/mondrian/.config"
        config.parent.mkdir(parents=True)
        config.write_text("CONFIG_A=y\n", encoding="utf-8")
        result = self.run_check("--out", str(out), use_config=False)
        self.assert_pass(result)
        self.assertIn(str(config), result.stdout)

    def test_explicit_config_and_out_are_mutually_exclusive(self) -> None:
        self.inputs("CONFIG_A=y\n", "CONFIG_A=y\n")
        result = self.run_check("--out", str(self.work))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("not allowed with argument", result.stderr)


if __name__ == "__main__":
    unittest.main()
