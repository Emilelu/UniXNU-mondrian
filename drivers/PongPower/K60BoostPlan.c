/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include "K60BoostPlan.h"

void k60_boost_reset(K60BoostState *state)
{
    if (!state) return;
    state->last_touch_ms = 0; state->last_submit_ms = 0;
    state->windows = 0; state->window_count = 0;
    state->has_touch = 0; state->has_submit = 0;
}

void k60_boost_touch(K60BoostState *state, uint64_t now_ms)
{
    if (!state) return;
    state->last_touch_ms = now_ms; state->has_touch = 1;
}

void k60_boost_window(K60BoostState *state, uint64_t now_ms, int submitted)
{
    if (!state) return;
    state->windows = (state->windows << 1) | (submitted ? 1u : 0u);
    state->windows &= (1u << K60_BOOST_WINDOWS) - 1u;
    if (state->window_count < K60_BOOST_WINDOWS) state->window_count++;
    if (submitted) { state->last_submit_ms = now_ms; state->has_submit = 1; }
}

int k60_boost_touch_active(const K60BoostState *state, uint64_t now_ms)
{
    if (!state || !state->has_touch) return 0;
    return now_ms - state->last_touch_ms < K60_BOOST_TOUCH_MS;
}

unsigned k60_boost_frame_count(const K60BoostState *state)
{
    uint32_t bits;
    unsigned n = 0;
    if (!state) return 0;
    bits = state->windows;
    while (bits) { n += bits & 1u; bits >>= 1; }
    return n;
}

int k60_boost_frame_active(const K60BoostState *state, uint64_t now_ms)
{
    if (!state || state->window_count < K60_BOOST_WINDOWS || !state->has_submit) return 0;
    if (k60_boost_frame_count(state) < K60_BOOST_FRAME_MIN) return 0;
    return now_ms - state->last_submit_ms < K60_BOOST_FRAME_MS;
}

unsigned k60_boost_cpu_floor_khz(uint32_t top_khz)
{
    return (unsigned)((uint64_t)top_khz * K60_BOOST_CPU_PCT / 100u);
}

unsigned k60_boost_gpu_wake_khz(uint32_t current_khz, uint32_t top_khz)
{
    uint64_t twice = (uint64_t)current_khz * 2u;
    uint64_t want = twice > K60_BOOST_GPU_MIN_KHZ ? twice : K60_BOOST_GPU_MIN_KHZ;
    return (unsigned)(want > top_khz ? top_khz : want);
}

int k60_boost_fence_ok(uint64_t start_us, uint64_t now_us)
{
    if (now_us < start_us) return 0;
    return now_us - start_us <= K60_BOOST_FENCE_US;
}
