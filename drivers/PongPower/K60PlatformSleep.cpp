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
#include <IOKit/IOService.h>
#include <IOKit/pwr_mgt/RootDomain.h>
#include <kern/thread.h>
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

/* Implemented in the XNU patch 0624 beside IOPMrootDomain::start(). A kernel
 * thread has no user-client entitlement, so IOPMrootDomain::setProperties()
 * refuses the System Boot Complete key with kIOReturnNotPermitted; this helper
 * submits the same power event directly on the root-domain queue. */
extern "C" void k60_platform_sleep_boot_complete(void);

static volatile unsigned gPrepares;
static volatile unsigned gRestores;
static volatile unsigned gTicks;

/* prepare/should_wake/restore/tick run with interrupts masked and the console
 * suspended. Logging from any of them panics the K60 USB log, so they only
 * count; k60_platform_sleep_report() prints the counters after resume. */

/* Diagnostic only: the official entry is the power key, but a bring-up run
 * needs a deterministic trigger while the PON SPI is still unrouted. The boot
 * argument is short because the K60 command line is at its size ceiling. */
static void k60_sleep_trigger_thread(void *arg, wait_result_t)
{
    const uint32_t seconds = (uint32_t)(uintptr_t)arg;

    IOSleep(seconds * 1000);
    IOPMrootDomain *pm = IOService::getPMRootDomain();
    IOLog("K60Sleep: diagnostic trigger after %u s pm=%p\n", seconds, pm);
    if (pm != nullptr) {
        /* The demand path refuses while systemBooting is still set. That flag
         * is cleared only by the kPowerEventSystemBootCompleted power event
         * that userland powerd normally publishes; this board has no such
         * publisher yet, so the bring-up trigger submits the event through the
         * XNU helper and retries the demand request while PM dispatches it.
         * It is guarded by k60_slp like the rest of the trigger. */
        k60_platform_sleep_boot_complete();
        IOLog("K60Sleep: boot complete event submitted\n");
        for (unsigned attempt = 0; attempt < 10; attempt++) {
            IOSleep(200);
            const IOReturn rc = pm->sleepSystem();
            IOLog("K60Sleep: sleepSystem attempt %u rc=0x%x\n", attempt + 1, rc);
            if (rc == kIOReturnSuccess) break;
        }
    }
}

static void k60_sleep_prepare(void)
{
    __atomic_add_fetch(&gPrepares, 1, __ATOMIC_RELAXED);
}

static int k60_sleep_should_wake(uint32_t)
{
    return 0;
}

static void k60_sleep_restore(void)
{
    __atomic_add_fetch(&gRestores, 1, __ATOMIC_RELAXED);
}

static void k60_sleep_tick(void)
{
    __atomic_add_fetch(&gTicks, 1, __ATOMIC_RELAXED);
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

/* Runs from IOCPUSleepKernel after console_resume(), so IOLog is safe here. */
extern "C" void k60_platform_sleep_report(void)
{
    IOLog("K60Sleep: report prepares=%u restores=%u ticks=%u\n",
        __atomic_load_n(&gPrepares, __ATOMIC_RELAXED),
        __atomic_load_n(&gRestores, __ATOMIC_RELAXED),
        __atomic_load_n(&gTicks, __ATOMIC_RELAXED));
}

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

    uint32_t trigger = 0;
    if (PE_parse_boot_argn("k60_slp", &trigger, sizeof(trigger)) && trigger != 0) {
        thread_t thread = THREAD_NULL;
        const kern_return_t kr = kernel_thread_start(k60_sleep_trigger_thread,
            (void *)(uintptr_t)trigger, &thread);
        if (kr == KERN_SUCCESS) {
            IOLog("K60Sleep: diagnostic trigger armed %u s\n", trigger);
            thread_deallocate(thread);
        } else {
            IOLog("K60Sleep: diagnostic trigger failed kr=0x%x\n", kr);
        }
    }
}
