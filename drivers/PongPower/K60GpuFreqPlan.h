/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#ifndef K60_GPU_FREQ_PLAN_H
#define K60_GPU_FREQ_PLAN_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* The live Pong profile has 13 GPU OPPs, 900 MHz down to 220 MHz. The HFI
 * performance table is built in ascending order with wire index 1 at the
 * lowest OPP and index 13 at the highest (index 0 is the level-0 entry);
 * this plan uses that same 1-based index so a vote needs no second mapping. */
#define K60_GPU_MAX_LEVELS 13
#define K60_GPU_XO_KHZ 19200u
#define K60_GPU_TARGET_BUSY 500u   /* msm_gpu_devfreq upthreshold 50 % */
#define K60_GPU_TOP_BUSY 850u
#define K60_GPU_MARGIN_PCT 110u
#define K60_GPU_DOWN_PCT 80u
#define K60_GPU_DOWN_WINDOWS 4u
#define K60_GPU_DOWN_AFTER_UP 5u
#define K60_GPU_IDLE_MS 80u

typedef struct { uint32_t khz[K60_GPU_MAX_LEVELS]; unsigned count; } K60GpuTable;
typedef struct { unsigned level; unsigned down; unsigned after_up; } K60GpuGovernor;

/* Sort the descending live profile into wire order. Returns the level count,
 * or 0 for a null/empty/oversized table. Duplicate or zero frequencies are
 * dropped, so count may be smaller than the input. */
unsigned k60_gpu_build_table(const uint32_t *descending_khz, unsigned count,
    K60GpuTable *out);
/* Busy share in per mille from the GMU XO counter delta (19.2 MHz ticks) and
 * the wall time of the same window. Returns 0 for a zero window and clamps a
 * counter that outran the clock to 1000. */
unsigned k60_gpu_busy_permille(uint64_t busy_ticks, uint64_t elapsed_us);
/* Frequency that would have kept the window at 50 % busy, then the level at
 * or above 1.1x of it; top for >=85 % busy, one level down only while the
 * caller's down-window count allows it. No vote, no MMIO. */
unsigned k60_gpu_target(const K60GpuTable *table, unsigned current,
    unsigned busy_permille);
/* Stateful 16 ms window rule: up immediately, down only after 4 quiet windows
 * (5 right after a step up), back to the lowest level after 80 ms idle.
 * Returns 1 when the level changed, 0 when it held, -1 on bad arguments. */
void k60_gpu_governor_reset(K60GpuGovernor *gov, unsigned floor);
int k60_gpu_governor_window(K60GpuGovernor *gov, const K60GpuTable *table,
    unsigned busy_permille, unsigned idle_ms);
/* HFI GX_BW_PERF_VOTE payload excluding the wire header: {1, level, bandwidth}.
 * Returns 3, or 0 when the level/bandwidth is outside the wire field. */
unsigned k60_gpu_vote_payload(unsigned level, unsigned bandwidth, uint32_t out[3]);
#ifdef __cplusplus
}
#endif
#endif
