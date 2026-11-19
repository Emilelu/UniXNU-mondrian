#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
# Copyright (c) 2026, UniXNU contributors.
"""Check the K60 Bluetooth power ladder against the official bring-up order.

unixnu.com/zh/porting/bluetooth step 2 fixes the order: BT_EN low, serial
clock, QUP engine, interrupts, BT_EN high, pins, GENI start.  The K60 backend
carries that order in k60_bt_power_on()/k60_bt_power_off() in
bsd/dev/qbt_k60.c, plus two local deviations that must stay visible:

  * the delays are 50/50 ms here, not the 100/60 ms of the page;
  * the ladder never votes a PMIC rail (0511: RPMh/RSC is out of reach), so a
    cold boot only logs that the rails were not voted.

This checker reads the source, extracts both functions and asserts the order
and the invariants.  It is a text check: it proves the code still says what
the port decided, not that the hardware followed it.

  python3 scripts/check-bluetooth-power.py [--tree DIR] [--source FILE]
                                          [--out DIR]
"""

import argparse
import json
import re
import sys
from pathlib import Path

CANDIDATES = [
    "bsd/dev/qbt_k60.c",
]

ON = "k60_bt_power_on"
OFF = "k60_bt_power_off"

# The ladder, in the order the page fixes.  Each entry is (label, needle).
# A needle may match anywhere inside the extracted body.
ON_ORDER = [
    ("map the register windows", "k60_map(&k60.uart"),
    ("park the UART pins", "k60_uart_pins_idle();"),
    ("drive BT_EN low", "k60_gpio_output(K60_BT_EN_GPIO, false"),
    ("hold BT_EN low", "IOSleep(K60_BT_EN_LOW_MS);"),
    ("release the shared rail discharge", "k60_pin_input(K60_WLAN_EN_GPIO)"),
    ("park BT_SW_CTRL as input", "k60_gpio_input(K60_BT_SW_CTRL_GPIO"),
    ("start the serial clock", "k60_serial_clock(true)"),
    ("stop the QUP engine", "k60_stop_engine()"),
    ("prepare the QUP engine", "k60_prepare_engine()"),
    ("attach the UART interrupt", "armcpu_spi_attach(K60_BT_UART_GIC_INTID"),
    ("attach the wake interrupt", "armcpu_spi_attach(K60_TLMM_GIC_INTID"),
    ("pulse the XO latch", "k60_xo_pulse();"),
    ("drive BT_EN high", "k60_gpio_output(K60_BT_EN_GPIO, true"),
    ("release the XO latch", "k60_xo_release();"),
    ("settle BT_EN high", "IOSleep(K60_BT_EN_HIGH_MS);"),
    ("mux the UART pins", "k60_uart_pins_active();"),
    ("start GENI", "qbt_geni_start(&k60.geni)"),
]

OFF_ORDER = [
    ("stop the H4 service", "qbt_set_service(k60.core, false)"),
    ("mask the interrupts", "k60_irq_mask(NULL, true)"),
    ("disarm the wake interrupt", "k60_disarm_rx_wake()"),
    ("drive BT_EN low", "k60_gpio_output(K60_BT_EN_GPIO, false"),
    ("hold BT_EN low", "IOSleep(K60_BT_OFF_MS);"),
    ("stop the QUP engine", "k60_stop_engine()"),
    ("drop the serial clock", "k60_serial_clock(false)"),
]

# 0517 aligned the two settle delays with the page (100 ms low, 60 ms high);
# the off and discharge delays are this board's own.  The values are part of
# the port decision, so a silent change is a failure.
DELAYS = {
    "K60_BT_EN_LOW_MS": 100,
    "K60_BT_EN_HIGH_MS": 60,
    "K60_BT_OFF_MS": 100,
    "K60_WLAN_OFF_DISCHARGE_MS": 100,
}

FORBIDDEN = [
    ("rpmh", "the ladder must not touch RPMh"),
    ("spmi", "the ladder must not touch SPMI"),
    ("pmic", "the ladder must not touch the PMIC"),
]


class Report:
    def __init__(self):
        self.rows = []
        self.failures = 0

    def add(self, ok, label, detail=""):
        self.rows.append({"ok": bool(ok), "check": label, "detail": detail})
        if not ok:
            self.failures += 1
        mark = "PASS" if ok else "FAIL"
        line = "%-4s %s" % (mark, label)
        if detail:
            line += "  (%s)" % detail
        print(line)
        return ok


def find_source(tree, explicit):
    if explicit:
        p = Path(explicit)
        if not p.is_file():
            raise SystemExit("bluetooth-power: no such source: %s" % p)
        return p
    root = Path(tree).resolve()
    for rel in CANDIDATES:
        p = root / rel
        if p.is_file():
            return p
    raise SystemExit("bluetooth-power: no %s under %s"
                     % (" or ".join(CANDIDATES), root))


