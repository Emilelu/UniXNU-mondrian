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
    K60GpuDcvs dcvs;
    K60GpuGovernor dgov;
    unsigned want = 0;
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

    k60_gpu_dcvs_reset(&dcvs, &dgov, 0, 0);
    check("dcvs floor default", dcvs.level, 1);
    check("dcvs top default", dcvs.top, 13);
    check("dcvs gov floor", dgov.level, 1);
    k60_gpu_dcvs_reset(&dcvs, &dgov, 1, 13);
    check("dcvs reset level", dcvs.level, 1);
    check("dcvs reset wakes", dcvs.wakes, 0);
    check("dcvs reset idle", (unsigned)dcvs.idle, 0);

    check("dcvs idle window", k60_gpu_dcvs_window(&dcvs, &dgov, &table, 0,
        16000000ull, 1000000000ull, 50, K60_GPU_WAKE_MIN_KHZ, &want), 0);
    check("dcvs idle flag", (unsigned)dcvs.idle, 1);
    check("dcvs idle ms", dcvs.idle_ms, 16);
    check("dcvs idle want", want, 1);
    check("dcvs idle again", k60_gpu_dcvs_window(&dcvs, &dgov, &table, 0,
        16000000ull, 1016000000ull, 50, K60_GPU_WAKE_MIN_KHZ, &want), 0);
    check("dcvs idle ms sum", dcvs.idle_ms, 32);

    check("dcvs wake window", k60_gpu_dcvs_window(&dcvs, &dgov, &table, 4800,
        16000000ull, 1032000000ull, 50, K60_GPU_WAKE_MIN_KHZ, &want), 0);
    check("dcvs wake count", dcvs.wakes, 1);
    check("dcvs wake level", dcvs.wake_level, 7);
    check("dcvs wake want", want, 7);
    check("dcvs wake end", (unsigned)(dcvs.wake_end_ns / 1000000ull),
        (unsigned)((1032000000ull + 50000000ull) / 1000000ull));
    check("dcvs idle cleared", (unsigned)dcvs.idle, 0);
    check("dcvs idle ms reset", dcvs.idle_ms, 0);

    check("dcvs vote ok", k60_gpu_dcvs_voted(&dcvs, &dgov, 7, 1), 0);
    check("dcvs voted level", dcvs.level, 7);
    check("dcvs voted gov", dgov.level, 7);
    check("dcvs voted changes", dcvs.changes, 1);
    check("dcvs voted refused", dcvs.refused, 0);

    k60_gpu_dcvs_reset(&dcvs, &dgov, 1, 13);
    (void)k60_gpu_dcvs_window(&dcvs, &dgov, &table, 0, 16000000ull,
        2000000000ull, 50, K60_GPU_WAKE_MIN_KHZ, &want);
    (void)k60_gpu_dcvs_window(&dcvs, &dgov, &table, 4800, 16000000ull,
        2016000000ull, 50, K60_GPU_WAKE_MIN_KHZ, &want);
    check("dcvs wake held", want, 7);
    check("dcvs wake expires", k60_gpu_dcvs_window(&dcvs, &dgov, &table, 4800,
        16000000ull, 2067000000ull, 50, K60_GPU_WAKE_MIN_KHZ, &want), 0);
    check("dcvs wake gone want", want, 1);

    k60_gpu_dcvs_reset(&dcvs, &dgov, 1, 13);
    (void)k60_gpu_dcvs_window(&dcvs, &dgov, &table, 0, 16000000ull,
        3000000000ull, 50, K60_GPU_WAKE_MIN_KHZ, &want);
    (void)k60_gpu_dcvs_window(&dcvs, &dgov, &table, 4800, 16000000ull,
        3016000000ull, 0, K60_GPU_WAKE_MIN_KHZ, &want);
    check("dcvs no boost", dcvs.wakes, 0);
    check("dcvs no boost want", want, 1);

    k60_gpu_dcvs_reset(&dcvs, &dgov, 1, 4);
    check("dcvs top window", k60_gpu_dcvs_window(&dcvs, &dgov, &table, 307200,
        16000000ull, 4000000000ull, 50, K60_GPU_WAKE_MIN_KHZ, &want), 0);
    check("dcvs top clamp", want, 4);
    check("dcvs top gov", dgov.level, 13);

    k60_gpu_dcvs_reset(&dcvs, &dgov, 9, 13);
    check("dcvs floor window", k60_gpu_dcvs_window(&dcvs, &dgov, &table, 0,
        100000000ull, 4100000000ull, 50, K60_GPU_WAKE_MIN_KHZ, &want), 0);
    check("dcvs floor clamp", want, 9);
    check("dcvs floor gov", dgov.level, 1);

    k60_gpu_dcvs_reset(&dcvs, &dgov, 1, 13);
    for (unsigned i = 0; i < 7; i++)
        check("dcvs refusal holds", k60_gpu_dcvs_voted(&dcvs, &dgov, 5, 0), 0);
    check("dcvs refusal stops", k60_gpu_dcvs_voted(&dcvs, &dgov, 5, 0), 1);
    check("dcvs refusal count", dcvs.refused, 8);

    k60_gpu_dcvs_reset(&dcvs, &dgov, 1, 13);
    for (unsigned i = 0; i < 3; i++)
        (void)k60_gpu_dcvs_voted(&dcvs, &dgov, 5, 0);
    check("dcvs accept resets", k60_gpu_dcvs_voted(&dcvs, &dgov, 5, 1), 0);
    check("dcvs accept refused", dcvs.refused, 0);
    for (unsigned i = 0; i < 7; i++)
        check("dcvs refusal again", k60_gpu_dcvs_voted(&dcvs, &dgov, 5, 0), 0);
    check("dcvs stops again", k60_gpu_dcvs_voted(&dcvs, &dgov, 5, 0), 1);

    check("dcvs window null", k60_gpu_dcvs_window(0, &dgov, &table, 0, 16000000ull,
        0, 0, 0, &want), (unsigned)-1);
    check("dcvs window no want", k60_gpu_dcvs_window(&dcvs, &dgov, &table, 0,
        16000000ull, 0, 0, 0, 0), (unsigned)-1);
    check("dcvs vote null", k60_gpu_dcvs_voted(0, &dgov, 1, 1), 1);

    if (failures) printf("TESTS FAILED %u failures / %u checks\n", failures, checks);
    else printf("TESTS OK %u checks (0 failures)\n", checks);
    return failures ? 1 : 0;
}
