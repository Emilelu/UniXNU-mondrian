#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
# Copyright (c) 2026, UniXNU contributors.
"""Host-only tests for scripts/check-bluetooth-power.py.

Every case builds a synthetic bsd/dev/qbt_k60.c, runs the checker and asserts
the verdict.  The mutations are the ones a careless edit would produce: a step
moved, a step dropped, a delay retuned, a rail voted, a cold boot refused.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts" / "check-bluetooth-power.py"

DEFINES = """#define K60_BT_UART_GIC_SPI 587u
#define K60_BT_UART_GIC_INTID (32u + K60_BT_UART_GIC_SPI)
#define K60_TLMM_GIC_SPI 208u
#define K60_TLMM_GIC_INTID (32u + K60_TLMM_GIC_SPI)
#define K60_BT_EN_LOW_MS 100u
#define K60_BT_EN_HIGH_MS 60u
#define K60_BT_OFF_MS 100u
#define K60_WLAN_OFF_DISCHARGE_MS 100u
"""

ON_BODY = """static int k60_bt_power_on(void) {
    if (!k60.warm_boot) k60_log(NULL, 1, "power: cold boot, rails not voted (k60bt_warm=0)");
    int e = k60_map(&k60.uart, K60_BT_UART_BASE, K60_BT_UART_SIZE);
    if (e) return e;
    k60_uart_pins_idle();
    k60_gpio_output(K60_BT_EN_GPIO, false, K60_TLMM_PULL_DOWN, K60_TLMM_DRIVE_2MA);
    IOSleep(K60_BT_EN_LOW_MS);
    k60.powered = true;
    if (!k60_pin_input(K60_WLAN_EN_GPIO)) IOSleep(K60_WLAN_OFF_DISCHARGE_MS);
    k60_gpio_input(K60_BT_SW_CTRL_GPIO, K60_TLMM_PULL_NONE, K60_TLMM_DRIVE_2MA);
    e = k60_serial_clock(true);
    if (e) return e;
    e = k60_stop_engine();
    if (e) return e;
    e = k60_prepare_engine();
    if (e) return e;
    e = armcpu_spi_attach(K60_BT_UART_GIC_INTID, false, k60_uart_irq, NULL, NULL, NULL);
    if (e) return -EIO;
    e = armcpu_spi_attach(K60_TLMM_GIC_INTID, false, k60_tlmm_irq, NULL, NULL, NULL);
    if (e) return -EIO;
    k60_xo_pulse();
    k60_gpio_output(K60_BT_EN_GPIO, true, K60_TLMM_PULL_DOWN, K60_TLMM_DRIVE_2MA);
    k60_xo_release();
    IOSleep(K60_BT_EN_HIGH_MS);
    k60_uart_pins_active();
    e = qbt_geni_start(&k60.geni);
    if (e) return e;
    return 0;
}
"""

OFF_BODY = """static int k60_bt_power_off(void) {
    qbt_set_service(k60.core, false);
    k60_irq_mask(NULL, true);
    k60_disarm_rx_wake();
    k60_gpio_output(K60_BT_EN_GPIO, false, K60_TLMM_PULL_DOWN, K60_TLMM_DRIVE_2MA);
    IOSleep(K60_BT_OFF_MS);
    (void)k60_stop_engine();
    k60_serial_clock(false);
    return 0;
}
"""

CASES = []


def case(name, expect_ok, mutate=None):
    CASES.append((name, expect_ok, mutate))


def build(mutate=None):
    on, off, defines = ON_BODY, OFF_BODY, DEFINES
    if mutate:
        on, off, defines = mutate(on, off, defines)
    return defines + "\n" + on + "\n" + off


def run(source_text):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "bsd" / "dev").mkdir(parents=True)
        (root / "bsd" / "dev" / "qbt_k60.c").write_text(source_text, encoding="utf-8")
        out = root / "report"
        proc = subprocess.run([sys.executable, str(CHECK), "--tree", str(root),
                               "--out", str(out)],
                              capture_output=True, text=True)
        return proc, out


def expect(proc, ok):
    return (proc.returncode == 0) == ok


# --- the baseline ---------------------------------------------------------
case("the port as written passes", True)
case("an empty tree has no source", False, None)


def move_bt_en_high_first(on, off, d):
    line = "    k60_gpio_output(K60_BT_EN_GPIO, true, K60_TLMM_PULL_DOWN, K60_TLMM_DRIVE_2MA);\n"
    on = on.replace(line, "")
    return (on.replace("    int e = k60_map", line + "    int e = k60_map"), off, d)


case("BT_EN high before the engine is prepared fails", False, move_bt_en_high_first)


def drop_geni(on, off, d):
    return (on.replace("    e = qbt_geni_start(&k60.geni);\n", ""), off, d)


case("a ladder that never starts GENI fails", False, drop_geni)


def drop_pins_idle(on, off, d):
    return (on.replace("    k60_uart_pins_idle();\n", ""), off, d)


case("a ladder that leaves the pins muxed fails", False, drop_pins_idle)


def retune_low(d, value):
    def go(on, off, dd):
        return (on, off, dd.replace("#define K60_BT_EN_LOW_MS 100u",
                                    "#define K60_BT_EN_LOW_MS %du" % value))
    return go


case("a 50 ms BT_EN low hold fails", False, retune_low(None, 50))
case("a 200 ms BT_EN low hold fails", False, retune_low(None, 200))


def retune_high(on, off, d):
    return (on, off, d.replace("#define K60_BT_EN_HIGH_MS 60u",
                               "#define K60_BT_EN_HIGH_MS 50u"))


case("a 50 ms BT_EN high settle fails", False, retune_high)


def bare_spi(on, off, d):
    return (on.replace("K60_BT_UART_GIC_INTID", "K60_BT_UART_GIC_SPI"), off, d)


case("attaching a bare SPI number fails", False, bare_spi)


def vote_rail(on, off, d):
    return (on.replace("    k60_uart_pins_idle();\n",
                       "    k60_uart_pins_idle();\n    pong_rpmh_vote(0x10, 7);\n"), off, d)


case("voting a rail inside the ladder fails", False, vote_rail)


def refuse_cold(on, off, d):
    return (on.replace('k60_log(NULL, 1, "power: cold boot, rails not voted (k60bt_warm=0)");',
                       "return -EOPNOTSUPP;"), off, d)


case("refusing a cold boot fails", False, refuse_cold)


def drop_flag(on, off, d):
    return (on.replace("    k60.powered = true;\n", ""), off, d)


case("dropping the cleanup flag fails", False, drop_flag)


def flag_before_low(on, off, d):
    on = on.replace("    k60.powered = true;\n", "")
    return (on.replace("    k60_gpio_output(K60_BT_EN_GPIO, false",
                       "    k60.powered = true;\n    k60_gpio_output(K60_BT_EN_GPIO, false"),
            off, d)


case("marking powered before BT_EN goes low fails", False, flag_before_low)


def drop_off_step(on, off, d):
    return (on, off.replace("    k60_disarm_rx_wake();\n", ""), d)


case("a power-off that keeps the wake armed fails", False, drop_off_step)


def off_before_mask(on, off, d):
    off = off.replace("    k60_irq_mask(NULL, true);\n", "")
    return (on, off.replace("    qbt_set_service",
                            "    k60_irq_mask(NULL, true);\n    qbt_set_service"), d)


case("masking after the service stops fails", False, off_before_mask)


def intid_literal(on, off, d):
    return (on, off, d.replace("#define K60_BT_UART_GIC_INTID (32u + K60_BT_UART_GIC_SPI)",
                               "#define K60_BT_UART_GIC_INTID 587u"))


case("an INTID without the +32 fails", False, intid_literal)


def wrong_spi(on, off, d):
    return (on, off, d.replace("#define K60_BT_UART_GIC_SPI 587u",
                               "#define K60_BT_UART_GIC_SPI 619u"))


case("a wrong UART SPI fails", False, wrong_spi)


def comment_only(on, off, d):
    """A rail vote named only in a comment still passes: prose is not code."""
    return (on.replace("    k60_uart_pins_idle();\n",
                       "    k60_uart_pins_idle(); /* never votes a rail */\n"), off, d)


case("a comment mentioning the rail is not a vote", True, comment_only)


def main():
    failures = 0
    for name, expect_ok, mutate in CASES:
        if mutate is None and name.startswith("an empty"):
            with tempfile.TemporaryDirectory() as tmp:
                proc = subprocess.run([sys.executable, str(CHECK), "--tree", tmp],
                                      capture_output=True, text=True)
                ok = proc.returncode != 0
        else:
            proc, out = run(build(mutate))
            ok = expect(proc, expect_ok)
            if expect_ok and ok and out.exists():
                import json
                payload = json.loads((out / "report.json").read_text())
                ok = payload["passed"] is True and payload["hardware_verified"] is False
        print(("PASS" if ok else "FAIL") + " " + name)
        if not ok:
            failures += 1
            print(proc.stdout[-800:])
            print(proc.stderr[-400:])
    if failures:
        print("TESTS FAILED: %d case(s)" % failures)
        return 1
    print("TESTS OK %d case(s)" % len(CASES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