def extract_function(text, name):
    """Return the body of a top-level function, braces balanced."""
    match = re.search(r"^[A-Za-z_][A-Za-z0-9_ \t*]*\b" + name + r"\s*\([^;{]*\)\s*\{",
                      text, re.MULTILINE)
    if not match:
        return None
    start = text.index("{", match.start())
    depth = 0
    i = start
    while i < len(text):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    return None


def strip_comments(text):
    """Drop C and C++ comments so prose cannot satisfy a token check."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", " ", text)


def define_value(text, name):
    m = re.search(r"^#define\s+" + name + r"\s+(\d+)u?\b", text, re.MULTILINE)
    return int(m.group(1)) if m else None


def check_order(report, body, order, label):
    positions = []
    missing = []
    for name, needle in order:
        at = body.find(needle)
        if at < 0:
            missing.append(name)
        positions.append((name, at))
    if missing:
        report.add(False, "%s: every step is present" % label,
                   "missing: " + ", ".join(missing))
        return
    report.add(True, "%s: every step is present" % label,
               "%d steps" % len(order))
    ordered = all(positions[i][1] < positions[i + 1][1]
                  for i in range(len(positions) - 1))
    if not ordered:
        first = next(i for i in range(len(positions) - 1)
                     if positions[i][1] > positions[i + 1][1])
        report.add(False, "%s: the steps run in the official order" % label,
                   "%s runs after %s" % (positions[first][0], positions[first + 1][0]))
    else:
        report.add(True, "%s: the steps run in the official order" % label)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tree", default=".")
    ap.add_argument("--source")
    ap.add_argument("--out")
    args = ap.parse_args(argv)

    src = find_source(args.tree, args.source)
    text = src.read_text(encoding="utf-8", errors="replace")
    report = Report()
    report.add(True, "source", str(src))

    on = extract_function(text, ON)
    off = extract_function(text, OFF)
    report.add(on is not None, "k60_bt_power_on() is present")
    report.add(off is not None, "k60_bt_power_off() is present")
    if on is None or off is None:
        return finish(report, args.out, src)

    check_order(report, on, ON_ORDER, "power on")
    check_order(report, off, OFF_ORDER, "power off")

    # 0518: the SPI number is 587 and 208; the GIC wants INTID = 32 + SPI.
    for name, spi in (("K60_BT_UART_GIC_SPI", 587), ("K60_TLMM_GIC_SPI", 208)):
        got = define_value(text, name)
        report.add(got == spi, "%s is %d" % (name, spi), "got %s" % got)
    report.add(bool(re.search(r"#define\s+K60_BT_UART_GIC_INTID\s+\(\s*32u?\s*\+\s*K60_BT_UART_GIC_SPI\s*\)", text)),
               "K60_BT_UART_GIC_INTID adds 32")
    report.add(bool(re.search(r"#define\s+K60_TLMM_GIC_INTID\s+\(\s*32u?\s*\+\s*K60_TLMM_GIC_SPI\s*\)", text)),
               "K60_TLMM_GIC_INTID adds 32")
    report.add("armcpu_spi_attach(K60_BT_UART_GIC_SPI" not in on and
               "armcpu_spi_attach(K60_TLMM_GIC_SPI" not in on,
               "the attach calls pass an INTID, not a bare SPI")

    for name, want in DELAYS.items():
        got = define_value(text, name)
        report.add(got == want, "%s is %d ms" % (name, want), "got %s" % got)

    bare_on = strip_comments(on).lower()
    bare_off = strip_comments(off).lower()
    for token, why in FORBIDDEN:
        report.add(token not in bare_on and token not in bare_off,
                   "the ladder leaves %s alone" % token, why)

    # 0511: a cold boot continues and says once that no rail was voted.
    report.add("rails not voted" in on, "a cold boot logs that no rail was voted")
    report.add("-EOPNOTSUPP" not in on, "a cold boot is not refused")
    report.add("k60.powered = true" in on and
               on.index("k60.powered = true") > on.index("IOSleep(K60_BT_EN_LOW_MS)"),
               "the cleanup flag is set after BT_EN goes low")

    return finish(report, args.out, src)


def finish(report, out, src):
    if out:
        dest = Path(out)
        dest.mkdir(parents=True, exist_ok=True)
        payload = {
            "checker": "check-bluetooth-power",
            "source": str(src),
            "passed": report.failures == 0,
            "failures": report.failures,
            "checks": report.rows,
            "hardware_verified": False,
        }
        (dest / "report.json").write_text(json.dumps(payload, indent=2) + "\n",
                                          encoding="utf-8")
    if report.failures:
        print("bluetooth-power: FAIL (%d failure(s))" % report.failures)
        return 1
    print("bluetooth-power: OK (%d check(s))" % len(report.rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
