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
/* Lowest 1-based level whose OPP is at or above khz, or the top level when no
 * OPP reaches it. 0 on a missing/empty table. No MMIO. */
unsigned k60_gpu_level_for_khz(const K60GpuTable *table, uint64_t khz);
/* Wake boost floor (official section 5: 2x the pre-idle clock, at least
 * 578 MHz, for 50 ms). Returns the 1-based level, clamped to the table top;
 * 0 on a missing table or a zero current level. No MMIO. */
unsigned k60_gpu_wake_level(const K60GpuTable *table, unsigned current,
    uint64_t min_khz);
/* HFI GX_BW_PERF_VOTE payload excluding the wire header: {1, level, bandwidth}.
 * Returns 3, or 0 when the level/bandwidth is outside the wire field. */
unsigned k60_gpu_vote_payload(unsigned level, unsigned bandwidth, uint32_t out[3]);

/* Wake boost floor and the refusal budget the DCVS thread applies. */
#define K60_GPU_WAKE_MIN_KHZ 578000u
#define K60_GPU_STOP_REFUSALS 8u

/* Runtime state of the GPU DCVS thread: the hardware level, the wake boost and
 * the counters the 10 s summary prints. The governor keeps its own level; both
 * move together on a successful vote. */
typedef struct {
    unsigned level;
    unsigned floor;
    unsigned top;
    unsigned wake_level;
    uint64_t wake_end_ns;
    unsigned idle_ms;
    int idle;
    unsigned wakes;
    unsigned changes;
    unsigned refused;
} K60GpuDcvs;

/* Seat the thread at `floor`, clamp the window to [floor, top]. */
void k60_gpu_dcvs_reset(K60GpuDcvs *dcvs, K60GpuGovernor *gov, unsigned floor,
    unsigned top);
/* One 16 ms window: feeds the governor, arms the wake boost when activity
 * resumes after idle, applies it while it has not expired, and clamps the
 * result to [floor, top]. Stores the level to vote in *want. Returns 0, or -1
 * on bad arguments or a governor failure. No MMIO, no vote. */
int k60_gpu_dcvs_window(K60GpuDcvs *dcvs, K60GpuGovernor *gov,
    const K60GpuTable *table, uint64_t delta_ticks, uint64_t window_ns,
    uint64_t now_ns, unsigned boost_ms, uint64_t wake_min_khz, unsigned *want);
/* Record the vote for `want`: a success moves both levels, a refusal counts.
 * Returns 1 when the thread should stop (K60_GPU_STOP_REFUSALS refusals in a
 * row), 0 to continue. */
int k60_gpu_dcvs_voted(K60GpuDcvs *dcvs, K60GpuGovernor *gov, unsigned want,
    int accepted);
#ifdef __cplusplus
}
#endif
#endif
