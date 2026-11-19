#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Host tests for scripts/check-audio27-kernel-api.py.

The checker answers one question - are the four interfaces the wiring table names
still declared in this XNU tree - and these cases hold it to four properties:
it says yes when all four are there, it names what is missing, it accepts both
tree layouts, and it does not count the headers the wiring itself installs.
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE.parent / "check-audio27-kernel-api.py"
NAMES = ["ml_io_map", "ml_io_map_wcomb", "PE_parse_boot_argn", "delay_for_interval"]
HEADERS = {
    "osfmk/arm/machine_routines.h": ["extern vm_offset_t ml_io_map(vm_offset_t, vm_size_t);",
                                     "extern vm_offset_t ml_io_map_wcomb(vm_offset_t, vm_size_t);"],
    "pexpert/pexpert/pexpert.h": ["extern boolean_t PE_parse_boot_argn(const char *, void *, int);"],
    "osfmk/kern/clock.h": ["extern void delay_for_interval(uint32_t, uint32_t);"],
}


def build(root, inplace=False, headers=None, names=None):
    base = root if inplace else root / ".cache/xnu-work"
    (base / "bsd/conf").mkdir(parents=True, exist_ok=True)
    (base / "bsd/conf/files").write_text("bsd/dev/unix_startup.c\t\t\tstandard\n")
    for rel, lines in (headers or HEADERS).items():
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n")
    return base


def run(tree):
    done = subprocess.run([sys.executable, str(SCRIPT), str(tree)],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          universal_newlines=True)
    return done.returncode, done.stdout


def case_all_present():
    root = pathlib.Path(tempfile.mkdtemp(prefix="k60-api-"))
    try:
        build(root)
        code, out = run(root)
        assert code == 0, out
        assert "API OK 4/4" in out, out
        assert "osfmk/arm/machine_routines.h:1" in out, out
        return "all four declared: API OK 4/4"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def case_one_missing():
    root = pathlib.Path(tempfile.mkdtemp(prefix="k60-api-"))
    try:
        headers = dict(HEADERS)
        del headers["osfmk/kern/clock.h"]
        build(root, headers=headers)
        code, out = run(root)
        assert code == 1, out
        assert "API FAILED" in out and "delay_for_interval" in out, out
        assert "1 of 4" in out, out
        return "one missing: named in the failure"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def case_inplace_layout():
    root = pathlib.Path(tempfile.mkdtemp(prefix="k60-api-"))
    try:
        build(root, inplace=True)
        code, out = run(root)
        assert code == 0, out
        assert "API OK 4/4" in out, out
        return "in place layout: same verdict"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def case_wired_headers_do_not_count():
    root = pathlib.Path(tempfile.mkdtemp(prefix="k60-api-"))
    try:
        headers = {"bsd/dev/PongAudioRegs.h": ["extern vm_offset_t ml_io_map(vm_offset_t, vm_size_t);"],
                   "osfmk/arm/machine_routines.h": ["extern vm_offset_t ml_io_map_wcomb(vm_offset_t, vm_size_t);"],
                   "pexpert/pexpert/pexpert.h": ["extern boolean_t PE_parse_boot_argn(const char *, void *, int);"],
                   "osfmk/kern/clock.h": ["extern void delay_for_interval(uint32_t, uint32_t);"]}
        build(root, headers=headers)
        code, out = run(root)
        assert code == 1, "the glue's own header is not the kernel: " + out
        assert "ml_io_map," in out or "ml_io_map\n" in out, out
        return "wired headers skipped: ml_io_map stays missing"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def case_signature_drift():
    root = pathlib.Path(tempfile.mkdtemp(prefix="k60-api-"))
    try:
        headers = dict(HEADERS)
        headers["osfmk/kern/clock.h"] = ["extern void delay_for_interval(uint32_t);"]
        build(root, headers=headers)
        code, out = run(root)
        assert code == 1, "a changed signature is not the declaration the glue assumes: " + out
        assert "SIGNATURE CHANGED" in out, out
        assert "delay_for_interval" in out, out
        return "signature drift: reported, not silently accepted"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def case_unseeded():
    root = pathlib.Path(tempfile.mkdtemp(prefix="k60-api-"))
    try:
        code, out = run(root)
        assert code == 1, out
        assert "no bsd/conf/files" in out, out
        return "unseeded tree: refused"
    finally:
        shutil.rmtree(root, ignore_errors=True)


CASES = [case_all_present, case_one_missing, case_inplace_layout,
         case_wired_headers_do_not_count, case_signature_drift, case_unseeded]


def main():
    failures = 0
    for case in CASES:
        try:
            print("  ok   %s" % case())
        except AssertionError as exc:
            failures += 1
            print("  FAIL %s: %s" % (case.__name__, exc))
    if failures:
        print("FAILED: %d case(s)" % failures)
        return 1
    print("TESTS OK %d cases" % len(CASES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
