// SPDX-License-Identifier: BSD-2-Clause-Patent
// Host tests of the platform sleep logic (ArmCpuSleep.h): which distributor enables stay on while the boot core waits, and what
// a pending interrupt means for the wait. Interrupt numbers are GIC INTIDs (SPI n is INTID 32 + n).
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../../drivers/ArmCpu/ArmCpuSleep.h"

static unsigned checks;
#define CHECK(x) do {if (!(x)) {fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); exit(1);} ++checks;} while (0)

static void set(uint32_t words[ARMCPU_SLEEP_SPI_WORDS], uint32_t intid) {words[intid / 32] |= 1u << (intid % 32);}
static int isset(const uint32_t words[ARMCPU_SLEEP_SPI_WORDS], uint32_t intid) {return (words[intid / 32] >> (intid % 32)) & 1u;}
static unsigned count(const uint32_t words[ARMCPU_SLEEP_SPI_WORDS])
{
    unsigned n = 0;
    for (unsigned i = 0; i < ARMCPU_SLEEP_SPI_WORDS; ++i) n += (unsigned)__builtin_popcount(words[i]);
    return n;
}

static void keep_only_enabled_wake_spis(void)
{
    uint32_t saved[ARMCPU_SLEEP_SPI_WORDS] = {0}, keep[ARMCPU_SLEEP_SPI_WORDS];
    set(saved, 240); set(saved, 513); set(saved, 332);
    const uint32_t wake[] = {240, 513, 532};
    memset(keep, 0xa5, sizeof keep);
    armcpu_sleep_keep(saved, wake, 3, keep);
    CHECK(isset(keep, 240) && isset(keep, 513));
    CHECK(!isset(keep, 332) && !isset(keep, 532));     // enabled but not a wake source; a wake source never enabled
    CHECK(count(keep) == 2);
}

static void keep_ignores_out_of_range(void)
{
    uint32_t saved[ARMCPU_SLEEP_SPI_WORDS], keep[ARMCPU_SLEEP_SPI_WORDS];
    memset(saved, 0xff, sizeof saved);
    const uint32_t wake[] = {31, 1020, 4096, 240};
    armcpu_sleep_keep(saved, wake, 4, keep);
    CHECK(count(keep) == 1 && isset(keep, 240));        // PPI 31 and INTIDs past 1019 are not SPIs
    CHECK(keep[0] == 0);                                // word 0 (SGIs, PPIs) is never touched
}

static void decide_board_wake(void) {CHECK(armcpu_sleep_decide(240, 1, 27) == ArmcpuWakeSource);}
static void decide_timer(void) {CHECK(armcpu_sleep_decide(27, 0, 27) == ArmcpuWakeTimer);}
static void decide_none_1023(void)
{
    CHECK(armcpu_sleep_decide(1023, 0, 27) == ArmcpuWakeNone);
    CHECK(armcpu_sleep_decide(240, 0, 27) == ArmcpuWakeNone);   // a wake source the board turned down
    CHECK(armcpu_sleep_decide(27, 0, ARMCPU_SLEEP_NO_TIMER) == ArmcpuWakeNone);
}
static void timer_and_wake_source_prefers_source(void) {CHECK(armcpu_sleep_decide(27, 1, 27) == ArmcpuWakeSource);}

static void two_rounds_same_result(void)
{
    uint32_t saved[ARMCPU_SLEEP_SPI_WORDS] = {0}, copy[ARMCPU_SLEEP_SPI_WORDS], a[ARMCPU_SLEEP_SPI_WORDS], b[ARMCPU_SLEEP_SPI_WORDS];
    set(saved, 240); set(saved, 513); set(saved, 615); set(saved, 1019);
    memcpy(copy, saved, sizeof saved);
    const uint32_t wake[] = {240, 513};
    armcpu_sleep_keep(saved, wake, 2, a);
    armcpu_sleep_keep(saved, wake, 2, b);
    CHECK(!memcmp(a, b, sizeof a) && !memcmp(saved, copy, sizeof saved));
}

// Nothing could end the wait without a wake source left enabled (and no wake-after timer): the hook returns at once instead.
static void armed_needs_a_kept_line(void)
{
    uint32_t keep[ARMCPU_SLEEP_SPI_WORDS] = {0};
    CHECK(!armcpu_sleep_armed(keep));
    keep[0] = 1u;                                       // word 0 is never a kept SPI
    CHECK(!armcpu_sleep_armed(keep));
    set(keep, 513);
    CHECK(armcpu_sleep_armed(keep));
}

static void deadline_never_for_zero(void) {CHECK(armcpu_sleep_deadline(5, 0, 19200000) == ARMCPU_SLEEP_NEVER);}
// An hour at 19.2 MHz is past the 32-bit CNTV_TVAL; the deadline is absolute (CNTV_CVAL).
static void deadline_large_no_overflow(void) {CHECK(armcpu_sleep_deadline(1000, 3600, 19200000) == 1000ull + 3600ull * 19200000ull);}

