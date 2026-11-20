#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Host tests for scripts/check-audio27-stubs.py.

The fixtures are small XNU-shaped trees: one that declares the five names the
way the stub headers do, and variants that drift one declaration at a time.
"""
import pathlib
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[2]
CHECK = REPO / "scripts/check-audio27-stubs.py"

MACHINE_ROUTINES = (
    "vm_offset_t ml_io_map(vm_offset_t phys_addr,\n"
    "\tvm_size_t size);\n"
    "vm_offset_t ml_io_map_wcomb(vm_offset_t phys_addr,\n"
    "\tvm_size_t size);\n"
)
CLOCK = (
    "#include <mach/clock_types.h>\n"
    "extern void delay_for_interval(\n"
    "\tuint32_t interval,\n"
    "\tuint32_t scale_factor);\n"
    "#define NSEC_PER_USEC 1000ull\n"
)
PEXPERT = (
    "extern boolean_t PE_parse_boot_argn(\n"
    "\tconst char *arg_string,\n"
    "\tvoid *arg_ptr,\n"
    "\tint max_arg);\n"
)
PROTOS = "extern int printf(const char *format, ...) __printflike(1, 2);\n"
MACRO = (
    "#define PKT_LOG(level, fmt, ...) \\\n"
    "do { \\\n"
    "\tif (level) \\\n"
    "\t\tprintf(\"%s:%d \" fmt \"\\n\", __LINE__, ##__VA_ARGS__); \\\n"
    "} while (0)\n"
)


def tree(root, clock=CLOCK, protos=PROTOS, pexpert=PEXPERT):
    (root / "bsd/conf").mkdir(parents=True, exist_ok=True)
    (root / "bsd/conf/files").write_text("bsd/dev/unix_startup.c\t\t\tstandard\n")
    (root / "bsd/net").mkdir(parents=True, exist_ok=True)
    (root / "bsd/net/packet_mangler.h").write_text(MACRO)
    (root / "osfmk/arm").mkdir(parents=True, exist_ok=True)
    (root / "osfmk/arm/machine_routines.h").write_text(MACHINE_ROUTINES)
    (root / "osfmk/kern").mkdir(parents=True, exist_ok=True)
    (root / "osfmk/kern/clock.h").write_text(clock)
    (root / "osfmk/kern/misc_protos.h").write_text(protos)
    (root / "pexpert/pexpert").mkdir(parents=True, exist_ok=True)
    (root / "pexpert/pexpert/pexpert.h").write_text(pexpert)
    return root


def run(*args):
    done = subprocess.run([sys.executable, str(CHECK)] + [str(a) for a in args],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          universal_newlines=True)
    return done.returncode, done.stdout


def case_match():
    root = tree(pathlib.Path(tempfile.mkdtemp()) / "x")
    code, out = run(root)
    assert code == 0, out
    assert "STUBS OK 5/5 declarations match" in out, out


def case_drift():
    wide = CLOCK.replace("uint32_t interval", "uint64_t interval").replace(
        "uint32_t scale_factor", "uint64_t scale_factor")
    root = tree(pathlib.Path(tempfile.mkdtemp()) / "x", clock=wide)
    code, out = run(root)
    assert code == 1, out
    assert "STUB DRIFT: delay_for_interval" in out, out
    assert "uint64_t, uint64_t" in out and "uint32_t, uint32_t" in out, out


def case_macro_is_not_a_declaration():
    """printf appears in a macro body first; the prototype must still win."""
    root = tree(pathlib.Path(tempfile.mkdtemp()) / "x")
    code, out = run(root)
    assert code == 0, out
    assert "printf" not in out, out


def case_missing_name():
    root = tree(pathlib.Path(tempfile.mkdtemp()) / "x", protos="")
    code, out = run(root)
    assert code == 1, out
    assert "the tree does not declare printf" in out, out


def case_not_a_tree():
    empty = pathlib.Path(tempfile.mkdtemp()) / "x"
    empty.mkdir()
    code, out = run(empty)
    assert code == 1, out
    assert "no bsd/conf/files" in out, out


def main():
    cases = [case_match, case_drift, case_macro_is_not_a_declaration,
             case_missing_name, case_not_a_tree]
    for case in cases:
        case()
    print("TESTS OK %d cases" % len(cases))


if __name__ == "__main__":
    main()
