/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#ifndef K60_BOOST_PLAN_H
#define K60_BOOST_PLAN_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Official section 5 boost rules (snapshot power-page-20261117.txt:115-117):
 * touch holds the P domain and GPU top for 1 s after the last report; two of
 * the last four 16 ms windows with a GPU submission hold every CPU domain at
 * 60 % of its top for 300 ms; a GPU that resumes after an idle drop runs at
 * twice the current frequency, at least 578 MHz, for 50 ms; a fence waiter
 * sleeps until the interrupt for at most 1 ms. Pure rules, no MMIO. */
#define K60_BOOST_TOUCH_MS 1000u
#define K60_BOOST_FRAME_MS 300u
#define K60_BOOST_WINDOWS 4u
#define K60_BOOST_FRAME_MIN 2u
#define K60_BOOST_CPU_PCT 60u
#define K60_BOOST_GPU_WAKE_MS 50u
#define K60_BOOST_GPU_MIN_KHZ 578000u
#define K60_BOOST_FENCE_US 1000u

typedef struct {
    uint64_t last_touch_ms, last_submit_ms;
    uint32_t windows;      /* bit 0 is the newest of the last four windows */
    unsigned window_count; /* 0..4, so a fresh boot is not judged on 4 slots */
    int has_touch, has_submit;
} K60BoostState;

void k60_boost_reset(K60BoostState *state);
void k60_boost_touch(K60BoostState *state, uint64_t now_ms);
/* Shift one 16 ms window in. The caller samples whether a GPU submission
 * happened in that window; this module does not read the Adreno rings. */
void k60_boost_window(K60BoostState *state, uint64_t now_ms, int submitted);
int k60_boost_touch_active(const K60BoostState *state, uint64_t now_ms);
unsigned k60_boost_frame_count(const K60BoostState *state);
int k60_boost_frame_active(const K60BoostState *state, uint64_t now_ms);
unsigned k60_boost_cpu_floor_khz(uint32_t top_khz);
unsigned k60_boost_gpu_wake_khz(uint32_t current_khz, uint32_t top_khz);
int k60_boost_fence_ok(uint64_t start_us, uint64_t now_us);
#ifdef __cplusplus
}
#endif
#endif
