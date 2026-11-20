#!/usr/bin/env python3
"""Host tests for scripts/check-27-series-composition.py.

Every fixture here is a real directory tree, because the bug this guards
against (P-266) is precisely a path that does not exist yet is not reported.
A test that stubs the filesystem would have passed on the broken version.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE.parent / "check-27-series-composition.py"

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}{(': ' + detail) if detail else ''}")
        FAILURES.append(name)


def write_series(path: pathlib.Path, entries: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# fixture\n" + "".join(f"{entry}\n" for entry in entries), encoding="utf-8")


def write_board(path: pathlib.Path, profile: str) -> None:
    path.write_text(
        "[board]\n"
        f'os_profile = "{profile}"\n'
        "\n"
        "[kernel]\n"
        'patch_series = ["arch:patches/xnu/series", "soc:patches/xnu-12377/series",\n'
        '                "os:patches/xnu/series", "device:patches/xnu-12377/series"]\n',
        encoding="utf-8",
    )


def build_fixture(root: pathlib.Path, *, with_soc: bool = True) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    framework = root / "framework"
    device = root / "device"
    soc = root / "soc"
    profile = "ios-27.0.1-24A446"

    (framework / "profiles" / "os" / profile).mkdir(parents=True)
    (framework / "profiles" / "os" / profile / "profile.toml").write_text(
        '[os]\narch = "arm64e"\n', encoding="utf-8"
    )
    write_series(framework / "profiles" / "arch" / "arm64e" / "patches" / "xnu" / "series",
                 ["../../../../../patches/xnu-12377/arch-one.patch",
                  "../../../../../patches/xnu-12377/arch-two.patch"])
    write_series(framework / "profiles" / "os" / profile / "patches" / "xnu" / "series",
                 ["zzz-boot-progress.patch"])

    device.mkdir(parents=True)
    write_board(device / "board.toml", profile)
    write_series(device / "patches" / "xnu-12377" / "series", ["device-one.patch"])

    if with_soc:
        write_series(soc / "patches" / "xnu-12377" / "series",
                     ["sheng-platform-power.patch", "native-smp-secondary.patch"])
    return framework, device, soc


def run(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *argv],
        capture_output=True, text=True, check=False,
    )


def layer_line(stdout: str, reference: str, count: int) -> bool:
    """True when a `reference<count>` summary line is present, whatever the padding."""
    pattern = re.compile(rf"^{re.escape(reference)}\s+{count}$", re.MULTILINE)
    return pattern.search(stdout) is not None


def total_line(stdout: str, count: int) -> bool:
    return re.search(rf"^total\s+{count}$", stdout, re.MULTILINE) is not None


def test_four_layers_resolve() -> None:
    print("four layers resolve to four different files")
    with tempfile.TemporaryDirectory() as tmp:
        framework, device, soc = build_fixture(pathlib.Path(tmp))
        done = run("--framework", str(framework), "--device", str(device), "--soc", str(soc))
        check("exits 0", done.returncode == 0, done.stderr.strip())
        check("arch layer has 2", layer_line(done.stdout, "arch:patches/xnu/series", 2), done.stdout)
        check("soc layer has 2", layer_line(done.stdout, "soc:patches/xnu-12377/series", 2), done.stdout)
        check("os layer has 1", layer_line(done.stdout, "os:patches/xnu/series", 1), done.stdout)
        check("device layer has 1", layer_line(done.stdout, "device:patches/xnu-12377/series", 1), done.stdout)
        check("total is 6", total_line(done.stdout, 6), done.stdout)
        check("order starts with arch", done.stdout.splitlines()[0].startswith("arch    arch-one.patch"),
              done.stdout.splitlines()[0] if done.stdout else "")


def test_device_only_read_is_short() -> None:
    """The whole point of P-266: a device-only checkout cannot see three layers."""
    print("a device-only tree resolves the framework layers to nothing")
    with tempfile.TemporaryDirectory() as tmp:
        framework, device, soc = build_fixture(pathlib.Path(tmp))
        # Point --framework at the device repo: the profiles directories are absent.
        done = run("--framework", str(device), "--device", str(device), "--soc", str(soc))
        check("exits 0 but reports fewer patches", done.returncode == 0, done.stderr.strip())
        check("total drops to 3", total_line(done.stdout, 3), done.stdout)
        check("arch layer is empty", layer_line(done.stdout, "arch:patches/xnu/series", 0), done.stdout)


def test_missing_soc_is_refused() -> None:
    print("a missing soc root is refused, not silently dropped")
    with tempfile.TemporaryDirectory() as tmp:
        framework, device, _ = build_fixture(pathlib.Path(tmp), with_soc=False)
        done = run("--framework", str(framework), "--device", str(device))
        check("exits non-zero", done.returncode != 0, f"rc={done.returncode}")
        combined = (done.stdout + done.stderr)
        check("names the prefix", "soc" in combined, combined.strip())
        check("tells the operator to pass --soc", "--soc" in combined, combined.strip())


def test_duplicate_patch_is_refused() -> None:
    print("the same patch name twice in the composition is refused")
    with tempfile.TemporaryDirectory() as tmp:
        framework, device, soc = build_fixture(pathlib.Path(tmp))
        write_series(device / "patches" / "xnu-12377" / "series",
                     ["device-one.patch", "arch-one.patch"])
        done = run("--framework", str(framework), "--device", str(device), "--soc", str(soc))
        check("exits 1", done.returncode == 1, f"rc={done.returncode}")
        check("names the duplicate", "arch-one.patch" in done.stdout, done.stdout.strip())
        check("says it would apply twice", "twice" in done.stdout, done.stdout.strip())


def test_log_matches() -> None:
    print("a build log with the same patches in the same order is accepted")
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        framework, device, soc = build_fixture(root)
        log = root / "build.log"
        log.write_text(
            "== kernel: patch arch-one.patch\n"
            "== kernel: patch arch-two.patch\n"
            "== kernel: patch sheng-platform-power.patch\n"
            "== kernel: patch native-smp-secondary.patch\n"
            "== kernel: patch zzz-boot-progress.patch\n"
            "== kernel: patch device-one.patch\n",
            encoding="utf-8",
        )
        done = run("--framework", str(framework), "--device", str(device), "--soc", str(soc),
                   "--log", str(log))
        check("exits 0", done.returncode == 0, done.stdout.strip())
        check("reports the match", "OK the composition matches the build: 6 patches, same order"
              in done.stdout, done.stdout.strip())


def test_log_order_mismatch_names_position() -> None:
    print("a log in a different order names the first differing position")
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        framework, device, soc = build_fixture(root)
        log = root / "build.log"
        log.write_text(
            "== kernel: patch arch-one.patch\n"
            "== kernel: patch zzz-boot-progress.patch\n"
            "== kernel: patch arch-two.patch\n"
            "== kernel: patch sheng-platform-power.patch\n"
            "== kernel: patch native-smp-secondary.patch\n"
            "== kernel: patch device-one.patch\n",
            encoding="utf-8",
        )
        done = run("--framework", str(framework), "--device", str(device), "--soc", str(soc),
                   "--log", str(log))
        check("exits 1", done.returncode == 1, f"rc={done.returncode}")
        check("names position 2", "position 2" in done.stdout, done.stdout.strip())
        check("names both names", "arch-two.patch" in done.stdout and "zzz-boot-progress.patch" in done.stdout,
              done.stdout.strip())


def test_log_shorter_reports_both_directions() -> None:
    print("a log missing a patch lists what the composition has and the build does not")
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        framework, device, soc = build_fixture(root)
        log = root / "build.log"
        log.write_text(
            "== kernel: patch arch-one.patch\n"
            "== kernel: patch arch-two.patch\n"
            "== kernel: patch sheng-platform-power.patch\n"
            "== kernel: patch zzz-boot-progress.patch\n"
            "== kernel: patch device-one.patch\n",
            encoding="utf-8",
        )
        done = run("--framework", str(framework), "--device", str(device), "--soc", str(soc),
                   "--log", str(log))
        check("exits 1", done.returncode == 1, f"rc={done.returncode}")
        check("says the composition has more", "composition has more" in done.stdout, done.stdout.strip())
        check("names the missing patch", "only in composition: native-smp-secondary.patch" in done.stdout,
              done.stdout.strip())


def test_help() -> None:
    print("--help answers without touching the trees")
    done = run("--help")
    check("exits 0", done.returncode == 0, done.stderr.strip())
    check("mentions patch_series", "patch_series" in done.stdout, done.stdout.strip()[:200])


def main() -> int:
    for test in (
        test_four_layers_resolve,
        test_device_only_read_is_short,
        test_missing_soc_is_refused,
        test_duplicate_patch_is_refused,
        test_log_matches,
        test_log_order_mismatch_names_position,
        test_log_shorter_reports_both_directions,
        test_help,
    ):
        test()
    if FAILURES:
        print(f"FAILED {len(FAILURES)}: {', '.join(FAILURES)}")
        return 1
    print("TESTS OK: the composition reader resolves four layers and refuses to guess")
    return 0


if __name__ == "__main__":
    sys.exit(main())
