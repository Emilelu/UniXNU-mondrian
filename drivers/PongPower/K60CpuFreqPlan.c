/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#include "K60CpuFreqPlan.h"

uint32_t k60_cpufreq_row_khz(uint32_t row)
{
    if (row >> 30) return K60_CPU_FREQ_XO_KHZ * (row & 0xffu);
    return K60_CPU_FREQ_GPLL_HALF_KHZ;
}

unsigned k60_cpufreq_row_cores(uint32_t row)
{
    return (row >> 16) & 7u;
}

unsigned k60_cpufreq_row_turbo(uint32_t row)
{
    return k60_cpufreq_row_cores(row) == 1u;
}

int k60_cpufreq_build_table(const uint32_t *rows, unsigned row_count, uint32_t cap_khz,
    K60CpuFreqTable *out)
{
    uint32_t previous = 0;
    unsigned kept = 0, i;

    if (!rows || !out || !row_count) return -1;
    out->count = 0;
    for (i = 0; i < row_count && i < K60_CPU_FREQ_LUT_ROWS; ++i) {
        const uint32_t khz = k60_cpufreq_row_khz(rows[i]);
        unsigned at;
        if (i && khz == previous) break;
        previous = khz;
        if (k60_cpufreq_row_turbo(rows[i])) continue;
        if (cap_khz && khz > cap_khz) continue;
        at = kept;
        while (at > 0 && out->khz[at - 1] > khz) {
            out->khz[at] = out->khz[at - 1];
            out->level[at] = out->level[at - 1];
            --at;
        }
        out->khz[at] = khz;
        out->level[at] = (uint8_t)i;
        ++kept;
    }
    out->count = kept;
    return kept ? 0 : -1;
}

int k60_cpufreq_pick_highest(const K60CpuFreqTable *table, uint32_t cap_khz,
    unsigned *index, uint32_t *khz)
{
    int best = -1;
    unsigned i;

    if (!table || !table->count) return -1;
    for (i = 0; i < table->count; ++i) {
        if (cap_khz && table->khz[i] > cap_khz) continue;
        if (best < 0 || table->khz[i] >= table->khz[best]) best = (int)i;
    }
    if (best < 0) return -1;
    if (index) *index = (unsigned)best;
    if (khz) *khz = table->khz[best];
    return 0;
}

unsigned k60_cpufreq_target(const K60CpuFreqTable *table, unsigned current,
    unsigned busy_permille, unsigned shared_cluster, unsigned boost,
    unsigned framing, unsigned quiet_windows)
{
    unsigned want;

    if (!table || !table->count) return 0;
    if (current >= table->count) current = table->count - 1;
    if (busy_permille >= K60_CPU_FREQ_HISPEED) {
        want = table->count - 1;
    } else {
        const uint64_t need = (uint64_t)table->khz[current] * busy_permille *
            K60_CPU_FREQ_MARGIN / 100000u;
        want = 0;
        while (want + 1 < table->count && table->khz[want] < need) ++want;
    }
    if (framing) {
        const uint64_t floor = (uint64_t)table->khz[table->count - 1] *
            K60_CPU_FREQ_FRAME_PCT / 100u;
        while (want + 1 < table->count && table->khz[want] < floor) ++want;
    }
    if (shared_cluster) {
        if (boost) {
            want = table->count - 1;
        } else if (quiet_windows < K60_CPU_FREQ_QUIET_WINDOWS) {
            const uint64_t half = table->khz[table->count - 1] / 2u;
            while (want + 1 < table->count && table->khz[want] < half) ++want;
        }
    }
    return want;
}

unsigned k60_cpufreq_step(const K60CpuFreqTable *table, unsigned *current,
    unsigned want, unsigned *down)
{
    if (!table || !current || !down || !table->count) return 0;
    if (*current >= table->count) *current = table->count - 1;
    if (want >= table->count) want = table->count - 1;
    if (want > *current) {
        *current = want;
        *down = 0;
        return 1;
    }
    if (want < *current) {
        if (++*down >= K60_CPU_FREQ_DOWN_WINDOWS) {
            *current = want;
            *down = 0;
            return 1;
        }
        return 0;
    }
    *down = 0;
    return 0;
}

unsigned k60_cpufreq_domain_of_cpu(unsigned cpu)
{
    if (cpu < 4) return 0;
    if (cpu < 7) return 1;
    return 2;
}

unsigned k60_cpufreq_domain_cores(unsigned domain)
{
    static const unsigned cores[K60_CPU_FREQ_DOMAINS] = {4, 3, 1};
    return domain < K60_CPU_FREQ_DOMAINS ? cores[domain] : 0;
}

unsigned k60_cpufreq_build_votes(unsigned domain, unsigned dcvs_ctrl, unsigned level,
    K60CpuFreqWrite *out, unsigned capacity)
{
    const unsigned cores = k60_cpufreq_domain_cores(domain);
    unsigned writes = dcvs_ctrl && cores > 1 ? cores : 1, i;

    if (!out || capacity < writes) return 0;
    out[0].offset = K60_CPU_FREQ_REG_PERF_STATE;
    out[0].value = level;
    for (i = 1; i < writes; ++i) {
        out[i].offset = K60_CPU_FREQ_REG_PERF_STATE + i * 4;
        out[i].value = level;
    }
    return writes;
}

unsigned k60_cpufreq_build_l3_vote(unsigned level, K60CpuFreqWrite *out, unsigned capacity)
{
    if (!out || !capacity) return 0;
    out[0].offset = K60_CPU_FREQ_REG_L3_VOTE;
    out[0].value = level;
    return 1;
}
