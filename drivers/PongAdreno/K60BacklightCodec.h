// SPDX-License-Identifier: APSL-2.0
//
// K60BacklightCodec.h - the encoding half of the K60 brightness service.
//
// K60 has no backlight IC: the panel takes its brightness as the DSI DCS 0x51
// long write (online DBV), which drivers/PongAdreno/PongDsiPanel.cpp:247 already
// sends. What was missing is the *encoding* layer between the domain the OS talks
// in and the 8 bit DBV the panel takes, so it lives here, free of IOKit, and is
// unit tested on the host by scripts/check-brightness-encoder.py.
//
// Two domains:
//   OS   : 0..kMaxLevel (2047), the scale CoreBrightness/backboardd uses, see
//          UniXNU-sheng/package/AppleARMBacklight.cpp kMaxLevel.
//   panel: 0..0xff, the byte carried in DCS 0x51. 0 means "off", 1 is the
//          dimmest lit step, 0xff is the brightest.
// The live FDT also advertises bl-max = 0xfff / bl-min = 0x1 (docs/research/
// display/RESEARCH.md:76), but that is the vendor 12 bit domain; the 0x51 write
// that actually lights this panel is 8 bit (0x51 0xff at bring-up, PongDsiPanel.cpp:236).

#ifndef K60_BACKLIGHT_CODEC_H
#define K60_BACKLIGHT_CODEC_H

#include <stdint.h>

namespace k60backlight {

enum : uint32_t {
    kMaxLevel = 2047,   // OS brightness domain, matches AppleARMBacklight kMaxLevel
    kMinNits = 2,       // calibration points published to CoreBrightness
    kMidNits = 140,
    kMaxNits = 500,
    kMaxFadeMs = 5000,  // a FadePeriod longer than this is clamped
    kStepMs = 16,       // fade step cadence
    kMaxDbv = 0xff,     // panel DBV domain carried by DCS 0x51
    kMinDbvOn = 1,      // dimmest value that still lights the panel
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
// Anything at or below zero is "off"; otherwise scale to the panel's nits and
// never hand back a lit level of 0.
static inline uint32_t levelFromNits(int32_t fixedNits)
{
    if (fixedNits <= 0) return 0;
    const uint64_t scale = (uint64_t)kMaxNits << 16;
    const uint64_t scaled = ((uint64_t)(uint32_t)fixedNits * (uint64_t)kMaxLevel + scale / 2) / scale;
    if (scaled < (uint64_t)kMinDbvOn) return kMinDbvOn;
    if (scaled > (uint64_t)kMaxLevel) return kMaxLevel;
    return (uint32_t)scaled;
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
    const uint32_t span = kMaxDbv - kMinDbvOn;                 // 254
    const uint32_t steps = (clamped * span + kMaxLevel / 2) / kMaxLevel;
    return kMinDbvOn + steps;
}

// Panel DBV -> OS level, the inverse used to report a read-back value.
static inline uint32_t levelFromDbv(uint32_t dbv)
{
    if (dbv == 0) return 0;
    const uint32_t d = dbv > kMaxDbv ? kMaxDbv : dbv;
    const uint32_t span = kMaxDbv - kMinDbvOn;                 // 254
    const uint32_t steps = ((d - kMinDbvOn) * kMaxLevel + span / 2) / span;
    if (steps < kMinDbvOn) return kMinDbvOn;
    return steps > kMaxLevel ? kMaxLevel : steps;
}

// Some panels wire DBV inverted (live FDT bl-inverted-dbv, RESEARCH.md:77).
// K60 sends 0xff at bring-up and the panel comes up bright, so the default is
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
