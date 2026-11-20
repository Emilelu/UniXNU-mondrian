#!/usr/bin/env python3
"""Host tests for scripts/check-device-tree.py.

The defect this guards against (P-275) is a device tree that no gate ever
parsed, so the tests must feed the checker real files through real dtc. Every
fixture below writes an actual .dts and, where the source has /include/, an
actual .dtsi -- stubbing dtc would have let the broken tree pass.
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE.parent / "check-device-tree.py"

FAILURES: list[str] = []

GOOD_SOURCE = """/dts-v1/;

/include/ "soc.dtsi"

/ {
	model = "fixture";
	#address-cells = <2>;
	#size-cells = <2>;

	/*
	 * A comment that a merge could lose its opener from.
	 */
	wlan {
		device_type = "wlan";
	};

	bluetooth {
		device_type = "bluetooth";
	};
};
"""

DTSI = """/ {
	soc {
		#address-cells = <2>;
		#size-cells = <2>;
	};
};
"""


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}{(': ' + detail) if detail else ''}")
        FAILURES.append(name)


def board_toml(source: str = "device:dts/board.dts", include: str = "soc:dts") -> str:
    return (
        "[board]\n"
        'os_profile = "ios-27.0.1-24A446"\n'
        "\n"
        "[device_tree]\n"
        f'source = "{source}"\n'
        f'include_dirs = ["{include}"]\n'
    )


def make_tree(root: pathlib.Path, source_text: str = GOOD_SOURCE, with_soc: bool = True,
              with_include_dirs: bool = True) -> tuple[pathlib.Path, pathlib.Path]:
    device = root / "device"
    (device / "dts").mkdir(parents=True)
    (device / "board.toml").write_text(
        board_toml(include="soc:dts" if with_include_dirs else "device:dts"),
        encoding="utf-8",
    )
    (device / "dts" / "board.dts").write_text(source_text, encoding="utf-8")
    if not with_include_dirs:
        (device / "dts" / "soc.dtsi").write_text(DTSI, encoding="utf-8")

    out = root / "out"
    if with_soc:
        feed = out / "feeds" / "UniXNU-sm8475-common-fixture" / "dts"
        feed.mkdir(parents=True)
        (feed / "soc.dtsi").write_text(DTSI, encoding="utf-8")
    return device, out


def run(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *argv],
                          capture_output=True, text=True, check=False)


def need_dtc() -> bool:
    if shutil.which("dtc"):
        return True
    print("  SKIP dtc is not installed; these tests need the real compiler")
    return False


def test_good_tree_compiles() -> None:
    print("a well-formed tree compiles and the feed supplies the include")
    if not need_dtc():
        return
    with tempfile.TemporaryDirectory() as tmp:
        device, out = make_tree(pathlib.Path(tmp))
        done = run("--device", str(device), "--out", str(out))
        check("exits 0", done.returncode == 0, (done.stdout + done.stderr).strip())
        check("reports bytes", "compiles:" in done.stdout and "bytes" in done.stdout, done.stdout.strip())
        check("names the include dir", "UniXNU-sm8475-common-fixture" in done.stdout, done.stdout.strip())


def test_missing_comment_opener_is_caught() -> None:
    """This is the exact 585fe75a shape: a comment body with no opener."""
    print("a comment body whose opener was lost is rejected, with dtc's own line number")
    if not need_dtc():
        return
    broken = GOOD_SOURCE.replace("\t/*\n", "\t\n", 1)
    with tempfile.TemporaryDirectory() as tmp:
        device, out = make_tree(pathlib.Path(tmp), source_text=broken)
        done = run("--device", str(device), "--out", str(out))
        combined = done.stdout + done.stderr
        check("exits 1", done.returncode == 1, f"rc={done.returncode}: {combined.strip()}")
        check("says dtc rejected it", "dtc rejected" in done.stdout, done.stdout.strip())
        check("passes dtc's message through", "syntax error" in combined or "ERROR" in combined,
              combined.strip())
        check("names a line", any(ch.isdigit() for ch in combined), combined.strip())


def test_unbalanced_brace_is_caught() -> None:
    print("an unbalanced brace is rejected")
    if not need_dtc():
        return
    broken = GOOD_SOURCE.replace("\t};\n};\n", "\t};\n", 1)
    with tempfile.TemporaryDirectory() as tmp:
        device, out = make_tree(pathlib.Path(tmp), source_text=broken)
        done = run("--device", str(device), "--out", str(out))
        check("exits 1", done.returncode == 1, f"rc={done.returncode}")
        check("says dtc rejected it", "dtc rejected" in done.stdout, done.stdout.strip())


def test_missing_include_is_no_tree_not_a_pass() -> None:
    print("a feed that does not supply the include is NO TREE, not a silent pass")
    if not need_dtc():
        return
    with tempfile.TemporaryDirectory() as tmp:
        device, out = make_tree(pathlib.Path(tmp), with_soc=False)
        done = run("--device", str(device), "--out", str(out))
        check("exits 2", done.returncode == 2, f"rc={done.returncode}: {done.stdout.strip()}")
        check("says NO TREE", "NO TREE" in done.stdout, done.stdout.strip())
        check("tells the operator to pass --soc", "--soc" in done.stdout, done.stdout.strip())


def test_explicit_soc_wins() -> None:
    print("--soc points at the includes directly and needs no --out")
    if not need_dtc():
        return
    with tempfile.TemporaryDirectory() as tmp:
        device, out = make_tree(pathlib.Path(tmp))
        soc = out / "feeds" / "UniXNU-sm8475-common-fixture"
        done = run("--device", str(device), "--soc", str(soc))
        check("exits 0", done.returncode == 0, (done.stdout + done.stderr).strip())


def test_missing_source_is_no_tree() -> None:
    print("a board.toml whose source is absent is NO TREE")
    if not need_dtc():
        return
    with tempfile.TemporaryDirectory() as tmp:
        device, out = make_tree(pathlib.Path(tmp))
        (device / "dts" / "board.dts").unlink()
        done = run("--device", str(device), "--out", str(out))
        check("exits 2", done.returncode == 2, f"rc={done.returncode}")
        check("says NO TREE", "NO TREE" in done.stdout, done.stdout.strip())


def test_include_dir_without_prefix_comes_from_device() -> None:
    print("an unprefixed include dir resolves inside the device repository")
    if not need_dtc():
        return
    with tempfile.TemporaryDirectory() as tmp:
        device, out = make_tree(pathlib.Path(tmp), with_include_dirs=False)
        done = run("--device", str(device), "--out", str(out))
        check("exits 0", done.returncode == 0, (done.stdout + done.stderr).strip())
        check("names the device dir", str(device / "dts") in done.stdout, done.stdout.strip())


def test_help() -> None:
    print("--help answers without touching the tree")
    done = run("--help")
    check("exits 0", done.returncode == 0, done.stderr.strip())
    check("mentions device_tree", "device_tree" in done.stdout or "device tree" in done.stdout,
          done.stdout.strip()[:200])


def main() -> int:
    for test in (
        test_good_tree_compiles,
        test_missing_comment_opener_is_caught,
        test_unbalanced_brace_is_caught,
        test_missing_include_is_no_tree_not_a_pass,
        test_explicit_soc_wins,
        test_missing_source_is_no_tree,
        test_include_dir_without_prefix_comes_from_device,
        test_help,
    ):
        test()
    if FAILURES:
        print(f"FAILED {len(FAILURES)}: {', '.join(FAILURES)}")
        return 1
    print("TESTS OK: the device tree is compiled before a build, not during one")
    return 0


if __name__ == "__main__":
    sys.exit(main())
