/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include <stdio.h>
#include <string.h>
#include "../../drivers/PongPower/K60GpuFreqPlan.h"

static unsigned failures, checks;
static void check(const char *name, unsigned got, unsigned want)
{
    checks++;
    if (got != want) { failures++; printf("FAIL %s: got %u want %u\n", name, got, want); }
}
static const uint32_t live_khz[13] = {
    900000, 862000, 815000, 765000, 710000, 645000, 580000,
    515000, 440000, 364000, 323000, 285000, 220000
};
int main(void)
{
    K60GpuTable table;
    K60GpuGovernor gov;
    uint32_t out[3] = {0, 0, 0};
    uint32_t dup[4] = {900000, 900000, 0, 220000};

    memset(&table, 0, sizeof(table));
    check("build count", k60_gpu_build_table(live_khz, 13, &table), 13);
    check("lowest", table.khz[0], 220000);
    check("second", table.khz[1], 285000);
    check("highest", table.khz[12], 900000);
    check("wire 6", table.khz[5], 515000);
    check("build rejects 14", k60_gpu_build_table(live_khz, 14, &table), 0);
    check("build rejects null", k60_gpu_build_table(0, 13, &table), 0);
    check("build rejects empty", k60_gpu_build_table(live_khz, 0, &table), 0);
    check("build drops dup/zero", k60_gpu_build_table(dup, 4, &table), 2);
    check("dedup low", table.khz[0], 220000);
    check("dedup high", table.khz[1], 900000);
    k60_gpu_build_table(live_khz, 13, &table);

    check("busy half", k60_gpu_busy_permille(9600, 1000), 500);
    check("busy full", k60_gpu_busy_permille(19200, 1000), 1000);
    check("busy zero window", k60_gpu_busy_permille(100, 0), 0);
    check("busy clamps", k60_gpu_busy_permille(40000, 1000), 1000);
    check("busy quarter", k60_gpu_busy_permille(4800, 500), 500);

    check("target holds 50", k60_gpu_target(&table, 6, 500), 6);
    check("target up", k60_gpu_target(&table, 6, 700), 11);
    check("target down", k60_gpu_target(&table, 6, 200), 5);
    check("target top busy", k60_gpu_target(&table, 3, 900), 13);
    check("target zero busy", k60_gpu_target(&table, 6, 0), 5);
    check("target top zero busy", k60_gpu_target(&table, 13, 100), 12);
    check("target floor", k60_gpu_target(&table, 1, 0), 1);
    check("target bad level", k60_gpu_target(&table, 0, 500), 0);
    check("target bad table", k60_gpu_target(0, 1, 500), 0);

    k60_gpu_governor_reset(&gov, 1);
    check("gov reset", gov.level, 1);
    check("gov up", k60_gpu_governor_window(&gov, &table, 700, 0), 1);
    check("gov up level", gov.level, 4);
    check("gov up latch", gov.after_up, 1);
    check("gov quiet 1", k60_gpu_governor_window(&gov, &table, 0, 0), 0);
    check("gov quiet 4", gov.down, 1);
    check("gov quiet 5", k60_gpu_governor_window(&gov, &table, 0, 0), 0);
    check("gov quiet 6", k60_gpu_governor_window(&gov, &table, 0, 0), 0);
    check("gov quiet 7", k60_gpu_governor_window(&gov, &table, 0, 0), 0);
    check("gov after up limit", gov.down, 4);
    check("gov down after up", k60_gpu_governor_window(&gov, &table, 0, 0), 1);
    check("gov down level", gov.level, 3);
    check("gov down cleared", gov.after_up, 0);
    check("gov down 1", k60_gpu_governor_window(&gov, &table, 0, 0), 0);
    check("gov down 2", k60_gpu_governor_window(&gov, &table, 0, 0), 0);
    check("gov down 3", k60_gpu_governor_window(&gov, &table, 0, 0), 0);
    check("gov down 4", k60_gpu_governor_window(&gov, &table, 0, 0), 1);
    check("gov down twice", gov.level, 2);
    check("gov idle", k60_gpu_governor_window(&gov, &table, 0, 80), 1);
    check("gov idle level", gov.level, 1);
    check("gov bad domain", k60_gpu_governor_window(0, &table, 0, 0), (unsigned)-1);
    k60_gpu_governor_reset(&gov, 0);
    check("gov floor default", gov.level, 1);
    gov.level = 14;
    check("gov bad level", k60_gpu_governor_window(&gov, &table, 0, 0), (unsigned)-1);

    check("vote words", k60_gpu_vote_payload(7, 2, out), 3);
    check("vote id", out[0], 1);
    check("vote level", out[1], 7);
    check("vote bw", out[2], 2);
    check("vote top", k60_gpu_vote_payload(13, 11, out), 3);
    check("vote rejects level 0", k60_gpu_vote_payload(0, 1, out), 0);
    check("vote rejects bw", k60_gpu_vote_payload(1, 256, out), 0);
    check("vote rejects null", k60_gpu_vote_payload(1, 1, 0), 0);

    check("level exact", k60_gpu_level_for_khz(&table, 515000), 6);
    check("level between", k60_gpu_level_for_khz(&table, 600000), 8);
    check("level below", k60_gpu_level_for_khz(&table, 200000), 1);
    check("level above", k60_gpu_level_for_khz(&table, 990000), 13);
    check("level null", k60_gpu_level_for_khz(0, 515000), 0);
    check("wake min 578", k60_gpu_wake_level(&table, 1, 578000), 7);
    check("wake doubles", k60_gpu_wake_level(&table, 4, 578000), 10);
    check("wake clamps top", k60_gpu_wake_level(&table, 13, 578000), 13);
    check("wake zero level", k60_gpu_wake_level(&table, 0, 578000), 0);
    check("wake null", k60_gpu_wake_level(0, 4, 578000), 0);

    if (failures) printf("TESTS FAILED %u failures / %u checks\n", failures, checks);
    else printf("TESTS OK %u checks (0 failures)\n", checks);
    return failures ? 1 : 0;
}
