#!/usr/bin/env python3
"""Tests for check-ios27-board-inputs.py. Offline: every fixture is built in a temp dir.

Run: python3 test_check_ios27_board_inputs.py
The negative cases must go red for the intended reason: each asserts the exit
code *and* that the named check is the one that failed, so a fixture that trips
a different check, or passes for the wrong reason, fails the test.

The fixture also carries a minimal `scripts/unixnu/profiles.py` so the gate's
merge mirror has something to compare against; one test breaks that file on
purpose to prove the mirror check can go red.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("check-ios27-board-inputs.py")

GOOD_BOARD = """
[board]
os_profile = "test-os"

[firmware]
config = "mondrian"
dsc = "Platforms/Xiaomi/mondrianPkg/mondrian.dsc"
fd = "Build/mondrianPkg/{target}_CLANGPDB/FV/SILICIUM_UEFI.fd"

[payload]
random_seed = "11"
root_match_volume_uuid = "E3F4AED0-4454-4D5B-833C-E27E99C4F67B"

[payload.adt]
chip_id = "8015"

[os_overrides."test-os"]
remove = []

[os_overrides."test-os".payload.adt]
chip_id = "8140"
"""

GOOD_CONFIG = """
[uefi_fd]
base = 0xA7400000
size = 0x300000
"""

GOOD_LOADER = """
#define UNIXNU_LOADER_REVISION_1  0x00010000
#define UNIXNU_LOADER_REVISION    0x00020000
"""

GOOD_PROFILES = '''
import copy


def merge(base, overlay):
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result
'''

MODULES = (
    "Platforms/Xiaomi/UniXNUPkg/Application/UniXNU/UniXNU.inf",
    "Platforms/Xiaomi/UniXNUPkg/Driver/UniXNUDxe/UniXNUDxe.inf",
    "Platforms/Xiaomi/UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe.inf",
    "Platforms/Xiaomi/DarwinBootPkg/Driver/DarwinBoot.inf",
)


class Fixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.device = root / "device"
        self.uefi = root / "uefi"
        self.framework = root / "framework"
        for path in (self.device, self.uefi, self.framework / "scripts/unixnu"):
            path.mkdir(parents=True)
        (self.framework / "scripts/unixnu/__init__.py").write_text("", encoding="utf-8")
        (self.framework / "scripts/unixnu/profiles.py").write_text(GOOD_PROFILES, encoding="utf-8")
        self.write_board(GOOD_BOARD)
        self.write_config(GOOD_CONFIG)
        self.write_loader(GOOD_LOADER)
        self.touch("Platforms/Xiaomi/mondrianPkg/mondrian.dsc")
        for rel in MODULES:
            self.touch(rel)

    # -- writers ---------------------------------------------------------
    def write_board(self, text: str) -> None:
        (self.device / "board.toml").write_text(textwrap.dedent(text), encoding="utf-8")

    def write_config(self, text: str) -> None:
        path = self.uefi / "Resources/Configs/mondrian.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text), encoding="utf-8")

    def write_loader(self, text: str) -> None:
        path = self.uefi / "Platforms/Xiaomi/UniXNUPkg/Include/Protocol/UniXNULoader.h"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text), encoding="utf-8")

    def break_merge(self) -> None:
        (self.framework / "scripts/unixnu/profiles.py").write_text(
            "def merge(base, overlay):\n    return dict(base, **overlay)\n", encoding="utf-8"
        )

    def touch(self, rel: str, body: str = "x") -> None:
        path = self.uefi / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    def built_fd(self, size: int) -> None:
        path = self.uefi / "Build/mondrianPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\0" * size)

    # -- runner ----------------------------------------------------------
    def run(self, *args: str, framework: bool = True) -> tuple[int, dict]:
        command = [sys.executable, str(SCRIPT), "--device", str(self.device), "--uefi", str(self.uefi), "--json"]
        if framework:
            command += ["--framework", str(self.framework)]
        command += list(args)
        proc = subprocess.run(command, capture_output=True, text=True)
        payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
        return proc.returncode, payload


def states(payload: dict) -> dict:
    return {item["check"]: item["state"] for item in payload.get("results", [])}


def details(payload: dict) -> dict:
    return {item["check"]: item["detail"] for item in payload.get("results", [])}


class PreflightTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.fixture = Fixture(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # -- positive --------------------------------------------------------
    def test_good_board_passes(self) -> None:
        code, payload = self.fixture.run()
        self.assertEqual(code, 0, payload)
        self.assertEqual(set(states(payload).values()), {"pass"})

    def test_override_wins_over_top_level_value(self) -> None:
        code, payload = self.fixture.run()
        self.assertEqual(code, 0, payload)
        self.assertIn("chip_id=8140", details(payload)["payload-inputs"])
        self.assertNotIn("8015", details(payload)["payload-inputs"])
        self.assertEqual(payload["values"], "effective (os_overrides applied)")

    def test_built_fd_that_fits_passes(self) -> None:
        self.fixture.built_fd(0x100000)
        code, payload = self.fixture.run()
        self.assertEqual(code, 0, payload)
        self.assertIn("fits", details(payload)["fd-window"])

    def test_exactly_full_fd_passes_but_says_no_headroom(self) -> None:
        self.fixture.built_fd(0x300000)
        code, payload = self.fixture.run()
        self.assertEqual(code, 0, payload)
        self.assertIn("no headroom", details(payload)["fd-window"])

    # -- negatives: each must go red for its own reason ------------------
    def test_missing_firmware_table_fails_board(self) -> None:
        self.fixture.write_board("[board]\nos_profile = 'test-os'\n")
        code, payload = self.fixture.run()
        self.assertEqual(code, 1)
        self.assertEqual(states(payload)["board"], "fail")

    def test_unknown_os_name_fails_os_override(self) -> None:
        code, payload = self.fixture.run("--os", "nope-1.0")
        self.assertEqual(code, 1)
        self.assertEqual(states(payload)["os-override"], "fail")

    def test_remove_list_is_honoured(self) -> None:
        self.fixture.write_board(GOOD_BOARD.replace('remove = []', 'remove = ["payload.adt.chip_id"]'))
        code, payload = self.fixture.run()
        self.assertEqual(code, 1)
        self.assertEqual(states(payload)["payload-inputs"], "fail")
        self.assertIn("chip_id", details(payload)["payload-inputs"])

    def test_merge_mirror_disagreement_fails(self) -> None:
        self.fixture.break_merge()
        code, payload = self.fixture.run()
        self.assertEqual(code, 1)
        self.assertEqual(states(payload)["merge-mirror"], "fail")

    def test_missing_dsc_fails_dsc(self) -> None:
        (self.fixture.uefi / "Platforms/Xiaomi/mondrianPkg/mondrian.dsc").unlink()
        code, payload = self.fixture.run()
        self.assertEqual(code, 1)
        self.assertEqual(states(payload)["dsc"], "fail")
        self.assertEqual(states(payload)["board"], "pass", "board must not be blamed for a missing DSC")

    def test_missing_module_fails_modules(self) -> None:
        (self.fixture.uefi / MODULES[3]).unlink()
        code, payload = self.fixture.run()
        self.assertEqual(code, 1)
        self.assertEqual(states(payload)["modules"], "fail")

    def test_misaligned_fd_fails_window(self) -> None:
        self.fixture.write_config("[uefi_fd]\nbase = 0xA7400800\nsize = 0x300000\n")
        code, payload = self.fixture.run()
        self.assertEqual(code, 1)
        self.assertEqual(states(payload)["fd-window"], "fail")

    def test_oversized_built_fd_fails_window(self) -> None:
        self.fixture.built_fd(0x300000 + 0x1000)
        code, payload = self.fixture.run()
        self.assertEqual(code, 1)
        self.assertEqual(states(payload)["fd-window"], "fail")

    def test_old_loader_revision_fails(self) -> None:
        self.fixture.write_loader("#define UNIXNU_LOADER_REVISION 0x00010000\n")
        code, payload = self.fixture.run()
        self.assertEqual(code, 1)
        self.assertEqual(states(payload)["loader-revision"], "fail")

    def test_loader_header_without_revision_fails(self) -> None:
        self.fixture.write_loader("/* nothing here */\n")
        code, payload = self.fixture.run()
        self.assertEqual(code, 1)
        self.assertEqual(states(payload)["loader-revision"], "fail")

    def test_bad_chip_id_fails_payload_inputs(self) -> None:
        self.fixture.write_board(GOOD_BOARD.replace('chip_id = "8140"', 'chip_id = "81400"'))
        code, payload = self.fixture.run()
        self.assertEqual(code, 1)
        self.assertEqual(states(payload)["payload-inputs"], "fail")

    def test_bad_uuid_fails_payload_inputs(self) -> None:
        self.fixture.write_board(GOOD_BOARD.replace("E3F4AED0-4454-4D5B-833C-E27E99C4F67B", "not-a-uuid"))
        code, payload = self.fixture.run()
        self.assertEqual(code, 1)
        self.assertEqual(states(payload)["payload-inputs"], "fail")

    # -- cannot judge ----------------------------------------------------
    def test_absent_uefi_is_unknown_not_pass(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--device", str(self.fixture.device),
             "--framework", str(self.fixture.framework), "--json"],
            capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"},
        )
        payload = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 2, "cannot judge must not look like a pass")
        self.assertEqual(states(payload)["modules"], "unknown")
        self.assertEqual(states(payload)["fd-window"], "unknown")

    def test_absent_framework_is_unknown_not_pass(self) -> None:
        code, payload = self.fixture.run(framework=False)
        self.assertEqual(code, 2)
        self.assertEqual(states(payload)["merge-mirror"], "unknown")

    def test_allow_unknown_returns_zero_but_keeps_the_report(self) -> None:
        code, payload = self.fixture.run("--allow-unknown", framework=False)
        self.assertEqual(code, 0)
        self.assertEqual(payload["unknown"], 1, "the absent framework stays visible in the report")

    def test_allow_unknown_never_rescues_a_failure(self) -> None:
        (self.fixture.uefi / MODULES[0]).unlink()
        code, _ = self.fixture.run("--allow-unknown", framework=False)
        self.assertEqual(code, 1)

    def test_missing_device_is_two(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--device", str(self.fixture.root / "nope")],
            capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"},
        )
        self.assertEqual(proc.returncode, 2)

    def test_invalid_toml_is_one(self) -> None:
        (self.fixture.device / "board.toml").write_text("[firmware\nbad", encoding="utf-8")
        code, _ = self.fixture.run()
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
