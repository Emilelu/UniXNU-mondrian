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
    /* Shared clusters: boost pins the top, quiet holds at least the half. */
    check("target_boost", k60_cpufreq_target(&clock, 0, 0, 1, 1, 0, 0), 4);
    check("target_quiet", k60_cpufreq_target(&clock, 0, 0, 1, 0, 0, 0), 1);
    check("target_quiet_done", k60_cpufreq_target(&clock, 0, 0, 1, 0, 0,
        K60_CPU_FREQ_QUIET_WINDOWS), 0);
    /* The boot cluster never takes the shared-cluster floors. */
    check("target_boot_boost", k60_cpufreq_target(&clock, 0, 0, 0, 1, 0, 0), 0);
    check("target_empty", k60_cpufreq_target(NULL, 0, 0, 0, 0, 0, 0), 0);

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

    printf("%s %u checks (%u failure%s)\n", failures ? "TESTS FAILED" : "TESTS OK",
        checks, failures, failures == 1 ? "" : "s");
    return failures ? 1 : 0;
}
