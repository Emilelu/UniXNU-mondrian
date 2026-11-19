/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/*
 * K60 board hook for the ArmCpu platform-sleep core.
 *
 * The generic wait, the GIC enable save/restore, the PSCI CPU_OFF of the
 * secondary cores and the wake-after timer all live in drivers/ArmCpu. This
 * file only supplies what is board-specific, and the first flight is
 * deliberately timer-only: platform-sleep-wake-after=N gives the wait a
 * deadline, so the sleep path can be measured without claiming a wake source
 * that is not routed yet.
 *
 * The power key is not registered here. Its PON interrupt arrives as GIC SPI
 * 481 (INTID 513) through the SPMI arbiter, and no driver in this tree
 * programs that SPI's trigger or clears the PON latch. Registering INTID 513
 * without that work would leave the distributor enable set on a line that
 * never asserts, which looks like a wake source and is not one. It is the
 * next step after the timer path is proven on the device; K60SleepPlan already
 * carries the read-only PON RT_STS bit (0x80) and the 60 ms touch rules.
 */
#include <IOKit/IOLib.h>
#include <pexpert/pexpert.h>
#include "../ArmCpu/ArmCpuSleep.h"

/* Ten seconds is the official watchdog cadence: the tick is where a board
 * feeds its own watchdog. This board has no writable watchdog endpoint in the
 * tree (IOWatchdog is a software check-in service, not a PMIC ping), so the
 * tick counts and logs instead of inventing a register write. */
#define K60_SLEEP_TICK_S 10u

/* Implemented in drivers/ArmCpu/ArmCpu.cpp; ArmCpuSleep.h deliberately holds
 * only the value types and inline helpers. */
extern "C" int armcpu_sleep_register(const struct armcpu_sleep_board *board);

static volatile unsigned gPrepares;
static volatile unsigned gRestores;
static volatile unsigned gTicks;

static void k60_sleep_prepare(void)
{
    const unsigned n = __atomic_add_fetch(&gPrepares, 1, __ATOMIC_RELAXED);
    IOLog("K60Sleep: prepare #%u; timer-only wake (platform-sleep-wake-after)\n", n);
}

static int k60_sleep_should_wake(uint32_t intid)
{
    IOLog("K60Sleep: should_wake intid=%u -> no (no board wake source registered yet)\n", intid);
    return 0;
}

static void k60_sleep_restore(void)
{
    const unsigned n = __atomic_add_fetch(&gRestores, 1, __ATOMIC_RELAXED);
    IOLog("K60Sleep: restore #%u (prepares=%u ticks=%u)\n", n,
        __atomic_load_n(&gPrepares, __ATOMIC_RELAXED),
        __atomic_load_n(&gTicks, __ATOMIC_RELAXED));
}

static void k60_sleep_tick(void)
{
    const unsigned n = __atomic_add_fetch(&gTicks, 1, __ATOMIC_RELAXED);
    IOLog("K60Sleep: tick #%u (no hardware watchdog endpoint in tree)\n", n);
}

static const struct armcpu_sleep_board k60SleepBoard = {
    k60_sleep_prepare,
    k60_sleep_should_wake,
    k60_sleep_restore,
    nullptr,
    0,
    k60_sleep_tick,
    K60_SLEEP_TICK_S,
};

/* Called from k60_physical_battery_start(), which runs before ArmCpu parses
 * platform-sleep. The record is therefore handed over unconditionally and the
 * return value only says whether the hook is installed yet; ArmCpu reads the
 * stored record when the wait begins. */
extern "C" void k60_platform_sleep_register(void)
{
    static unsigned attempted;

    if (__atomic_exchange_n(&attempted, 1u, __ATOMIC_ACQ_REL)) return;
    const int rc = armcpu_sleep_register(&k60SleepBoard);
    IOLog("K60Sleep: board hook registered rc=%d (0 hook installed; -2 until platform-sleep=1 is parsed)\n", rc);
}
