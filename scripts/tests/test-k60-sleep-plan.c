/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* Offline check of the K60 platform-sleep mask and wake arithmetic. The
 * register values are synthetic: the board hook has not been written, so the
 * expectations pin the documented TLMM/PON meaning, not a measured sleep. */
#include <stdio.h>
#include <string.h>
#include "../../drivers/PongPower/K60SleepPlan.h"

static unsigned failures, checks;

static void check(const char *name, long got, long want)
{
    ++checks;
    if (got != want) {
        ++failures;
        printf("FAIL %s: got %ld want %ld\n", name, got, want);
    }
}

static void check_text(const char *name, const char *got, const char *want)
{
    ++checks;
    if (!got || strcmp(got, want)) {
        ++failures;
        printf("FAIL %s: got %s want %s\n", name, got ? got : "(null)", want);
    }
}

int main(void)
{
    /* AP pin, enabled, level: 0x63. Pin 0 targets another processor. */
    uint32_t cfg[40], out[40];
    for (unsigned i = 0; i < 40; ++i) { cfg[i] = 0x63; out[i] = 0xaaaaaaaa; }
    cfg[0] = 0x43;  /* target 2, enabled: not ours, keep it */
    cfg[5] = 0x62;  /* already disabled */

    check("count 40", k60_sleep_mask_tlmm(cfg, 40, out, 40), 40);
    check("ap pin masked", out[1], 0x62);
    check("other target kept", out[0], 0x43);
    check("disabled kept", out[5], 0x62);
    check("reserved 28 kept", out[28], 0x63);
    check("reserved 31 kept", out[31], 0x63);
    check("usable 32 masked", out[32], 0x62);
    check("reserved 36 kept", out[36], 0x63);
    check("reserved 39 kept", out[39], 0x63);
    check("mask tail", out[27], 0x62);

    for (unsigned i = 0; i < 40; ++i) out[i] = 0xaaaaaaaa;
    check("tight capacity", k60_sleep_mask_tlmm(cfg, 40, out, 39), 0);
    check("tight capacity untouched", out[0], 0xaaaaaaaa);
    check("null cfg", k60_sleep_mask_tlmm(0, 40, out, 40), 0);
    check("null out", k60_sleep_mask_tlmm(cfg, 40, 0, 40), 0);
    check("zero count", k60_sleep_mask_tlmm(cfg, 0, out, 40), 0);

    check("pin 0 usable", k60_sleep_pin_usable(0), 1);
    check("pin 27 usable", k60_sleep_pin_usable(27), 1);
    check("pin 28 reserved", k60_sleep_pin_usable(28), 0);
    check("pin 31 reserved", k60_sleep_pin_usable(31), 0);
    check("pin 32 usable", k60_sleep_pin_usable(32), 1);
    check("pin 35 usable", k60_sleep_pin_usable(35), 1);
    check("pin 36 reserved", k60_sleep_pin_usable(36), 0);
    check("pin 39 reserved", k60_sleep_pin_usable(39), 0);
    check("pin 40 usable", k60_sleep_pin_usable(40), 1);
    check("last pin usable", k60_sleep_pin_usable(K60_SLEEP_GPIO_COUNT - 1), 1);
    check("past last pin", k60_sleep_pin_usable(K60_SLEEP_GPIO_COUNT), 0);

    check("pending set", k60_sleep_pin_pending(1), 1);
    check("pending clear", k60_sleep_pin_pending(0), 0);
    check("pending upper bits", k60_sleep_pin_pending(0xffffffffu), 1);
    check("pending only bit0 off", k60_sleep_pin_pending(0xfffffff0u), 0);

    check("power idle", k60_sleep_power_wakes(0, 0), 0);
    check("power realtime", k60_sleep_power_wakes(0x80, 0), 1);
    check("power latched", k60_sleep_power_wakes(0, 0x80), 1);
    check("power other bits", k60_sleep_power_wakes(0x7f, 0x7f), 0);
    check("power both", k60_sleep_power_wakes(0x80, 0x80), 1);

    {
        int pending = 0;
        check("first press passes", k60_sleep_swallow(&pending, 1), 1);
        check("no pending after pass", pending, 0);
        pending = 1;
        check("wake press dropped", k60_sleep_swallow(&pending, 1), 0);
        check("still pending", pending, 1);
        check("release dropped", k60_sleep_swallow(&pending, 0), 0);
        check("pending cleared", pending, 0);
        check("next press passes", k60_sleep_swallow(&pending, 1), 1);
        check("null pending", k60_sleep_swallow(0, 1), 1);
    }

    check("deadline disabled", k60_sleep_deadline_reached(100, 0), 0);
    check("deadline early", k60_sleep_deadline_reached(99, 100), 0);
    check("deadline exact", k60_sleep_deadline_reached(100, 100), 1);
    check("deadline late", k60_sleep_deadline_reached(101, 100), 1);

    check_text("woke power", k60_sleep_woke_by(0, K60WakePower), "power");
    check_text("woke timer source", k60_sleep_woke_by(0, K60WakeTimer), "timer");
    check_text("woke source wins", k60_sleep_woke_by(K60_SLEEP_ARMCPU_STORM, K60WakePower), "power");
    check_text("woke armcpu timer", k60_sleep_woke_by(K60_SLEEP_ARMCPU_TIMER, K60WakeNone), "timer");
    check_text("woke storm", k60_sleep_woke_by(K60_SLEEP_ARMCPU_STORM, K60WakeNone), "storm");
    check_text("woke nothing", k60_sleep_woke_by(0, K60WakeNone), "nothing");

    check("watchdog early", k60_sleep_watchdog_due(9999, 0), 0);
    check("watchdog due", k60_sleep_watchdog_due(10000, 0), 1);
    check("watchdog late", k60_sleep_watchdog_due(10001, 0), 1);
    check("watchdog backwards", k60_sleep_watchdog_due(5, 10), 0);

    check("wake-after off", (long)k60_sleep_wake_after_ms(0), 0);
    check("wake-after one", (long)k60_sleep_wake_after_ms(1), 1000);
    check("wake-after thirty", (long)k60_sleep_wake_after_ms(30), 30000);

    check("backlight one frame", k60_sleep_backlight_ready(1, 1, 0), 0);
    check("backlight two frames", k60_sleep_backlight_ready(2, 1, 0), 1);
    check("backlight cap pending", k60_sleep_backlight_ready(0, 1, 1499), 0);
    check("backlight cap reached", k60_sleep_backlight_ready(0, 1, 1500), 1);
    check("backlight counting ignores 600", k60_sleep_backlight_ready(0, 1, 600), 0);
    check("backlight fallback pending", k60_sleep_backlight_ready(0, 0, 599), 0);
    check("backlight fallback reached", k60_sleep_backlight_ready(0, 0, 600), 1);
    check("backlight fallback ignores frames", k60_sleep_backlight_ready(5, 0, 0), 0);

    check("touch no contact", k60_sleep_touch_reestablish(1000, 0), 0);
    check("touch same instant", k60_sleep_touch_reestablish(1000, 1000), 0);
    check("touch 60 ms", k60_sleep_touch_reestablish(1060, 1000), 0);
    check("touch 61 ms", k60_sleep_touch_reestablish(1061, 1000), 1);
    check("touch backwards", k60_sleep_touch_reestablish(900, 1000), 0);

    printf("TESTS %s %u checks (%u failure%s)\n", failures ? "FAILED" : "OK",
        checks, failures, failures == 1 ? "" : "s");
    return failures != 0;
}
