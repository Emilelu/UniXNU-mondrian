#!/usr/bin/env python3
"""Structural check for the ADSP region override parser (0613).

The live FDT normally has no /chosen qcom,adsp-region property, so the
big-endian cell decoder can regress without being exercised by a default
build. This test reads the 0613 patch body and checks that the parser keeps
the explicit byte-order decoder and both documented cell shapes.

Run: python3 scripts/tests/test-k60-adsp-region.py
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches" / "xnu" / "0613-k60-adsp-pas.patch"


def fail(message):
    print("FAIL " + message)
    return 1


def function_body(text, name):
    start = text.index("k60_adsp_cell(" if name == "cell" else "k60_adsp_board_region(")
    end = text.index("\n}\n", start)
    return text[start:end]


def main():
    text = "\n".join(line[1:] if line.startswith("+") else line
                     for line in PATCH.read_text(encoding="utf-8").splitlines())
    problems = 0
    cell = function_body(text, "cell")
    for needle in ("p[0] << 24", "p[1] << 16", "p[2] << 8", "p[3]"):
        if needle not in cell:
            problems += fail("k60_adsp_cell lost the big-endian decode: " + needle)
    region = function_body(text, "region")
    if "const uint32_t *cells" in region:
        problems += fail("k60_adsp_board_region regressed to native-endian words")
    if "length == 8" not in region:
        problems += fail("k60_adsp_board_region lost the two-cell form")
    for index in range(4):
        needle = "k60_adsp_cell(prop, %d)" % index
        if needle not in region:
            problems += fail("k60_adsp_board_region lost " + needle)
    if "want_span" not in region or "want_base" not in region:
        problems += fail("k60_adsp_board_region lost the base/span checks")
    if problems:
        print("PROBLEMS %d" % problems)
        return 1
    print("TESTS OK region override parser uses big-endian cells (2 and 4 cell forms)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
