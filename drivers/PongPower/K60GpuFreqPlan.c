/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include "K60GpuFreqPlan.h"

static unsigned lower_bound(const K60GpuTable *t, uint64_t khz)
{
    unsigned i = 0;
    while (i < t->count && t->khz[i] < khz) i++;
    return i < t->count ? i + 1 : t->count;
}

unsigned k60_gpu_build_table(const uint32_t *descending_khz, unsigned count,
    K60GpuTable *out)
{
    unsigned used = 0;
    if (!descending_khz || !out || count == 0 || count > K60_GPU_MAX_LEVELS) return 0;
    for (unsigned i = count; i > 0; i--) {
        uint32_t khz = descending_khz[i - 1];
        unsigned dup = 0;
        if (khz == 0) continue;
        for (unsigned j = 0; j < used; j++) if (out->khz[j] == khz) { dup = 1; break; }
        if (dup) continue;
        out->khz[used++] = khz;
    }
    out->count = used;
    return used;
}

unsigned k60_gpu_busy_permille(uint64_t busy_ticks, uint64_t elapsed_us)
{
    uint64_t ticks, permille;
    if (elapsed_us == 0) return 0;
    ticks = elapsed_us * K60_GPU_XO_KHZ / 1000u;
    if (ticks == 0) return 0;
    permille = busy_ticks * 1000u / ticks;
    return permille > 1000u ? 1000u : (unsigned)permille;
}

unsigned k60_gpu_target(const K60GpuTable *table, unsigned current,
    unsigned busy_permille)
{
    uint64_t need, want;
    if (!table || table->count == 0 || current < 1 || current > table->count) return 0;
    if (busy_permille >= K60_GPU_TOP_BUSY) return table->count;
    if (busy_permille == 0) return current > 1 ? current - 1 : 1;
    need = ((uint64_t)table->khz[current - 1] * busy_permille + K60_GPU_TARGET_BUSY - 1)
        / K60_GPU_TARGET_BUSY;
    if (need > table->khz[current - 1]) {
        want = (need * K60_GPU_MARGIN_PCT + 99) / 100;
        if (want <= table->khz[current - 1]) return current;
        return lower_bound(table, want);
    }
    if (current > 1 && need * 100 <= (uint64_t)table->khz[current - 2] * K60_GPU_DOWN_PCT)
        return current - 1;
    return current;
}

void k60_gpu_governor_reset(K60GpuGovernor *gov, unsigned floor)
{
    if (!gov) return;
    gov->level = floor ? floor : 1;
    gov->down = 0;
    gov->after_up = 0;
}

int k60_gpu_governor_window(K60GpuGovernor *gov, const K60GpuTable *table,
    unsigned busy_permille, unsigned idle_ms)
{
    unsigned target, limit;
    if (!gov || !table || table->count == 0) return -1;
    if (gov->level < 1 || gov->level > table->count) return -1;
    if (idle_ms >= K60_GPU_IDLE_MS) {
        gov->level = 1; gov->down = 0; gov->after_up = 0;
        return 1;
    }
    if (busy_permille >= K60_GPU_TOP_BUSY) {
        gov->level = table->count; gov->down = 0; gov->after_up = 0;
        return 1;
    }
    target = k60_gpu_target(table, gov->level, busy_permille);
    if (target > gov->level) {
        gov->level = target; gov->down = 0; gov->after_up = 1;
        return 1;
    }
    if (target < gov->level) {
        limit = gov->after_up ? K60_GPU_DOWN_AFTER_UP : K60_GPU_DOWN_WINDOWS;
        if (++gov->down < limit) return 0;
        gov->level--; gov->down = 0; gov->after_up = 0;
        return 1;
    }
    gov->down = 0;
    return 0;
}

unsigned k60_gpu_vote_payload(unsigned level, unsigned bandwidth, uint32_t out[3])
{
    if (!out || level == 0 || level > 255 || bandwidth > 255) return 0;
    out[0] = 1; out[1] = level; out[2] = bandwidth;
    return 3;
}

unsigned k60_gpu_level_for_khz(const K60GpuTable *table, uint64_t khz)
{
    if (!table || !table->count) return 0;
    for (unsigned i = 0; i < table->count; i++)
        if (table->khz[i] >= khz) return i + 1;
    return table->count;
}

unsigned k60_gpu_wake_level(const K60GpuTable *table, unsigned current,
    uint64_t min_khz)
{
    if (!table || !table->count || current == 0) return 0;
    if (current > table->count) current = table->count;
    uint64_t target = (uint64_t)table->khz[current - 1] * 2u;
    if (target < min_khz) target = min_khz;
    return k60_gpu_level_for_khz(table, target);
}
