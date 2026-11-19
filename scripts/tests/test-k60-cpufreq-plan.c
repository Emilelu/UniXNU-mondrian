/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* Offline check of the pure EPSS decode/pick/governor math. The hardware LUT
 * rows are synthetic: the live K60 table has not been read yet, so every
 * expectation here pins the reference arithmetic, not a measured frequency. */
#include <stdio.h>
#include <string.h>
#include "../../drivers/PongPower/K60CpuFreqPlan.h"

static unsigned failures, checks;

static void check(const char *name, long got, long want)
{
    ++checks;
    if (got != want) {
        ++failures;
        printf("FAIL %s: got %ld want %ld\n", name, got, want);
    }
}

/* The vote set must never carry the firmware-owned DCVS control register. */
static unsigned control_writes(const K60CpuFreqWrite *writes, unsigned count)
{
    unsigned i, hits = 0;

    for (i = 0; i < count; ++i)
        if (writes[i].offset == K60_CPU_FREQ_REG_DCVS_CTRL) ++hits;
    return hits;
}

/* 0x40040028: source 1, four cores, L 40 -> 768 MHz.
 * 0x4001006E: source 1, one core (turbo), L 110 -> 2112 MHz. */
#define ROW_A 0x00040000u /* source 0 -> GPLL0/2 = 300 MHz */
#define ROW_B 0x40040028u
#define ROW_C 0x40040050u
#define ROW_D 0x40010032u /* turbo at 960 MHz, must be skipped */
#define ROW_E 0x40010032u /* repeated tail row, stops the walk */

static const uint32_t kRows[] = {ROW_A, ROW_B, ROW_C, ROW_D, ROW_E};

static K60CpuFreqTable clockTable(void)
{
    /* 300, 768, 960, 1344, 1536 MHz: L 0, 40, 50, 70, 80 on source 1. */
    static const uint32_t rows[] = {0x00040000u, 0x40040028u, 0x40040032u,
        0x40040046u, 0x40040050u};
    K60CpuFreqTable table;
    check("clock rows", k60_cpufreq_build_table(rows, 5, 0, &table), 0);
    check("clock count", table.count, 5);
    return table;
}

