#!/usr/bin/env python3
"""Guard the K60 SMCCC wrapper's register contract.

The secure monitor is allowed to clobber x4..x17 on every call, and it hands a
session cookie back in x6.  The wrapper that only declared x0..x3 as outputs
let the compiler keep live values in the other caller-saved registers across
the smc, which corrupts the caller after a successful or interrupted PAS call.
The fix is a property of the calling convention, not of one kernel version, so
it is guarded by text: the driver source and the patch that carries the same
code into XNU must both list x0..x7 as read-write and x8..x17 as clobbered.

Usage: python3 scripts/tests/test-k60-adsp-smccc.py
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
COPIES = [
    ROOT / "drivers" / "PongPower" / "K60AdspPas.c",
    ROOT / "patches" / "xnu" / "0613-k60-adsp-pas.patch",
]
ASM_HEAD = "__asm__ volatile(\"smc #0\""
READ_WRITE = ': "+r"(x0), "+r"(x1), "+r"(x2), "+r"(x3), "+r"(x4), "+r"(x5),'
CLOBBER = ': "x8", "x9", "x10", "x11", "x12", "x13", "x14", "x15", "x16",'
COOKIE = re.compile(r'register uint64_t x6 __asm__\("x6"\)')
checks = 0
failures = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global checks, failures
    checks += 1
    if not ok:
        failures += 1
        print("FAIL " + name + (": " + detail if detail else ""))


def text_of(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def audit(label: str, text: str) -> None:
    sites = text.count(ASM_HEAD)
    check(label + " has exactly one smc site", sites == 1, str(sites))
    check(label + " marks x0..x5 read-write in one operand line", READ_WRITE in text)
    check(label + " marks x6/x7 read-write on the continuation line",
          '"+r"(x6), "+r"(x7)' in text)
    check(label + " clobbers x8..x16", CLOBBER in text)
    check(label + " clobbers x17 and memory", '"x17", "memory"' in text)
    check(label + " names the cookie register", bool(COOKIE.search(text)))
    check(label + " no longer binds x4..x7 as inputs only",
          ': "r"(x4), "r"(x5), "r"(x6), "r"(x7)' not in text)
    check(label + " explains why the clobber list is complete",
          "SMCCC" in text and "x4..x17" in text)


def main() -> int:
    for copy in COPIES:
        check(copy.name + " exists", copy.is_file(), str(copy))
        if copy.is_file():
            audit(copy.name, text_of(copy))

    # The old shape must fail the same audit: a gate that cannot go red is not one.
    fixture = ROOT / "build" / "smccc-gate"
    fixture.mkdir(parents=True, exist_ok=True)
    old = fixture / "old-wrapper.c"
    old.write_text(
        'static int\nk60_scm_call(void)\n{\n'
        '\tregister uint64_t x0 __asm__("x0") = 0;\n'
        '\tregister uint64_t x1 __asm__("x1") = 0;\n'
        '\tregister uint64_t x2 __asm__("x2") = 0;\n'
        '\tregister uint64_t x3 __asm__("x3") = 0;\n'
        '\tregister uint64_t x4 __asm__("x4") = 0;\n'
        '\tregister uint64_t x5 __asm__("x5") = 0;\n'
        '\tregister uint64_t x6 __asm__("x6") = 0;\n'
        '\tregister uint64_t x7 __asm__("x7") = 0;\n'
        '\t__asm__ volatile("smc #0"\n'
        '\t    : "+r"(x0), "+r"(x1), "+r"(x2), "+r"(x3)\n'
        '\t    : "r"(x4), "r"(x5), "r"(x6), "r"(x7)\n'
        '\t    : "memory");\n}\n', encoding="utf-8")
    text = text_of(old)
    check("the old operand shape is rejected", READ_WRITE not in text)
    check("the old shape has no x8..x17 clobber", '"x17", "memory"' not in text)

    verdict = f"TESTS OK {checks} checks" if failures == 0 else \
        f"TESTS OK {checks} checks ({failures} failure(s))"
    print(verdict)
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
