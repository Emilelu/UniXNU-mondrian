/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#include "K60SleepPlan.h"

const uint8_t k60_sleep_reserved[K60_SLEEP_RESERVED_COUNT] = {28, 29, 30, 31, 36, 37, 38, 39};

int k60_sleep_pin_usable(unsigned gpio)
{
    if (gpio >= K60_SLEEP_GPIO_COUNT) return 0;
    for (unsigned i = 0; i < K60_SLEEP_RESERVED_COUNT; ++i)
        if (gpio == k60_sleep_reserved[i]) return 0;
    return 1;
}

unsigned k60_sleep_mask_tlmm(const uint32_t *cfg, unsigned count,
    uint32_t *out, unsigned capacity)
{
    if (!cfg || !out || !count || capacity < count) return 0;
    for (unsigned i = 0; i < count; ++i) {
        uint32_t value = cfg[i];
        if (k60_sleep_pin_usable(i) && K60_SLEEP_INTR_TARGET(value) == K60_SLEEP_TARGET_AP)
            value &= ~K60_SLEEP_INTR_ENABLE;
        out[i] = value;
    }
    return count;
}

int k60_sleep_pin_pending(uint32_t intr_status)
{
    return (intr_status & 1u) != 0;
}

int k60_sleep_power_wakes(uint8_t rt_status, uint32_t latched)
{
    return (((uint32_t)rt_status | latched) & K60_SLEEP_PON_POWER_BIT) != 0;
}

int k60_sleep_swallow(int *pending, int pressed)
{
    if (!pending) return pressed;
    if (!*pending) return pressed;
    if (!pressed) *pending = 0;
    return 0;
}

int k60_sleep_deadline_reached(uint64_t now_ms, uint64_t deadline_ms)
{
    return deadline_ms && now_ms >= deadline_ms;
}

const char *k60_sleep_woke_by(unsigned armcpu_reason, enum k60_wake_source source)
{
    if (source == K60WakePower) return "power";
    if (source == K60WakeTimer) return "timer";
    if (armcpu_reason == K60_SLEEP_ARMCPU_TIMER) return "timer";
    return armcpu_reason == K60_SLEEP_ARMCPU_STORM ? "storm" : "nothing";
}

int k60_sleep_watchdog_due(uint64_t now_ms, uint64_t last_feed_ms)
{
    if (now_ms < last_feed_ms) return 0;
    return now_ms - last_feed_ms >= K60_SLEEP_WATCHDOG_FEED_MS;
}

uint64_t k60_sleep_wake_after_ms(unsigned seconds)
{
    return (uint64_t)seconds * 1000u;
}

int k60_sleep_backlight_ready(unsigned frames, int frame_counting,
    uint64_t elapsed_ms)
{
    if (frame_counting) {
        if (frames >= K60_SLEEP_BACKLIGHT_FRAMES) return 1;
        return elapsed_ms >= K60_SLEEP_BACKLIGHT_MAX_MS;
    }
    return elapsed_ms >= K60_SLEEP_BACKLIGHT_FALLBACK_MS;
}

int k60_sleep_touch_reestablish(uint64_t now_ms, uint64_t last_report_ms)
{
    if (!last_report_ms || now_ms <= last_report_ms) return 0;
    return now_ms - last_report_ms > K60_SLEEP_TOUCH_GAP_MS;
}
