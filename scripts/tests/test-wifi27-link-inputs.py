#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Self-test for scripts/check-wifi27-link-inputs.py.

Each assertion has a failure that looks like success: an arm64 archive links
with a warning and zero symbols, a scratch stub archive links with hand-written
definitions, and a renamed stub archive passes every path test. The cases pin
each of those, plus the -l resolution the real link record depends on, so a
broken parser cannot pass vacuously.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check-wifi27-link-inputs.py"

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def load():
    spec = importlib.util.spec_from_file_location("check_wifi27_link_inputs", CHECKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def fake_ar(root: Path) -> str:
    """A .py tool is run by sys.executable, so the check needs no POSIX shell."""
    ar = root / "ar.py"
    ar.write_text(
        "import sys\n"
        "if sys.argv[1] == 't':\n"
        "    print('member.o')\n"
        "elif sys.argv[1] == 'p':\n"
        "    sys.stdout.buffer.write(open(sys.argv[2], 'rb').read())\n",
        encoding="utf-8")
    (root / "nm.py").write_text("import sys\n", encoding="utf-8")
    return str(ar)


def obj(cpusubtype: int) -> bytes:
    return struct.pack("<IIIIIIII", 0xFEEDFACF, 0x0100000C, cpusubtype, 1, 0, 0, 0, 0)


def archive(root: Path, name: str, cpusubtype: int = 0x80000002) -> Path:
    path = root / name
    path.write_bytes(obj(cpusubtype))
    return path


def run(root: Path, record: Path, ar: str, extra: list[str]) -> tuple[int, str, str]:
    checker = load()
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = checker.main(["--link-record", str(record), "--ar", ar, "--nm", str(root / "nm.py")] + extra)
    return code, out.getvalue(), err.getvalue()


@case
def good_archives_under_a_root_pass():
    root = Path(tempfile.mkdtemp())
    one, two = archive(root, "libOne.a"), archive(root, "libTwo.a")
    record = root / "linkarchives"
    record.write_text(f"-Wl,-force_load,{one} -Wl,-force_load,{two}\n", encoding="utf-8")
    code, out, err = run(root, record, fake_ar(root), ["--allow-root", str(root)])
    assert code == 0, (code, out, err)
    assert "PASS arch: 2 archives, arm64e" in out, out
    assert "PASS provenance: 2 archives declared" in out, out


@case
def an_arm64_member_fails_the_arch_assertion():
    root = Path(tempfile.mkdtemp())
    good, bad = archive(root, "libGood.a"), archive(root, "libBad.a", cpusubtype=0)
    record = root / "linkarchives"
    record.write_text(f"-Wl,-force_load,{good} -Wl,-force_load,{bad}\n", encoding="utf-8")
    code, out, err = run(root, record, fake_ar(root), ["--allow-root", str(root)])
    assert code == 1, (code, out, err)
    assert "FAIL arch" in out and "libBad.a(member.o) is not arm64e" in out, out


@case
def an_archive_outside_every_root_fails_provenance():
    root = Path(tempfile.mkdtemp())
    outside = Path(tempfile.mkdtemp())
    stray = archive(outside, "libStray.a")
    record = root / "linkarchives"
    record.write_text(f"-Wl,-force_load,{stray}\n", encoding="utf-8")
    code, out, err = run(root, record, fake_ar(root), ["--allow-root", str(root)])
    assert code == 1, (code, out, err)
    assert "FAIL provenance" in out and "outside every declared root" in out, out


@case
def a_stub_name_is_refused_before_the_root_matters():
    root = Path(tempfile.mkdtemp())
    stub = archive(root, "libStub27.a")
    record = root / "linkarchives"
    record.write_text(f"-Wl,-force_load,{stub}\n", encoding="utf-8")
    code, out, err = run(root, record, fake_ar(root), ["--allow-root", str(root)])
    assert code == 1, (code, out, err)
    assert "named like a scratch stub" in out, out


@case
def a_declared_sha_that_disagrees_fails():
    root = Path(tempfile.mkdtemp())
    good = archive(root, "libGood.a")
    record = root / "linkarchives"
    record.write_text(f"-Wl,-force_load,{good}\n", encoding="utf-8")
    declared = root / "declared.txt"
    declared.write_text(f"{'00' * 32} {good}\n", encoding="utf-8")
    code, out, err = run(root, record, fake_ar(root), ["--declared", str(declared)])
    assert code == 1, (code, out, err)
    assert "does not match" in out, out


@case
def a_missing_archive_is_a_refusal_not_a_skip():
    root = Path(tempfile.mkdtemp())
    record = root / "linkarchives"
    record.write_text(f"-Wl,-force_load,{root / 'gone.a'}\n", encoding="utf-8")
    code, out, err = run(root, record, fake_ar(root), ["--allow-root", str(root)])
    assert code == 1, (code, out, err)
    assert "does not exist" in out, out


@case
def a_missing_record_is_named_and_refused():
    root = Path(tempfile.mkdtemp())
    missing = root / "no-such-linkarchives"
    code, out, err = run(root, missing, fake_ar(root), ["--allow-root", str(root)])
    assert code == 2, (code, out, err)
    assert "FAIL record:" in err and str(missing) in err, err
    assert "PASS" not in out, out


@case
def a_dash_l_is_resolved_through_the_L_flag():
    root = Path(tempfile.mkdtemp())
    archive(root, "libfirehose_kernel.a")
    record = root / "linkarchives"
    record.write_text(f"-L{root} -lfirehose_kernel\n", encoding="utf-8")
    code, out, err = run(root, record, fake_ar(root), ["--allow-root", str(root)])
    assert code == 0, (code, out, err)
    assert "PASS arch: 1 archives, arm64e" in out, out


@case
def a_renamed_archive_that_defines_a_stub_symbol_is_refused():
    root = Path(tempfile.mkdtemp())
    stub = archive(root, "libInputs.a")
    record = root / "linkarchives"
    record.write_text(f"-Wl,-force_load,{stub}\n", encoding="utf-8")
    ar = fake_ar(root)
    (root / "nm.py").write_text("import sys\nprint('_psci_smp_init T 0 0')\n", encoding="utf-8")
    code, out, err = run(root, record, ar, ["--allow-root", str(root)])
    assert code == 1, (code, out, err)
    assert "FAIL stubs" in out and "_psci_smp_init" in out, out
    assert "named like a scratch stub" not in out, out


def main() -> int:
    failed = 0
    for fn in CASES:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as error:
            failed += 1
            print(f"FAIL {fn.__name__}: {error}")
    print(f"{len(CASES) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
