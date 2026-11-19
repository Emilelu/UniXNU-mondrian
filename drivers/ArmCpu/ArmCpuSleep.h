// SPDX-License-Identifier: BSD-2-Clause-Patent
// Platform sleep (suspend to idle) for boards without Apple's sleep hardware, the logic ArmCpu.cpp applies while the system sleeps:
// the boot core waits with interrupts masked for one of the board's wake sources, the other cores are off (PSCI CPU_OFF). While it
// waits only the wake sources stay enabled at the distributor; a pending interrupt is a wake when the board says so (should_wake) or
// when it is the wake-after timer. Interrupt numbers are GIC INTIDs (SPI n is INTID 32 + n). Host-tested by tests/armcpu_sleep_host.c.
#ifndef ARMCPU_SLEEP_H
#define ARMCPU_SLEEP_H
#include <stdint.h>
#include <string.h>

// GICD_ISENABLER<n> words: word 0 (SGIs and PPIs, banked per core) is left alone, words 1..31 cover INTIDs 32..1023.
#define ARMCPU_SLEEP_SPI_WORDS 32u
#define ARMCPU_SLEEP_NO_TIMER 0xffffffffu

#define ARMCPU_SLEEP_NEVER UINT64_MAX
#define ARMCPU_SLEEP_SPURIOUS 1023u
// A line the board turns down this many times in a row, each within a millisecond of the last, is a storm (armcpu_sleep_storm).
#define ARMCPU_SLEEP_STORM_LIMIT 1000u

// What a board gives ArmCpu (armcpu_sleep_register): prepare and restore run on the boot core with interrupts masked, before and after
// the wait; should_wake is asked about a pending wake source and may clear that source's own status when it answers 0. tick, when set,
// runs every tick_s seconds while the system sleeps (the board's watchdog ping), and the wait goes on.
struct armcpu_sleep_board {
    void (*prepare)(void);
    int (*should_wake)(uint32_t intid);
    void (*restore)(void);
    const uint32_t *wake_spis;
    uint32_t wake_spi_count;
    void (*tick)(void);
    uint32_t tick_s;
};
#define ARMCPU_SLEEP_BOARD_SIZE 56u

// Storm: a line kept firing after the board turned it down, and masking it left nothing to wake the system, so it woke.
enum armcpu_wake_reason {ArmcpuWakeNone, ArmcpuWakeSource, ArmcpuWakeTimer, ArmcpuWakeStorm};

// phase: 1 in the hook, 2 the other cores off, 3 waiting, 4 woken, 5 restored (the last one reached shows where a hang stopped).
// masked: storming lines turned off for the rest of a sleep; ticks: board ticks; unarmed: sleeps that returned at once, nothing armed.
struct armcpu_sleep_stats {
    uint32_t phase, entries, spurious, last_intid, last_reason, cpu_off_failures;
    uint64_t asleep_ticks;
    uint32_t masked, ticks, unarmed;
};
#define ARMCPU_SLEEP_STATS_SIZE 48u

// The distributor enables to keep while asleep: those of the wake sources that were enabled before.
static inline void armcpu_sleep_keep(const uint32_t saved[ARMCPU_SLEEP_SPI_WORDS], const uint32_t *wake_spis, uint32_t count,
                                     uint32_t keep[ARMCPU_SLEEP_SPI_WORDS])
{
    memset(keep, 0, ARMCPU_SLEEP_SPI_WORDS * sizeof *keep);
    for (uint32_t i = 0; i < count; ++i) {
        const uint32_t intid = wake_spis[i];
        if (intid < 32 || intid > 1019) continue;
        const uint32_t bit = 1u << (intid % 32);
        keep[intid / 32] |= saved[intid / 32] & bit;
    }
}

// What a pending interrupt means for the wait: the board's yes first, then the wake-after timer, else keep waiting.
static inline enum armcpu_wake_reason armcpu_sleep_decide(uint32_t intid, int board_says_wake, uint32_t timer_intid)
{
    if (board_says_wake) return ArmcpuWakeSource;
    if (timer_intid != ARMCPU_SLEEP_NO_TIMER && intid == timer_intid) return ArmcpuWakeTimer;
    return ArmcpuWakeNone;
}

// Whether a wake source stays enabled while asleep (word 0 is never kept). With none and no wake-after timer nothing could end the
// wait, so the hook returns at once.
static inline int armcpu_sleep_armed(const uint32_t keep[ARMCPU_SLEEP_SPI_WORDS])
{
    for (uint32_t w = 1; w < ARMCPU_SLEEP_SPI_WORDS; ++w)
        if (keep[w]) return 1;
    return 0;
}

// The counter value `seconds` after start, for CNTV_CVAL (a 64-bit absolute deadline: an hour at 19.2 MHz is past CNTV_TVAL's 31 bits).
static inline uint64_t armcpu_sleep_deadline(uint64_t start, uint32_t seconds, uint64_t hz)
{
    return seconds ? start + (uint64_t)seconds * hz : ARMCPU_SLEEP_NEVER;
}

static inline uint64_t armcpu_sleep_next(uint64_t wake_at, uint64_t tick_at) {return wake_at < tick_at ? wake_at : tick_at;}

// What the virtual timer firing at now means: the wake-after deadline reached (it wins over a tick due at the same time), else a board
// tick due (the next one tick_ticks from now), else nothing (early, or spurious).
enum armcpu_timer_event {ArmcpuTimerNothing, ArmcpuTimerTick, ArmcpuTimerWake};
static inline enum armcpu_timer_event armcpu_sleep_timer(uint64_t now, uint64_t wake_at, uint64_t *tick_at, uint64_t tick_ticks)
{
    if (now >= wake_at) return ArmcpuTimerWake;
    if (*tick_at != ARMCPU_SLEEP_NEVER && now >= *tick_at) {
        *tick_at = now + tick_ticks;
        return ArmcpuTimerTick;
    }
    return ArmcpuTimerNothing;
}

// The lowest kept wake source pending at the distributor (GICD_ISPENDR words), 1023 if none. The timer's PPI outranks device SPIs, so
// when it fires the board is asked about these first: a real wake at the same moment as the timer wins.
static inline uint32_t armcpu_sleep_pending_source(const uint32_t pending[ARMCPU_SLEEP_SPI_WORDS],
                                                   const uint32_t keep[ARMCPU_SLEEP_SPI_WORDS])
{
    for (uint32_t w = 1; w < ARMCPU_SLEEP_SPI_WORDS; ++w) {
        const uint32_t both = pending[w] & keep[w];
        if (both) return w * 32 + (uint32_t)__builtin_ctz(both);
    }
    return ARMCPU_SLEEP_SPURIOUS;
}

// A turned-down line counted towards a storm: the same INTID as the last one, within window ticks of it. Returns 1 at the limit, and
// counts afresh after it.
struct armcpu_sleep_storm {uint32_t intid, count; uint64_t last;};
static inline int armcpu_sleep_storm(struct armcpu_sleep_storm *s, uint32_t intid, uint64_t now, uint64_t window)
{
    if (s->count == 0 || intid != s->intid || now - s->last > window) {
        s->intid = intid;
        s->count = 0;
    }
    s->last = now;
    if (++s->count < ARMCPU_SLEEP_STORM_LIMIT) return 0;
    s->count = 0;
    return 1;
}

#endif
