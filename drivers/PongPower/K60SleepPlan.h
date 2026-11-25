/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/*
 * Pure platform-sleep planning for the K60 TLMM block. No MMIO and no IOKit
 * here: the board hook that will own the registers is not written yet, so the
 * host test pins the mask and wake arithmetic first.
 *
 * Facts from the live K60 device tree
 * (E:/iOS Port/Work/reports/live-6033dbec-fdt.dtb, decompiled 2026-11-18):
 *   /soc/pinctrl@f000000  compatible "qcom,cape-pinctrl", reg 0x0f000000
 *                         (0x1000000), interrupts <0 0xd0 4> = SPI 208,
 *                         qcom,gpios-reserved = <28 29 30 31 36 37 38 39>;
 *   /soc/qcom,spmi@c42d000  PMK8350 PON pwrkey interrupts <0 0x13 0x07 0x03>.
 * K60 has no lid/hall node (it is a phone): unlike the SM8550 tablet
 * reference (UniXNU-sheng package/ShengSleep.h), the only wake source is the
 * PMIC power key, plus the platform-sleep-wake-after deadline.
 */
#ifndef K60_SLEEP_PLAN_H
#define K60_SLEEP_PLAN_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

/* The SM8475 TLMM exposes 210 pins, the same count as the SM8550 block. The
 * live FDT does not state it; read the reset value of the pin count register
 * before relying on the last pins. */
#define K60_SLEEP_GPIO_COUNT 210u

/* qcom,gpios-reserved: secure pins where any access aborts. */
#define K60_SLEEP_RESERVED_COUNT 8u
extern const uint8_t k60_sleep_reserved[K60_SLEEP_RESERVED_COUNT];

/* TLMM interrupt registers: IO bit 0 is the pin level. INTR_CFG bit 0 enable,
 * bit 1 polarity, bits 3:2 detection (0 level, 1 rising, 2 falling, 3 both),
 * bits 7:5 target processor, 3 = the application processor. */
#define K60_SLEEP_REG_IO 0x04u
#define K60_SLEEP_REG_INTR_CFG 0x08u
#define K60_SLEEP_REG_INTR_STATUS 0x0cu
#define K60_SLEEP_INTR_ENABLE 1u
#define K60_SLEEP_INTR_POLARITY (1u << 1)
#define K60_SLEEP_INTR_DETECTION (3u << 2)
#define K60_SLEEP_INTR_TARGET(cfg) (((cfg) >> 5) & 7u)
#define K60_SLEEP_TARGET_AP 3u

/* PMK8350 PON real-time and latched status, bit 7: key pressed. */
#define K60_SLEEP_PON_POWER_BIT 0x80u

/* ArmCpu's last_reason values, as in the reference ArmCpuSleep.h. */
#define K60_SLEEP_ARMCPU_SOURCE 1u
#define K60_SLEEP_ARMCPU_TIMER 2u
#define K60_SLEEP_ARMCPU_STORM 3u

enum k60_wake_source { K60WakeNone, K60WakePower, K60WakeTimer };

/* Pins the board must not touch (reserved) and pins whose INTR_CFG targets
 * another processor belong to that processor, not to this mask. */
int k60_sleep_pin_usable(unsigned gpio);

/* Copy cfg[0..count) into out, clearing the enable bit on every usable pin
 * that interrupts the application processor. Other pins are copied unchanged,
 * and the reserved pins are never modified. Returns count on success, 0 for a
 * null/empty input or a capacity smaller than count (out stays untouched). */
unsigned k60_sleep_mask_tlmm(const uint32_t *cfg, unsigned count,
    uint32_t *out, unsigned capacity);

/* A raw INTR_STATUS bit 0 means this pin raised the summary interrupt. */
int k60_sleep_pin_pending(uint32_t intr_status);

/* The power key wakes from either its real-time or its latched status: a short
 * press can be over before the wait checks it. */
int k60_sleep_power_wakes(uint8_t rt_status, uint32_t latched);

/* The press that woke the system and its release are not delivered to macOS:
 * drop the first press, and end the suppression when the key is seen up. */
int k60_sleep_swallow(int *pending, int pressed);

/* platform-sleep-wake-after: now_ms >= deadline_ms ends the wait. A zero
 * deadline disables the timer. */
int k60_sleep_deadline_reached(uint64_t now_ms, uint64_t deadline_ms);

/* Wake reason for the log line: power, the wake-after timer, a storm (a line
 * kept firing with nothing left to wake the system), or nothing (the wait was
 * not entered). armcpu_reason is ArmCpu's last_reason. */
const char *k60_sleep_woke_by(unsigned armcpu_reason, enum k60_wake_source source);

/* While asleep the board hook feeds the firmware watchdog it took over every
 * 10 s; a zero last_feed means it has not fed yet. */
#define K60_SLEEP_WATCHDOG_FEED_MS 10000u
int k60_sleep_watchdog_due(uint64_t now_ms, uint64_t last_feed_ms);

/* platform-sleep-wake-after=<seconds>; 0 keeps the timer disabled. */
uint64_t k60_sleep_wake_after_ms(unsigned seconds);

/* The panel returns after two frames, capped at 1500 ms; without a frame
 * counter the hook waits 600 ms and does not look at frames. */
#define K60_SLEEP_BACKLIGHT_FRAMES 2u
#define K60_SLEEP_BACKLIGHT_MAX_MS 1500u
#define K60_SLEEP_BACKLIGHT_FALLBACK_MS 600u
int k60_sleep_backlight_ready(unsigned frames, int frame_counting,
    uint64_t elapsed_ms);

/* A touch report gap longer than 60 ms re-establishes the contact position;
 * exactly 60 ms is still the same stream. A zero last_report means no contact. */
#define K60_SLEEP_TOUCH_GAP_MS 60u
int k60_sleep_touch_reestablish(uint64_t now_ms, uint64_t last_report_ms);

#ifdef __cplusplus
}
#endif
#endif /* K60_SLEEP_PLAN_H */
