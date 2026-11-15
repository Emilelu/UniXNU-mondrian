#!/usr/bin/env python3
"""Tests for scripts/check-data-identity.py (P-210).

The gate has to score every defconfig that mounts a Data window, not just
``configs/mondrian_defconfig``. The wifi board's own defconfig was never scored,
which is how the 32 MiB seed UUID reached a shipped build.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

GATE = Path(__file__).resolve().parent.parent / "check-data-identity.py"

LIVE_UUID = "1BCD69FF-24A5-48B1-94B6-8FE592B2F597"
SEED_UUID = "6DCCF70A-6FD6-403E-ACED-95313CD7CBB8"


def load_gate():
    spec = importlib.util.spec_from_file_location("k60_check_data_identity", GATE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def make_config(directory: Path, name: str, uuid: str, mounts: bool = True) -> Path:
    body = ["CONFIG_XNU_OWNER_DATA_MOUNT=y" if mounts else "CONFIG_XNU_OWNER_DATA_MOUNT=n", ""]
    if uuid:
        body.append(f'CONFIG_XNU_OWNER_DATA_VOLUME_UUID="{uuid}"')
    return write(directory / name, "\n".join(body) + "\n")


def make_console(evidence: Path, uuid: str, size: int = 8192) -> Path:
    log = evidence / "usblog-20260101-000000" / "console.log"
    line = (f"K60DATA: window media uuid={uuid} name=Data block=512 depth=3\n")
    text = line * (size // max(1, len(line)))
    return write(log, text)


def make_patch(repo: Path, ceiling: int = 0x600000000) -> Path:
    body = (
        "--- a/bsd/vfs/vfs_mountroot.c\n"
        "+++ b/bsd/vfs/vfs_mountroot.c\n"
        "@@ -1,2 +1,4 @@\n"
        " if (size > UINT64_C(0x%x)) {\n"
        "     return EINVAL;\n" % ceiling
    )
    return write(repo / "patches" / "xnu" / "offline-owner-systemos-mount.patch", body)


def make_manifest(repo: Path, data_bytes: int) -> Path:
    text = f"Images:\n  Data: off=1234 size={data_bytes}\n"
    return write(repo / "scratch" / "cur-manifest.bin", text)


class Fixture:
    def __init__(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="k60-data-identity-"))
        self.repo = self.root / "repo"
        self.configs = self.repo / "configs"
        self.evidence = self.root / "evidence"
        self.configs.mkdir(parents=True)
        self.evidence.mkdir(parents=True)
        make_patch(self.repo)
        make_manifest(self.repo, 21_342_715_904)
        make_console(self.evidence, LIVE_UUID)

    def close(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def truth(self) -> tuple[list[str], list[str]]:
        gate = load_gate()
        return gate.run(config_dir=self.configs, evidence=self.evidence,
                        patch=self.repo / "patches" / "xnu" / "offline-owner-systemos-mount.patch",
                        manifest=self.repo / "scratch" / "cur-manifest.bin")


def case_a_good_config_passes(fx: Fixture) -> None:
    make_config(fx.configs, "mondrian_defconfig", LIVE_UUID)
    problems, notes = fx.truth()
    assert not problems, problems
    assert any("observed" in n for n in notes), notes


def case_b_second_defconfig_is_scored(fx: Fixture) -> None:
    """The P-210 case: a board-specific defconfig with a foreign UUID must fail."""
    make_config(fx.configs, "mondrian_defconfig", LIVE_UUID)
    make_config(fx.configs, "mondrian_wifi_defconfig", SEED_UUID)
    problems, _ = fx.truth()
    assert problems, "a foreign UUID in a second defconfig must be reported"
    joined = " ".join(problems)
    assert "mondrian_wifi_defconfig" in joined, joined
    assert SEED_UUID in joined, joined
    assert "mondrian_defconfig:" not in joined.replace("mondrian_wifi_defconfig:", ""), joined


def case_c_config_without_the_mount_key_is_ignored(fx: Fixture) -> None:
    make_config(fx.configs, "mondrian_defconfig", LIVE_UUID)
    make_config(fx.configs, "some_other_defconfig", SEED_UUID, mounts=False)
    problems, _ = fx.truth()
    assert not problems, problems


def case_d_missing_uuid_is_a_problem(fx: Fixture) -> None:
    make_config(fx.configs, "mondrian_defconfig", "")
    problems, _ = fx.truth()
    assert problems and "missing" in problems[0], problems


def case_e_no_console_log_skips(fx: Fixture) -> None:
    shutil.rmtree(fx.evidence)
    fx.evidence.mkdir(parents=True)
    make_config(fx.configs, "mondrian_defconfig", SEED_UUID)
    problems, notes = fx.truth()
    assert not problems, problems
    assert any("skipped" in n for n in notes), notes


def case_f_log_without_window_lines_skips(fx: Fixture) -> None:
    shutil.rmtree(fx.evidence)
    write(fx.evidence / "usblog-20260101-000000" / "console.log", "nothing here\n" * 1000)
    make_config(fx.configs, "mondrian_defconfig", SEED_UUID)
    problems, notes = fx.truth()
    assert not problems, problems
    assert any("window media uuid" in n for n in notes), notes


def case_g_ceiling_below_the_window_fails(fx: Fixture) -> None:
    make_config(fx.configs, "mondrian_defconfig", LIVE_UUID)
    make_patch(fx.repo, ceiling=0x80000000)
    problems, _ = fx.truth()
    assert any("P-153" in p for p in problems), problems


def case_h_missing_manifest_skips_the_ceiling(fx: Fixture) -> None:
    make_config(fx.configs, "mondrian_defconfig", LIVE_UUID)
    (fx.repo / "scratch" / "cur-manifest.bin").unlink()
    problems, notes = fx.truth()
    assert not problems, problems
    assert any("ceiling cross-check skipped" in n for n in notes), notes


def case_i_real_repository_reconciles() -> None:
    """The real tree must reach a verdict without raising."""
    gate = load_gate()
    problems, notes = gate.run()
    assert isinstance(problems, list) and isinstance(notes, list)
    for problem in problems:
        assert "Traceback" not in problem, problems


CASES = [
    ("a_good_config_passes", case_a_good_config_passes, True),
    ("a_second_defconfig_is_scored", case_b_second_defconfig_is_scored, True),
    ("a_config_without_the_mount_key_is_ignored", case_c_config_without_the_mount_key_is_ignored, True),
    ("a_missing_uuid_is_a_problem", case_d_missing_uuid_is_a_problem, True),
    ("no_console_log_skips_the_uuid", case_e_no_console_log_skips, True),
    ("a_log_without_window_lines_skips", case_f_log_without_window_lines_skips, True),
    ("a_ceiling_below_the_window_fails", case_g_ceiling_below_the_window_fails, True),
    ("a_missing_manifest_skips_the_ceiling", case_h_missing_manifest_skips_the_ceiling, True),
    ("the_real_repository_reconciles", case_i_real_repository_reconciles, False),
]


def main() -> int:
    failures = 0
    for name, function, needs_fixture in CASES:
        fixture = Fixture() if needs_fixture else None
        try:
            function(fixture) if needs_fixture else function()
            print(f"  ok   {name}")
        except Exception:
            failures += 1
            print(f"  FAIL {name}")
            traceback.print_exc()
        finally:
            if fixture is not None:
                fixture.close()
    total = len(CASES)
    print(f"TESTS {'OK' if not failures else 'FAILED'} {total - failures}/{total}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
