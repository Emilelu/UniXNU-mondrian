#!/usr/bin/env python3
"""The managed-page report must stay compiled out unless someone asks for it (P-233).

The report runs once per segment of every physical mapping and carries a backtrace, so a
board kernel that maps driver-owned pages for GPU buffer views prints tens of thousands of
lines a boot and pushes every other message out of the 128 KiB message buffer. Upstream
already wraps it in NATIVE_QUIET_MANAGED_PAGE_REPORT; this guard keeps the wrapper honest:
the macro is defined, the condition uses it, the print line is still present (so the switch
is a switch, not a deletion), and the patch is actually listed in the series.
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
PATCH = os.path.join(REPO, "patches/xnu/0624-k60-quiet-managed-page-report.patch")
SERIES = os.path.join(REPO, "patches/xnu/series")
NAME = "0624-k60-quiet-managed-page-report.patch"

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def read(path):
    return io.open(path, encoding="utf-8", errors="replace").read()


@case
def test_the_patch_defines_the_macro():
    text = read(PATCH)
    assert "+#define NATIVE_QUIET_MANAGED_PAGE_REPORT 1" in text, "the macro is not defined"


@case
def test_the_condition_uses_the_macro():
    text = read(PATCH)
    assert "+#if (DEBUG || DEVELOPMENT) && !NATIVE_QUIET_MANAGED_PAGE_REPORT" in text, text[:400]
    assert "+#endif /* (DEBUG || DEVELOPMENT) && !NATIVE_QUIET_MANAGED_PAGE_REPORT */" in text


@case
def test_the_report_line_survives_as_context():
    text = read(PATCH)
    assert 'OSReportWithBacktrace("IOMemoryDescriptor physical with managed page' in text
    for line in text.splitlines():
        if "managed page 0x%qx" in line:
            assert not line.startswith(("+", "-")), "the report line was added or deleted, not guarded"


@case
def test_the_series_lists_the_patch():
    names = [line.strip() for line in read(SERIES).splitlines() if line.strip()]
    assert NAME in names, "the patch is not in the series"
    assert names[-1] == NAME, "this patch has to come after the ones it depends on"


@case
def test_the_hunk_is_well_formed():
    text = read(PATCH)
    assert text.startswith("diff --git a/iokit/Kernel/IOMemoryDescriptor.cpp b/"), text[:80]
    assert "@@ -" in text
    assert text.endswith("\n"), "the patch has no trailing newline"


def main():
    failed = 0
    for fn in CASES:
        try:
            fn()
        except AssertionError as exc:
            failed += 1
            print("FAIL %s: %s" % (fn.__name__, exc))
        else:
            print("ok   %s" % fn.__name__)
    print("\nTESTS %s %d case(s) (%d failure(s))" % ("OK" if not failed else "FAILED", len(CASES), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
