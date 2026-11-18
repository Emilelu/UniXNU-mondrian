// SPDX-License-Identifier: APSL-2.0
//
// K60BacklightCodec.h - the encoding half of the K60 brightness service.
//
// K60 has no backlight IC: the panel takes its brightness as the DSI DCS 0x51
// write (online DBV), which drivers/PongAdreno/PongDsiPanel.cpp:247 already
// sends. What was missing is the *encoding* layer between the domain the OS talks
// in and the 12 bit DBV the panel takes, so it lives here, free of IOKit, and is
// unit tested on the host by scripts/check-brightness-encoder.py.
//
// Two domains:
//   OS   : 0..kMaxLevel (2047), the scale CoreBrightness/backboardd uses, see
//          UniXNU-sheng/package/AppleARMBacklight.cpp kMaxLevel.
//   panel: 0..0xfff, the two-byte value carried in DCS 0x51. 0 means "off";
//          0x4 is the dimmest lit level, 0xfff is the brightest. Android's own
//          DisplayPowerController has mScreenBrightnessRangeMinimum = 9.15639E-4
//          and panel0-backlight/max_brightness = 4095, so its minimum is
//          0.000915639 * 4095 = 3.75 -> DBV 0x4 (live Android on this device,
//          2026-11-17). The live m11a node's mi,doze-lbm-dbv-level = 0x14 is a
//          doze/AOD level, not the normal slider floor. brightness-17 drove DBV 1
//          at night and the panel went black (user report), so 0x4 is the first
//          value above that experiment and is the value Android itself uses.
// The live FDT advertises bl-max = 0xfff, the vendor 12 bit domain, and Android
// writes it as two bytes: dsi_panel_update_backlight() byte-swaps under
// bl-inverted-dbv and mipi_dsi_dcs_set_display_brightness() always sends
// u8 payload[2] = {v & 0xff, v >> 8} (LineageOS sm8250 dsi_panel.c /
// drm_mipi_dsi.c). brightness-16 sent one byte, which this panel reads left
// aligned (0x01 -> 0x0100, 6% of 4095), so the bottom of the slider never got
// dark. PongDsiPanel.cpp now writes the two bytes.

#ifndef K60_BACKLIGHT_CODEC_H
#define K60_BACKLIGHT_CODEC_H

#include <stdint.h>

