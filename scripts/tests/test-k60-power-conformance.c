/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/*
 * One place that pins the numbers the official power page section 5 states:
 * the 1.25x CPU margin, four quiet windows, the 50 % GPU busy target, the
 * 578 MHz GPU floor, the 1 s touch hold, the 300 ms / 60 % frame floor, the
 * 50 ms GPU wake, the 1 ms fence budget, the 10 s watchdog feed, the two-frame
 * / 1500 ms / 600 ms backlight wait, the 60 ms touch gap and the release order
 * of a peripheral vote. The static assertions fail the compile when a plan
 * header drifts away from the page; the runtime checks pin the boundaries the
 * page states. Pure logic, no MMIO.
 */
#include <stdio.h>
#include <string.h>
#include "../../drivers/PongPower/K60CpuFreqPlan.h"
#include "../../drivers/PongPower/K60GpuFreqPlan.h"
#include "../../drivers/PongPower/K60BoostPlan.h"
#include "../../drivers/PongPower/K60SleepPlan.h"
#include "../../drivers/PongPower/K60PowerVotePlan.h"

_Static_assert(K60_CPU_FREQ_MARGIN == 125u, "official CPU margin is 1.25x");
_Static_assert(K60_CPU_FREQ_DOWN_WINDOWS == 4u, "four quiet windows before a drop");
_Static_assert(K60_CPU_FREQ_FRAME_PCT == 60u, "frame floor is 60 percent");
_Static_assert(K60_GPU_TARGET_BUSY == 500u, "GPU target is 50 percent busy");
_Static_assert(K60_GPU_WAKE_MIN_KHZ == 578000u, "GPU wake floor is 578 MHz");
_Static_assert(K60_BOOST_TOUCH_MS == 1000u, "touch holds for 1 s");
_Static_assert(K60_BOOST_FRAME_MS == 300u, "frame floor holds for 300 ms");
_Static_assert(K60_BOOST_WINDOWS == 4u, "frame rule looks at four windows");
_Static_assert(K60_BOOST_FRAME_MIN == 2u, "two of four windows arm the floor");
_Static_assert(K60_BOOST_CPU_PCT == K60_CPU_FREQ_FRAME_PCT, "one 60 percent floor");
_Static_assert(K60_BOOST_GPU_WAKE_MS == 50u, "GPU wake lands within 50 ms");
_Static_assert(K60_BOOST_GPU_MIN_KHZ == K60_GPU_WAKE_MIN_KHZ, "one 578 MHz floor");
_Static_assert(K60_BOOST_FENCE_US == 1000u, "fence waiter sleeps at most 1 ms");
_Static_assert(K60_SLEEP_WATCHDOG_FEED_MS == 10000u, "watchdog is fed every 10 s");
_Static_assert(K60_SLEEP_BACKLIGHT_FRAMES == 2u, "backlight waits two frames");
_Static_assert(K60_SLEEP_BACKLIGHT_MAX_MS == 1500u, "backlight waits at most 1500 ms");
_Static_assert(K60_SLEEP_BACKLIGHT_FALLBACK_MS == 600u, "600 ms without a frame count");
_Static_assert(K60_SLEEP_TOUCH_GAP_MS == 60u, "a 60 ms touch gap re-establishes contact");

static unsigned failures, checks;
static void check(const char *name, unsigned got, unsigned want)
{
    checks++;
    if (got != want) { failures++; printf("FAIL %s: got %u want %u\n", name, got, want); }
}

int main(void)
{
    K60BoostState boost;
    enum k60_vote_step steps[K60VoteStepCount];

    /* 1 s touch hold, boundaries inclusive at 999 ms and closed at 1000 ms. */
    memset(&boost, 0, sizeof(boost));
    k60_boost_reset(&boost);
    k60_boost_touch(&boost, 0);
    check("touch holds at 999 ms", (unsigned)k60_boost_touch_active(&boost, 999), 1);
    check("touch releases at 1000 ms", (unsigned)k60_boost_touch_active(&boost, 1000), 0);

    /* Two of the last four 16 ms windows hold the 300 ms frame floor. */
    k60_boost_reset(&boost);
    k60_boost_window(&boost, 0, 1);
    k60_boost_window(&boost, 16, 0);
    k60_boost_window(&boost, 32, 1);
    k60_boost_window(&boost, 48, 0);
    check("frame windows counted", k60_boost_frame_count(&boost), 2);
    check("frame floor active", (unsigned)k60_boost_frame_active(&boost, 48), 1);
    check("frame floor at 331 ms", (unsigned)k60_boost_frame_active(&boost, 331), 1);
    check("frame floor ends at 332 ms", (unsigned)k60_boost_frame_active(&boost, 332), 0);

    /* 60 % of the top, and the GPU floor is max(2x, 578 MHz). */
    check("cpu floor of 1 GHz", k60_boost_cpu_floor_khz(1000000), 600000);
    check("cpu floor of d0 top", k60_boost_cpu_floor_khz(1804800), 1082880);
    check("gpu floor 578", k60_boost_gpu_wake_khz(220000, 1804800), 578000);
    check("gpu wake double", k60_boost_gpu_wake_khz(400000, 1804800), 800000);
    check("gpu wake capped", k60_boost_gpu_wake_khz(900000, 1804800), 1800000);

    /* A fence waiter sleeps at most 1 ms. */
    check("fence sleeps 1000 us", (unsigned)k60_boost_fence_ok(0, 1000), 1);
    check("fence rejects 1001 us", (unsigned)k60_boost_fence_ok(0, 1001), 0);

    /* The owned watchdog is fed every 10 s. */
    check("watchdog waits 9999 ms", (unsigned)k60_sleep_watchdog_due(9999, 0), 0);
    check("watchdog feeds at 10000 ms", (unsigned)k60_sleep_watchdog_due(10000, 0), 1);

    /* Backlight: two frames, else 1500 ms, and 600 ms without a frame count. */
    check("backlight two frames", (unsigned)k60_sleep_backlight_ready(2, 1, 0), 1);
    check("backlight one frame 1499 ms", (unsigned)k60_sleep_backlight_ready(1, 1, 1499), 0);
    check("backlight one frame 1500 ms", (unsigned)k60_sleep_backlight_ready(1, 1, 1500), 1);
    check("backlight fallback 599 ms", (unsigned)k60_sleep_backlight_ready(0, 0, 599), 0);
    check("backlight fallback 600 ms", (unsigned)k60_sleep_backlight_ready(0, 0, 600), 1);

    /* A report gap over 60 ms re-establishes contact; 60 ms does not. */
    check("touch gap 60 ms", (unsigned)k60_sleep_touch_reestablish(1060, 1000), 0);
    check("touch gap 61 ms", (unsigned)k60_sleep_touch_reestablish(1061, 1000), 1);
    check("touch gap without contact", (unsigned)k60_sleep_touch_reestablish(5000, 0), 0);

    /* A vote is released only after the DMA stops and the interrupt is masked. */
    check("release step count", k60_vote_release_steps(steps, 3), 3);
    check("release step stop-dma", (unsigned)(strcmp(k60_vote_step_name(steps[0]), "stop-dma") == 0), 1);
    check("release step mask-irq", (unsigned)(strcmp(k60_vote_step_name(steps[1]), "mask-irq") == 0), 1);
    check("release step drop-vote", (unsigned)(strcmp(k60_vote_step_name(steps[2]), "drop-vote") == 0), 1);

    if (failures) printf("TESTS FAILED %u failures / %u checks\n", failures, checks);
    else printf("TESTS OK %u checks (0 failures)\n", checks);
    return failures ? 1 : 0;
}
