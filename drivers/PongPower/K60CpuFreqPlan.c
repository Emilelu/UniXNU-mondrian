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

int k60_cpufreq_pick_lowest(const K60CpuFreqTable *table, unsigned *index,
    uint32_t *khz)
{
    unsigned best = 0, i;

    if (!table || !table->count) return -1;
    for (i = 1; i < table->count; ++i) {
        if (table->khz[i] < table->khz[best]) best = i;
    }
    if (index) *index = best;
    if (khz) *khz = table->khz[best];
    return 0;
}

int k60_cpufreq_pick_at_least(const K60CpuFreqTable *table, uint32_t khz,
    unsigned *index, uint32_t *out)
{
    int best = -1;
    unsigned i;

    if (!table || !table->count) return -1;
    for (i = 0; i < table->count; ++i) {
        if (table->khz[i] < khz) continue;
        if (best < 0 || table->khz[i] < table->khz[best]) best = (int)i;
    }
    if (best < 0) return -1;
    if (index) *index = (unsigned)best;
    if (out) *out = table->khz[best];
    return 0;
}

int k60_cpufreq_l3_target(const K60CpuFreqTable *l3,
    const uint32_t *domain_khz, const uint32_t *domain_top, unsigned boost,
    unsigned *index, uint32_t *khz)
{
    uint64_t share = 0, target;
    uint32_t top = 0;
    unsigned topIndex = 0, domain;

    if (!l3 || !l3->count || !domain_khz || !domain_top) return -1;
    if (k60_cpufreq_pick_highest(l3, 0, &topIndex, &top)) return -1;
    if (boost) {
        if (index) *index = topIndex;
        if (khz) *khz = top;
        return 0;
    }
    for (domain = 0; domain < K60_CPU_FREQ_DOMAINS; ++domain) {
        uint64_t candidate;
        if (!domain_top[domain] || !domain_khz[domain]) continue;
        candidate = (uint64_t)domain_khz[domain] * 1000000u / domain_top[domain];
        if (candidate > share) share = candidate;
    }
    if (!share) return -1;
    if (share > 1000000u) share = 1000000u;
    target = (uint64_t)top * share / 1000000u;
    if (k60_cpufreq_pick_at_least(l3, (uint32_t)target, index, khz)) {
        if (index) *index = topIndex;
        if (khz) *khz = top;
    }
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
    if (boost) {
        /* A touch boost holds every domain at the top. The shared clusters
         * take it on their own rail; the boot cluster needs it too, because
         * the performance clusters ignore the vote and this is the only
         * cluster where the boost becomes visible in the hardware. */
        want = table->count - 1;
    } else if (shared_cluster && quiet_windows < K60_CPU_FREQ_QUIET_WINDOWS) {
        const uint64_t half = table->khz[table->count - 1] / 2u;
        while (want + 1 < table->count && table->khz[want] < half) ++want;
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

unsigned k60_cpufreq_busy_permille(uint64_t idle_delta, uint64_t elapsed)
{
    uint64_t busy;

    if (!elapsed || idle_delta >= elapsed) return 0;
    busy = (elapsed - idle_delta) * 1000u / elapsed;
    return busy > 1000u ? 1000u : (unsigned)busy;
}

unsigned k60_cpufreq_domain_busy(const uint64_t *idle_delta, unsigned count,
    uint64_t elapsed, unsigned domain)
{
    unsigned cpu, busy = 0;

    if (!idle_delta || !count || count > K60_CPU_FREQ_CPUS ||
        domain >= K60_CPU_FREQ_DOMAINS)
        return 0;
    for (cpu = 0; cpu < count; ++cpu) {
        unsigned b;
        if (k60_cpufreq_domain_of_cpu(cpu) != domain) continue;
        b = k60_cpufreq_busy_permille(idle_delta[cpu], elapsed);
        if (b > busy) busy = b;
    }
    return busy;
}

unsigned k60_cpufreq_domain_busy_elapsed(const uint64_t *idle_delta,
    const uint64_t *elapsed, unsigned count, unsigned domain)
{
    unsigned cpu, busy = 0;

    if (!idle_delta || !elapsed || !count || count > K60_CPU_FREQ_CPUS ||
        domain >= K60_CPU_FREQ_DOMAINS)
        return 0;
    for (cpu = 0; cpu < count; ++cpu) {
        unsigned b;
        if (k60_cpufreq_domain_of_cpu(cpu) != domain) continue;
        b = k60_cpufreq_busy_permille(idle_delta[cpu], elapsed[cpu]);
        if (b > busy) busy = b;
    }
    return busy;
}

int k60_cpufreq_tick_delta(const uint32_t previous[4], const uint32_t current[4],
    uint64_t *idle, uint64_t *elapsed)
{
    uint64_t total = 0, stopped = 0;
    unsigned state;

    if (!previous || !current || !idle || !elapsed) return -1;
    for (state = 0; state < 4; ++state) {
        const uint32_t delta = current[state] - previous[state];
        total += delta;
        if (state == K60_CPU_FREQ_STATE_IDLE) stopped = delta;
    }
    *idle = stopped;
    *elapsed = total;
    return total ? 0 : -1;
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

unsigned k60_cpufreq_pdmem_offset(unsigned domain)
{
    if (domain >= K60_CPU_FREQ_DOMAINS) return 0;
    return K60_CPU_FREQ_PDMEM_VOTE_OFFSET + 4 * domain;
}

unsigned k60_cpufreq_build_pdmem_vote(unsigned domain, unsigned level, K60CpuFreqWrite *out, unsigned capacity)
{
    const unsigned offset = k60_cpufreq_pdmem_offset(domain);

    if (!out || !capacity || !offset || level >= K60_CPU_FREQ_LUT_ROWS) return 0;
    out[0].offset = offset;
    out[0].value = level;
    return 1;
}

int k60_cpufreq_vote_allowed(unsigned enable, const K60CpuFreqTable *table,
    unsigned level, unsigned writes)
{
    unsigned i;

    if (!enable || !table || !table->count || table->count > K60_CPU_FREQ_LUT_ROWS ||
        !writes || writes > K60_CPU_FREQ_MAX_WRITES ||
        level >= K60_CPU_FREQ_LUT_ROWS)
        return 0;
    for (i = 0; i < table->count; ++i)
        if (table->level[i] == level) return 1;
    return 0;
}

int k60_cpufreq_check_readback(const K60CpuFreqWrite *writes,
    const uint32_t *readback, unsigned count)
{
    unsigned i;

    if (!writes || !readback || !count || count > K60_CPU_FREQ_MAX_WRITES)
        return 0;
    for (i = 0; i < count; ++i)
        if (readback[i] != writes[i].value) return 0;
    return 1;
}

unsigned k60_cpufreq_build_restore(const K60CpuFreqWrite *writes,
    const uint32_t *original, unsigned count, K60CpuFreqWrite *out,
    unsigned capacity)
{
    unsigned i;

    if (!writes || !original || !out || !count ||
        count > K60_CPU_FREQ_MAX_WRITES || capacity < count)
        return 0;
    for (i = 0; i < count; ++i) {
        out[i].offset = writes[i].offset;
        out[i].value = original[i];
    }
    return count;
}

void k60_cpufreq_governor_reset(K60CpuFreqGovernor *gov, unsigned level)
{
    unsigned d;

    if (!gov) return;
    for (d = 0; d < K60_CPU_FREQ_DOMAINS; ++d) {
        gov->current[d] = level;
        gov->down[d] = 0;
        gov->quiet[d] = 0;
    }
}

int k60_cpufreq_governor_window(K60CpuFreqGovernor *gov, const K60CpuFreqTable *table,
    unsigned domain, unsigned busy_permille, unsigned boost, unsigned framing)
{
    unsigned quiet, want;
    int changed;

    if (!gov || !table || !table->count || domain >= K60_CPU_FREQ_DOMAINS) return -1;
    quiet = gov->quiet[domain];
    if (busy_permille < K60_CPU_FREQ_QUIET_BUSY) {
        if (quiet < K60_CPU_FREQ_QUIET_WINDOWS) ++quiet;
    } else {
        quiet = 0;
    }
    gov->quiet[domain] = quiet;
    want = k60_cpufreq_target(table, gov->current[domain], busy_permille,
        domain != 0, boost, framing, quiet);
    changed = (int)k60_cpufreq_step(table, &gov->current[domain], want, &gov->down[domain]);
    return changed;
}