namespace k60backlight {

enum : uint32_t {
    kMaxLevel = 2047,   // OS brightness domain, matches AppleARMBacklight kMaxLevel
    /* CoreBrightness' own default calibration points. This port never publishes
     * backlight-calibration-parameters (a partial dictionary kills backboardd),
     * so 20G81 falls back to 5 / 140 / 400 nits (CoreBrightness 0x1af031684)
     * and brightness-nits arrives inside that range. Keeping different numbers
     * here would misplace both ends of the slider. */
    kMinNits = 5,
    kMidNits = 140,
    kMaxNits = 400,
    /* The level the dimmest request maps to: dbvFromLevel() turns 1..4 into
     * kMinDbvOn, the dimmest DBV that still lights the panel. */
    kDarkestLevel = 1,
    kMaxFadeMs = 5000,  // a FadePeriod longer than this is clamped
    kStepMs = 16,       // fade step cadence
    kMaxDbv = 0xfff,    // panel 12 bit DBV domain, two bytes in DCS 0x51
    /* Android's own minimum: mScreenBrightnessRangeMinimum = 9.15639E-4,
     * panel0-backlight/max_brightness = 4095 -> 3.75 -> DBV 0x4. The m11a
     * mi,doze-lbm-dbv-level = 0x14 is a doze/AOD level, not this floor.
     * brightness-17 at DBV 1 was black; 0x4 is four steps above it. */
    kMinDbvOn = 0x4,
};

// Clamp a raw request into the OS domain.
static inline uint32_t clampLevel(int64_t level)
{
    if (level <= 0) return 0;
    if (level >= (int64_t)kMaxLevel) return kMaxLevel;
    return (uint32_t)level;
}

// BrightnessMilliNits reported next to the level, same formula as the reference
// implementation (value * kMaxNits * 1000 / kMaxLevel).
static inline uint32_t milliNitsFromLevel(uint32_t level)
{
    const uint64_t nits = (uint64_t)clampLevel((int64_t)level) * (uint64_t)kMaxNits * 1000ull;
    return (uint32_t)(nits / (uint64_t)kMaxLevel);
}

// brightness-nits request (signed 16.16 fixed point nits) -> OS level.
// Anything at or below zero is "off"; otherwise the request range is stretched
// over the whole panel range: the dimmest request lands on kDarkestLevel
// (DBV 0x4) and the brightest on kMaxLevel (DBV 0xfff). A plain linear nits->level
// scale is what brightness-15 shipped and the slider's two ends missed the
// panel's: 400 nits stopped at DBV 0xcc of the then-8-bit domain (204 of 255,
// the top visibly below the panel maximum) while the dimmest 5 nits request
// still came out at DBV 0x03.
// Measured on brightness-15, 2026-11-17.
static inline uint32_t levelFromNits(int32_t fixedNits)
{
    if (fixedNits <= 0) return 0;
    const uint64_t nits = (uint32_t)fixedNits;
    const uint64_t low = (uint64_t)kMinNits << 16;
    const uint64_t high = (uint64_t)kMaxNits << 16;
    if (nits <= low) return kDarkestLevel;
    if (nits >= high) return kMaxLevel;
    const uint64_t span = high - low;
    const uint64_t steps = (nits - low) * (uint64_t)(kMaxLevel - kDarkestLevel);
    return kDarkestLevel + (uint32_t)((steps + span / 2) / span);
}

// FadePeriod arrives as 16.16 fixed point seconds; the service works in ms.
static inline uint32_t fadeMsFromFixed(uint64_t fixedSeconds)
{
    const uint64_t ms = (fixedSeconds * 1000ull) >> 16;
    return (uint32_t)(ms > (uint64_t)kMaxFadeMs ? (uint64_t)kMaxFadeMs : ms);
}

// Linear interpolation used by the fade timer: the level to show elapsedMs into
// a fade from -> to lasting periodMs. Never overshoots and lands exactly on to.
static inline uint32_t fadeLevel(uint32_t from, uint32_t to, uint32_t elapsedMs, uint32_t periodMs)
{
    const uint32_t a = clampLevel((int64_t)from);
    const uint32_t b = clampLevel((int64_t)to);
    if (periodMs == 0 || elapsedMs >= periodMs) return b;
    const int64_t delta = (int64_t)b - (int64_t)a;
    return (uint32_t)((int64_t)a + delta * (int64_t)elapsedMs / (int64_t)periodMs);
}

// OS level -> panel DBV. Level 0 is a real 0 (panel off), every lit level maps
// to at least kMinDbvOn so a dim screen never goes black.
static inline uint32_t dbvFromLevel(uint32_t level)
{
    const uint32_t clamped = clampLevel((int64_t)level);
    if (clamped == 0) return 0;
    /* Endpoint exact: kDarkestLevel -> kMinDbvOn, kMaxLevel -> kMaxDbv. The
     * panel has 4095 DBV steps for 2047 OS levels, so consecutive levels move
     * by one or two DBV steps; the floor must still be reachable. */
    const uint32_t spanDbv = kMaxDbv - kMinDbvOn;              // 4091
    const uint32_t spanLevel = kMaxLevel - kDarkestLevel;      // 2046
    const uint32_t steps =
        ((clamped - kDarkestLevel) * spanDbv + spanLevel / 2) / spanLevel;
    return kMinDbvOn + steps;
}

// Panel DBV -> OS level, the inverse used to report a read-back value.
static inline uint32_t levelFromDbv(uint32_t dbv)
{
    if (dbv == 0) return 0;
    const uint32_t d = dbv > kMaxDbv ? kMaxDbv : dbv;
    const uint32_t spanDbv = kMaxDbv - kMinDbvOn;              // 4091
    const uint32_t spanLevel = kMaxLevel - kDarkestLevel;      // 2046
    const uint32_t steps = ((d - kMinDbvOn) * spanLevel + spanDbv / 2) / spanDbv;
    return kDarkestLevel + steps;
}

// Some panels wire DBV inverted (live FDT bl-inverted-dbv, RESEARCH.md:77).
// K60 sends 0xfff at bring-up and the panel comes up bright, so the default is
// not inverted; the boot-arg k60_backlight_invert flips this if a board turns
// out the other way round.
static inline uint32_t applyInvert(uint32_t dbv, bool invert)
{
    return invert ? (kMaxDbv - dbv) : dbv;
}

// One step of the fade, in DBV, for the transport to hand to the panel.
static inline uint32_t fadeDbv(uint32_t fromLevel, uint32_t toLevel, uint32_t elapsedMs,
                               uint32_t periodMs, bool invert)
{
    return applyInvert(dbvFromLevel(fadeLevel(fromLevel, toLevel, elapsedMs, periodMs)), invert);
}

// Number of fade steps (including the one at elapsed 0) before the fade lands.
static inline uint32_t fadeStepCount(uint32_t periodMs)
{
    return periodMs / kStepMs + 1;
}

} // namespace k60backlight

#endif // K60_BACKLIGHT_CODEC_H