static void timer_wake_at_deadline(void)
{
    uint64_t tick = 50;
    CHECK(armcpu_sleep_timer(100, 100, &tick, 10) == ArmcpuTimerWake);   // the deadline wins over a tick due too
    CHECK(tick == 50);
}

static void timer_tick_before_deadline(void)
{
    uint64_t tick = 50;
    CHECK(armcpu_sleep_timer(55, 100, &tick, 10) == ArmcpuTimerTick);
    CHECK(tick == 65);                                  // the next tick from now
    CHECK(armcpu_sleep_timer(60, 100, &tick, 10) == ArmcpuTimerNothing);
    CHECK(armcpu_sleep_timer(65, ARMCPU_SLEEP_NEVER, &tick, 10) == ArmcpuTimerTick);   // ticks without a wake-after timer
}

static void timer_early_is_nothing(void)
{
    uint64_t tick = ARMCPU_SLEEP_NEVER;
    CHECK(armcpu_sleep_timer(10, 100, &tick, 0) == ArmcpuTimerNothing);
    CHECK(tick == ARMCPU_SLEEP_NEVER);
}

static void next_is_earlier(void)
{
    CHECK(armcpu_sleep_next(100, 65) == 65);
    CHECK(armcpu_sleep_next(100, ARMCPU_SLEEP_NEVER) == 100);
    CHECK(armcpu_sleep_next(ARMCPU_SLEEP_NEVER, ARMCPU_SLEEP_NEVER) == ARMCPU_SLEEP_NEVER);
}

// The timer's PPI has a higher priority than device SPIs: a wake source pending with it is found at the distributor and asked first.
static void pending_source_found_behind_timer(void)
{
    uint32_t pending[ARMCPU_SLEEP_SPI_WORDS] = {0}, keep[ARMCPU_SLEEP_SPI_WORDS] = {0};
    set(keep, 240); set(keep, 513);
    CHECK(armcpu_sleep_pending_source(pending, keep) == 1023u);
    set(pending, 300);
    CHECK(armcpu_sleep_pending_source(pending, keep) == 1023u);   // pending but not a kept wake source
    set(pending, 513);
    CHECK(armcpu_sleep_pending_source(pending, keep) == 513u);
    set(pending, 240);
    CHECK(armcpu_sleep_pending_source(pending, keep) == 240u);
}

// A line turned down again and again, each time within the window of the last: reported once at the limit, then counted afresh.
static void storm_reaches_limit(void)
{
    struct armcpu_sleep_storm s = {0};
    for (unsigned i = 1; i < ARMCPU_SLEEP_STORM_LIMIT; ++i) CHECK(!armcpu_sleep_storm(&s, 513, i, 10));
    CHECK(armcpu_sleep_storm(&s, 513, ARMCPU_SLEEP_STORM_LIMIT, 10));
    CHECK(!armcpu_sleep_storm(&s, 513, ARMCPU_SLEEP_STORM_LIMIT + 1, 10));
}

static void storm_resets_on_other_intid(void)
{
    struct armcpu_sleep_storm s = {0};
    for (unsigned i = 1; i < ARMCPU_SLEEP_STORM_LIMIT; ++i) (void)armcpu_sleep_storm(&s, 513, i, 10);
    CHECK(!armcpu_sleep_storm(&s, 240, ARMCPU_SLEEP_STORM_LIMIT, 10));
    CHECK(!armcpu_sleep_storm(&s, 513, ARMCPU_SLEEP_STORM_LIMIT + 1, 10));
}

static void storm_resets_after_gap(void)
{
    struct armcpu_sleep_storm s = {0};
    uint64_t now = 0;
    for (unsigned i = 1; i < ARMCPU_SLEEP_STORM_LIMIT; ++i) (void)armcpu_sleep_storm(&s, 513, now += 5, 10);
    CHECK(!armcpu_sleep_storm(&s, 513, now += 11, 10));   // a quiet gap: a new run starts
}

// The board's copy of the layouts (UniXNU-sheng package/ShengSleep.cpp) asserts the same sizes.
static void layout_sizes(void)
{
    CHECK(sizeof(struct armcpu_sleep_stats) == ARMCPU_SLEEP_STATS_SIZE);
    CHECK(sizeof(struct armcpu_sleep_board) == ARMCPU_SLEEP_BOARD_SIZE);
}

int main(void)
{
    keep_only_enabled_wake_spis();
    keep_ignores_out_of_range();
    decide_board_wake();
    decide_timer();
    decide_none_1023();
    timer_and_wake_source_prefers_source();
    two_rounds_same_result();
    armed_needs_a_kept_line();
    deadline_never_for_zero();
    deadline_large_no_overflow();
    timer_wake_at_deadline();
    timer_tick_before_deadline();
    timer_early_is_nothing();
    next_is_earlier();
    pending_source_found_behind_timer();
    storm_reaches_limit();
    storm_resets_on_other_intid();
    storm_resets_after_gap();
    layout_sizes();
    printf("TESTS OK %u checks\n", checks);
    return 0;
}
