/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include <stdio.h>
#include <string.h>
#include "../../drivers/PongPower/K60BoostPlan.h"

static unsigned failures, checks;
static void check(const char *name, unsigned got, unsigned want)
{
    checks++;
    if (got != want) { failures++; printf("FAIL %s: got %u want %u\n", name, got, want); }
}
int main(void)
{
    K60BoostState s;

    memset(&s, 0, sizeof(s));
    k60_boost_reset(&s);
    check("reset windows", s.windows, 0);
    check("reset count", s.window_count, 0);
    check("touch inactive fresh", k60_boost_touch_active(&s, 0), 0);

    k60_boost_touch(&s, 5000);
    check("touch at 5999", k60_boost_touch_active(&s, 5999), 1);
    check("touch at 6000", k60_boost_touch_active(&s, 6000), 0);
    check("touch at 7000", k60_boost_touch_active(&s, 7000), 0);
    k60_boost_touch(&s, 9000);
    check("touch renewed", k60_boost_touch_active(&s, 9500), 1);

    k60_boost_reset(&s);
    k60_boost_window(&s, 0, 1);
    check("one window count", s.window_count, 1);
    check("one window frame active", k60_boost_frame_active(&s, 0), 0);
    k60_boost_window(&s, 16, 0);
    k60_boost_window(&s, 32, 1);
    check("three windows", s.window_count, 3);
    k60_boost_window(&s, 48, 0);
    check("four windows", s.window_count, 4);
    check("frame count two", k60_boost_frame_count(&s), 2);
    check("frame active now", k60_boost_frame_active(&s, 48), 1);
    check("frame active 331", k60_boost_frame_active(&s, 331), 1);
    check("frame inactive 332", k60_boost_frame_active(&s, 332), 0);
    k60_boost_window(&s, 64, 0);
    check("shift keeps four", s.window_count, 4);
    check("shift drops oldest", k60_boost_frame_count(&s), 1);
    check("frame inactive one", k60_boost_frame_active(&s, 64), 0);
    k60_boost_window(&s, 80, 1);
    k60_boost_window(&s, 96, 1);
    check("frame count after shift", k60_boost_frame_count(&s), 2);
    check("frame active after shift", k60_boost_frame_active(&s, 96), 1);
    check("frame count mask", s.windows <= 15, 1);

    check("cpu floor 900", k60_boost_cpu_floor_khz(900000), 540000);
    check("cpu floor 220", k60_boost_cpu_floor_khz(220000), 132000);
    check("cpu floor 285", k60_boost_cpu_floor_khz(285000), 171000);
    check("cpu floor zero", k60_boost_cpu_floor_khz(0), 0);

    check("wake low", k60_boost_gpu_wake_khz(220000, 900000), 578000);
    check("wake double", k60_boost_gpu_wake_khz(400000, 900000), 800000);
    check("wake capped", k60_boost_gpu_wake_khz(500000, 900000), 900000);
    check("wake 300", k60_boost_gpu_wake_khz(300000, 900000), 600000);
    check("wake top floor", k60_boost_gpu_wake_khz(220000, 500000), 500000);

    check("fence exact", k60_boost_fence_ok(1000, 2000), 1);
    check("fence over", k60_boost_fence_ok(1000, 2001), 0);
    check("fence zero", k60_boost_fence_ok(1000, 1000), 1);
    check("fence backwards", k60_boost_fence_ok(1000, 999), 0);

    check("null reset", (k60_boost_reset(0), 1), 1);
    check("null touch", (k60_boost_touch(0, 1), 1), 1);
    check("null window", (k60_boost_window(0, 1, 1), 1), 1);
    check("null touch active", k60_boost_touch_active(0, 1), 0);
    check("null frame count", k60_boost_frame_count(0), 0);
    check("null frame active", k60_boost_frame_active(0, 1), 0);

    if (failures) printf("TESTS FAILED %u failures / %u checks\n", failures, checks);
    else printf("TESTS OK %u checks (0 failures)\n", checks);
    return failures ? 1 : 0;
}