int main(void)
{
    K60CpuFreqTable table, clock;
    unsigned index = 0;
    uint32_t khz = 0;

    check("row_a_khz", k60_cpufreq_row_khz(ROW_A), 300000);
    check("row_b_khz", k60_cpufreq_row_khz(ROW_B), 768000);
    check("row_c_khz", k60_cpufreq_row_khz(ROW_C), 1536000);
    check("row_d_khz", k60_cpufreq_row_khz(ROW_D), 960000);
    check("row_cores_b", k60_cpufreq_row_cores(ROW_B), 4);
    check("row_cores_d", k60_cpufreq_row_cores(ROW_D), 1);
    check("row_turbo_b", k60_cpufreq_row_turbo(ROW_B), 0);
    check("row_turbo_d", k60_cpufreq_row_turbo(ROW_D), 1);

    check("table_ok", k60_cpufreq_build_table(kRows, 5, 0, &table), 0);
    check("table_count", table.count, 3);
    check("table_khz0", table.khz[0], 300000);
    check("table_khz1", table.khz[1], 768000);
    check("table_khz2", table.khz[2], 1536000);
    check("table_level0", table.level[0], 0);
    check("table_level1", table.level[1], 1);
    check("table_level2", table.level[2], 2);
    check("table_turbo_absent", table.khz[table.count - 1], 1536000);

    check("pick_highest", k60_cpufreq_pick_highest(&table, 0, &index, &khz), 0);
    check("pick_highest_index", index, 2);
    check("pick_highest_khz", khz, 1536000);
    check("pick_cap", k60_cpufreq_pick_highest(&table, 800000, &index, &khz), 0);
    check("pick_cap_index", index, 1);
    check("pick_cap_khz", khz, 768000);
    check("pick_cap_below", k60_cpufreq_pick_highest(&table, 200000, &index, &khz), -1);
    check("pick_lowest", k60_cpufreq_pick_lowest(&table, &index, &khz), 0);
    check("pick_lowest_index", index, 0);
    check("pick_lowest_khz", khz, 300000);
    check("pick_lowest_null", k60_cpufreq_pick_lowest(NULL, &index, &khz), -1);
    {
        K60CpuFreqTable empty = {};
        check("pick_lowest_empty", k60_cpufreq_pick_lowest(&empty, &index, &khz), -1);
    }

    check("pick_at_least_exact", k60_cpufreq_pick_at_least(&table, 768000, &index, &khz), 0);
    check("pick_at_least_exact_index", index, 1);
    check("pick_at_least_above", k60_cpufreq_pick_at_least(&table, 500000, &index, &khz), 0);
    check("pick_at_least_above_index", index, 1);
    check("pick_at_least_below", k60_cpufreq_pick_at_least(&table, 200000, &index, &khz), 0);
    check("pick_at_least_below_index", index, 0);
    check("pick_at_least_none", k60_cpufreq_pick_at_least(&table, 2000000, &index, &khz), -1);
    check("pick_at_least_null", k60_cpufreq_pick_at_least(NULL, 300000, &index, &khz), -1);
    {
        K60CpuFreqTable l3 = {};
        const uint32_t tops[3] = {1804800, 2496000, 2995200};
        const uint32_t idle[3] = {1804800, 2496000, 2995200};
        const uint32_t half[3] = {900000, 1248000, 1497600};
        const uint32_t zero[3] = {0, 0, 0};
        l3.khz[0] = 300000; l3.khz[1] = 600000; l3.khz[2] = 1200000; l3.khz[3] = 1708800;
        l3.count = 4;
        check("l3_target_top", k60_cpufreq_l3_target(&l3, idle, tops, 0, &index, &khz), 0);
        check("l3_target_top_index", index, 3);
        check("l3_target_top_khz", khz, 1708800);
        check("l3_target_half", k60_cpufreq_l3_target(&l3, half, tops, 0, &index, &khz), 0);
        check("l3_target_half_index", index, 2);
        check("l3_target_half_khz", khz, 1200000);
        check("l3_target_boost", k60_cpufreq_l3_target(&l3, half, tops, 1, &index, &khz), 0);
        check("l3_target_boost_index", index, 3);
        check("l3_target_zero", k60_cpufreq_l3_target(&l3, zero, tops, 0, &index, &khz), -1);
        check("l3_target_null", k60_cpufreq_l3_target(NULL, idle, tops, 0, &index, &khz), -1);
    }

    check("build_cap", k60_cpufreq_build_table(kRows, 5, 1000000, &table), 0);
    check("build_cap_count", table.count, 2);
    check("build_cap_top", table.khz[1], 768000);
    check("build_empty", k60_cpufreq_build_table(kRows, 0, 0, &table), -1);
    check("build_null", k60_cpufreq_build_table(NULL, 4, 0, &table), -1);
    {
        static const uint32_t turbo_only[] = {0x40010050u, 0x40010050u};
        check("build_all_turbo", k60_cpufreq_build_table(turbo_only, 2, 0, &table), -1);
    }

    clock = clockTable();
    check("clock_top", clock.khz[clock.count - 1], 1536000);
    /* current 1536 MHz, half busy: 1536 x 0.5 x 1.25 = 960 MHz -> level 2. */
    check("target_half", k60_cpufreq_target(&clock, 4, 500, 0, 0, 0, 0), 2);
    /* 90% busy jumps to the top whatever the estimate says. */
    check("target_hispeed", k60_cpufreq_target(&clock, 4, 900, 0, 0, 0, 0), 4);
    /* 10% busy: 1536 x 0.1 x 1.25 = 192 MHz -> stays at the bottom. */
    check("target_idle", k60_cpufreq_target(&clock, 4, 100, 0, 0, 0, 0), 0);
    /* Frame floor is 60% of the top = 921.6 MHz -> level 2 (960 MHz). */
    check("target_frame", k60_cpufreq_target(&clock, 0, 0, 0, 0, 1, 0), 2);
    /* Boost pins the top on every domain; quiet holds at least the half on
     * the shared clusters only. */
    check("target_boost", k60_cpufreq_target(&clock, 0, 0, 1, 1, 0, 0), 4);
    check("target_boost_boot", k60_cpufreq_target(&clock, 0, 0, 0, 1, 0, 0), 4);
    check("target_quiet", k60_cpufreq_target(&clock, 0, 0, 1, 0, 0, 0), 1);
    check("target_quiet_done", k60_cpufreq_target(&clock, 0, 0, 1, 0, 0,
        K60_CPU_FREQ_QUIET_WINDOWS), 0);
    /* The boot cluster never takes the shared-cluster quiet floor. */
    check("target_boot_quiet", k60_cpufreq_target(&clock, 0, 0, 0, 0, 0, 0), 0);
    check("target_empty", k60_cpufreq_target(NULL, 0, 0, 0, 0, 0, 0), 0);
    /* A 1 GHz ceiling keeps the table at 960 MHz (index 2). With current above
     * the ceiling the need is measured from the capped top: 960 x 0.5 x 1.25
     * = 600 MHz, so the decision drops to 768 MHz. */
    check("target_cap_half", k60_cpufreq_target_capped(&clock, 1000000, 4, 500,
        0, 0, 0, 0), 1);
    check("target_cap_hispeed", k60_cpufreq_target_capped(&clock, 1000000, 4, 950,
        0, 0, 0, 0), 2);
    check("target_cap_boost", k60_cpufreq_target_capped(&clock, 1000000, 0, 0,
        1, 1, 0, 0), 2);
    check("target_cap_low", k60_cpufreq_target_capped(&clock, 500000, 4, 950,
        0, 0, 0, 0), 0);
    check("target_cap_below", k60_cpufreq_target_capped(&clock, 200000, 4, 950,
        0, 0, 0, 0), 5);
    check("target_cap_zero", k60_cpufreq_target_capped(&clock, 0, 4, 500,
        0, 0, 0, 0), 2);
    check("target_cap_null", k60_cpufreq_target_capped(NULL, 1000000, 4, 500,
        0, 0, 0, 0), 0);

    /* 0x81 is 129 x 19.2 MHz = 2476.8 MHz; the limit bit makes it a ceiling,
     * and a ceiling above the table top cannot raise the table. */
    check("hwcap_active", k60_cpufreq_hardware_cap(0x81, K60_CPU_FREQ_HW_LIMIT_ACTIVE,
        2995200), 2476800);
    check("hwcap_off", k60_cpufreq_hardware_cap(0x81, 0, 2995200), 2995200);
    check("hwcap_zero_state", k60_cpufreq_hardware_cap(0, K60_CPU_FREQ_HW_LIMIT_ACTIVE,
        2995200), 2995200);
    check("hwcap_above_top", k60_cpufreq_hardware_cap(0xff, K60_CPU_FREQ_HW_LIMIT_ACTIVE,
        2995200), 2995200);
    check("hwcap_below_table_top", k60_cpufreq_hardware_cap(0x81,
        K60_CPU_FREQ_HW_LIMIT_ACTIVE, 2000000), 2000000);
    check("hwcap_low", k60_cpufreq_hardware_cap(1, K60_CPU_FREQ_HW_LIMIT_ACTIVE,
        2995200), 19200);

    {
        unsigned current = 4, down = 0, i;
        for (i = 0; i < K60_CPU_FREQ_DOWN_WINDOWS - 1; ++i) {
            check("step_down_deferred", k60_cpufreq_step(&clock, &current, 2, &down), 0);
            check("step_down_level", current, 4);
        }
        check("step_down_lands", k60_cpufreq_step(&clock, &current, 2, &down), 1);
        check("step_down_lower", current, 2);
        check("step_down_reset", down, 0);
        check("step_up_now", k60_cpufreq_step(&clock, &current, 4, &down), 1);
        check("step_up_level", current, 4);
        check("step_same", k60_cpufreq_step(&clock, &current, 4, &down), 0);
        check("step_null", k60_cpufreq_step(NULL, &current, 4, &down), 0);
    }

    check("cpu0_domain", k60_cpufreq_domain_of_cpu(0), 0);
    check("cpu3_domain", k60_cpufreq_domain_of_cpu(3), 0);
    check("cpu4_domain", k60_cpufreq_domain_of_cpu(4), 1);
    check("cpu6_domain", k60_cpufreq_domain_of_cpu(6), 1);
    check("cpu7_domain", k60_cpufreq_domain_of_cpu(7), 2);
    check("domain0_cores", k60_cpufreq_domain_cores(0), 4);
    check("domain1_cores", k60_cpufreq_domain_cores(1), 3);
    check("domain2_cores", k60_cpufreq_domain_cores(2), 1);
    check("domain3_cores", k60_cpufreq_domain_cores(3), 0);
    check("row_source0_ignores_l", k60_cpufreq_row_khz(0x000000ffu), 300000);

    {
        K60CpuFreqWrite writes[K60_CPU_FREQ_MAX_WRITES];
        unsigned n;

        n = k60_cpufreq_build_votes(0, 0, 7, writes, K60_CPU_FREQ_MAX_WRITES);
        check("votes_d0_single_count", n, 1);
        check("votes_d0_single_offset", writes[0].offset, 0x320);
        check("votes_d0_single_value", writes[0].value, 7);
        n = k60_cpufreq_build_votes(0, 1, 9, writes, K60_CPU_FREQ_MAX_WRITES);
        check("votes_d0_dcvs_count", n, 4);
        check("votes_d0_core1_offset", writes[1].offset, 0x324);
        check("votes_d0_core3_offset", writes[3].offset, 0x32c);
        check("votes_d0_core3_value", writes[3].value, 9);
        check("votes_d0_never_control", control_writes(writes, n), 0);
        n = k60_cpufreq_build_votes(1, 1, 3, writes, K60_CPU_FREQ_MAX_WRITES);
        check("votes_d1_dcvs_count", n, 3);
        n = k60_cpufreq_build_votes(2, 1, 3, writes, K60_CPU_FREQ_MAX_WRITES);
        check("votes_d2_dcvs_count", n, 1);
        check("votes_tight_capacity", k60_cpufreq_build_votes(0, 1, 3, writes, 2), 0);
        check("votes_null", k60_cpufreq_build_votes(0, 1, 3, NULL, 8), 0);
        n = k60_cpufreq_build_l3_vote(5, writes, 1);
        check("l3_vote_count", n, 1);
        check("l3_vote_offset", writes[0].offset, 0x90);
        check("l3_vote_value", writes[0].value, 5);
        check("l3_vote_no_capacity", k60_cpufreq_build_l3_vote(5, writes, 0), 0);
    }

    {
        K60CpuFreqWrite writes[K60_CPU_FREQ_MAX_WRITES], restore[K60_CPU_FREQ_MAX_WRITES];
        uint32_t original[K60_CPU_FREQ_MAX_WRITES] = {11, 12, 13, 14};
        uint32_t readback[K60_CPU_FREQ_MAX_WRITES] = {0};
        K60CpuFreqTable empty = clock;
        unsigned n, i;

        n = k60_cpufreq_build_votes(0, 1, clock.level[4], writes, K60_CPU_FREQ_MAX_WRITES);
        check("guard_ok", k60_cpufreq_vote_allowed(1, &clock, clock.level[4], n), 1);
        check("guard_disabled", k60_cpufreq_vote_allowed(0, &clock, clock.level[4], n), 0);
        empty.count = 0;
        check("guard_empty", k60_cpufreq_vote_allowed(1, &empty, clock.level[4], n), 0);
        check("guard_unlisted", k60_cpufreq_vote_allowed(1, &clock, 39, n), 0);
        check("guard_no_writes", k60_cpufreq_vote_allowed(1, &clock, clock.level[4], 0), 0);
        check("guard_oversize", k60_cpufreq_vote_allowed(1, &clock, clock.level[4], 9), 0);
        check("guard_null", k60_cpufreq_vote_allowed(1, NULL, clock.level[4], n), 0);

        for (i = 0; i < n; ++i) readback[i] = writes[i].value;
        check("readback_ok", k60_cpufreq_check_readback(writes, readback, n), 1);
        readback[2] = 0;
        check("readback_mismatch", k60_cpufreq_check_readback(writes, readback, n), 0);
        readback[2] = writes[2].value;
        check("readback_zero", k60_cpufreq_check_readback(writes, readback, 0), 0);
        check("readback_null_writes", k60_cpufreq_check_readback(NULL, readback, n), 0);
        check("readback_null_values", k60_cpufreq_check_readback(writes, NULL, n), 0);
        check("readback_oversize", k60_cpufreq_check_readback(writes, readback, 9), 0);

        n = k60_cpufreq_build_restore(writes, original, n, restore, K60_CPU_FREQ_MAX_WRITES);
        check("restore_count", n, 4);
        check("restore_offset0", restore[0].offset, 0x320);
        check("restore_offset3", restore[3].offset, 0x32c);
        check("restore_value0", restore[0].value, 11);
        check("restore_value3", restore[3].value, 14);
        check("restore_tight", k60_cpufreq_build_restore(writes, original, 4, restore, 3), 0);
        check("restore_null_original", k60_cpufreq_build_restore(writes, NULL, 4, restore,
            K60_CPU_FREQ_MAX_WRITES), 0);
        check("restore_zero", k60_cpufreq_build_restore(writes, original, 0, restore,
            K60_CPU_FREQ_MAX_WRITES), 0);
    }

    {
        K60CpuFreqGovernor gov;
        unsigned i;

        k60_cpufreq_governor_reset(&gov, 4);
        for (i = 0; i < K60_CPU_FREQ_DOWN_WINDOWS - 1; ++i)
            check("gov_drop_deferred", k60_cpufreq_governor_window(&gov, &clock, 0, 100, 0, 0), 0);
        check("gov_drop_lands", k60_cpufreq_governor_window(&gov, &clock, 0, 100, 0, 0), 1);
        check("gov_drop_level", gov.current[0], 0);
        check("gov_jump_now", k60_cpufreq_governor_window(&gov, &clock, 0, 950, 0, 0), 1);
        check("gov_jump_level", gov.current[0], 4);

        k60_cpufreq_governor_reset(&gov, 0);
        check("gov_boost_up", k60_cpufreq_governor_window(&gov, &clock, 1, 0, 1, 0), 1);
        check("gov_boost_level", gov.current[1], 4);
        check("gov_boost_boot_up", k60_cpufreq_governor_window(&gov, &clock, 0, 0, 1, 0), 1);
        check("gov_boost_boot_level", gov.current[0], 4);
        for (i = 0; i < K60_CPU_FREQ_DOWN_WINDOWS - 1; ++i)
            check("gov_release_hold", k60_cpufreq_governor_window(&gov, &clock, 1, 0, 0, 0), 0);
        check("gov_release_lands", k60_cpufreq_governor_window(&gov, &clock, 1, 0, 0, 0), 1);
        check("gov_release_level", gov.current[1], 1);
        /* A quiet shared cluster must walk down to the bottom and stay there:
         * the down-steps that release the half-top floor must not re-arm it. */
        k60_cpufreq_governor_reset(&gov, 0);
        for (i = 0; i < 24; ++i)
            (void)k60_cpufreq_governor_window(&gov, &clock, 1, 0, 0, 0);
        check("gov_quiet_settles", gov.current[1], 0);
        check("gov_quiet_stays", k60_cpufreq_governor_window(&gov, &clock, 1, 0, 0, 0), 0);
        check("gov_quiet_level", gov.current[1], 0);
        check("gov_bad_domain", k60_cpufreq_governor_window(&gov, &clock, 3, 0, 0, 0), -1);
        check("gov_null", k60_cpufreq_governor_window(NULL, &clock, 0, 0, 0, 0), -1);

        /* The same down latch runs under a hardware ceiling, and a ceiling
         * below the table refuses every level instead of clamping upward. */
        k60_cpufreq_governor_reset(&gov, 4);
        for (i = 0; i < K60_CPU_FREQ_DOWN_WINDOWS - 1; ++i)
            check("gov_cap_deferred", k60_cpufreq_governor_window_capped(&gov,
                &clock, 0, 950, 0, 0, 1000000), 0);
        check("gov_cap_lands", k60_cpufreq_governor_window_capped(&gov, &clock,
            0, 950, 0, 0, 1000000), 1);
        check("gov_cap_level", gov.current[0], 2);
        check("gov_cap_below", k60_cpufreq_governor_window_capped(&gov, &clock,
            0, 0, 0, 0, 100000), -1);
    }

    {
        uint64_t idle[K60_CPU_FREQ_CPUS] = {0};

        check("busy_full", k60_cpufreq_busy_permille(0, 16000000), 1000);
        check("busy_half", k60_cpufreq_busy_permille(8000000, 16000000), 500);
        check("busy_idle", k60_cpufreq_busy_permille(16000000, 16000000), 0);
        check("busy_over_idle", k60_cpufreq_busy_permille(17000000, 16000000), 0);
        check("busy_zero_window", k60_cpufreq_busy_permille(0, 0), 0);

        idle[0] = 16000000;
        idle[1] = 8000000;
        idle[2] = 16000000;
        idle[3] = 16000000;
        for (unsigned c = 4; c < 8; ++c) idle[c] = 16000000;
        check("domain0_busiest",
            k60_cpufreq_domain_busy(idle, K60_CPU_FREQ_CPUS, 16000000, 0), 500);
        check("domain1_idle",
            k60_cpufreq_domain_busy(idle, K60_CPU_FREQ_CPUS, 16000000, 1), 0);
        idle[7] = 4000000;
        check("domain2_prime",
            k60_cpufreq_domain_busy(idle, K60_CPU_FREQ_CPUS, 16000000, 2), 750);
        check("domain_bad",
            k60_cpufreq_domain_busy(idle, K60_CPU_FREQ_CPUS, 16000000, 3), 0);
        check("domain_null", k60_cpufreq_domain_busy(NULL, 8, 16000000, 0), 0);
        check("domain_zero_count", k60_cpufreq_domain_busy(idle, 0, 16000000, 0), 0);
    }

    {
        const uint32_t previous[4] = {100, 200, 300, 0};
        const uint32_t current[4] = {150, 260, 700, 0};
        uint64_t idle = 0, elapsed = 0;

        check("tick_delta_ok", k60_cpufreq_tick_delta(previous, current, &idle, &elapsed), 0);
        check("tick_delta_idle", idle, 400);
        check("tick_delta_elapsed", elapsed, 510);

        {
            const uint32_t wrap_prev[4] = {0, 0, 0xfffffff0u, 0};
            const uint32_t wrap_cur[4] = {8, 0, 0x10, 0};

            idle = 0;
            elapsed = 0;
            check("tick_delta_wrap", k60_cpufreq_tick_delta(wrap_prev, wrap_cur, &idle, &elapsed), 0);
            check("tick_delta_wrap_idle", idle, 32);
            check("tick_delta_wrap_elapsed", elapsed, 40);
        }

        idle = 0;
        elapsed = 0;
        check("tick_delta_still", k60_cpufreq_tick_delta(previous, previous, &idle, &elapsed), -1);
        check("tick_delta_null", k60_cpufreq_tick_delta(NULL, current, &idle, &elapsed), -1);
    }

    {
        uint64_t idle[K60_CPU_FREQ_CPUS];
        uint64_t elapsed[K60_CPU_FREQ_CPUS];

        for (unsigned c = 0; c < K60_CPU_FREQ_CPUS; ++c) {
            idle[c] = 16000000;
            elapsed[c] = 16000000;
        }
        idle[1] = 8000000;
        check("elapsed_domain0_busiest",
            k60_cpufreq_domain_busy_elapsed(idle, elapsed, K60_CPU_FREQ_CPUS, 0), 500);
        check("elapsed_domain1_idle",
            k60_cpufreq_domain_busy_elapsed(idle, elapsed, K60_CPU_FREQ_CPUS, 1), 0);
        idle[7] = 4000000;
        check("elapsed_domain2_prime",
            k60_cpufreq_domain_busy_elapsed(idle, elapsed, K60_CPU_FREQ_CPUS, 2), 750);
        check("elapsed_bad_domain",
            k60_cpufreq_domain_busy_elapsed(idle, elapsed, K60_CPU_FREQ_CPUS, 3), 0);
        check("elapsed_null",
            k60_cpufreq_domain_busy_elapsed(NULL, elapsed, K60_CPU_FREQ_CPUS, 0), 0);
        check("elapsed_zero_count",
            k60_cpufreq_domain_busy_elapsed(idle, elapsed, 0, 0), 0);
        elapsed[1] = 0;
        idle[1] = 0;
        check("elapsed_zero_window",
            k60_cpufreq_domain_busy_elapsed(idle, elapsed, K60_CPU_FREQ_CPUS, 0), 0);
    }

    {
        K60CpuFreqWrite w[2] = {};
        check("pdmem_offset0", k60_cpufreq_pdmem_offset(0), 0x804);
        check("pdmem_offset1", k60_cpufreq_pdmem_offset(1), 0x808);
        check("pdmem_offset2", k60_cpufreq_pdmem_offset(2), 0x80c);
        check("pdmem_bad_domain", k60_cpufreq_pdmem_offset(3), 0);
        check("pdmem_build", k60_cpufreq_build_pdmem_vote(1, 16, w, 2), 1);
        check("pdmem_build_offset", w[0].offset, 0x808);
        check("pdmem_build_value", w[0].value, 16);
        check("pdmem_build_bad_domain", k60_cpufreq_build_pdmem_vote(3, 16, w, 2), 0);
        check("pdmem_build_bad_level",
            k60_cpufreq_build_pdmem_vote(0, K60_CPU_FREQ_LUT_ROWS, w, 2), 0);
        check("pdmem_build_tight", k60_cpufreq_build_pdmem_vote(0, 3, w, 0), 0);
        check("pdmem_build_null", k60_cpufreq_build_pdmem_vote(0, 3, NULL, 2), 0);
    }

    printf("%s %u checks (%u failure%s)\n", failures ? "TESTS FAILED" : "TESTS OK",
        checks, failures, failures == 1 ? "" : "s");
    return failures ? 1 : 0;
}
