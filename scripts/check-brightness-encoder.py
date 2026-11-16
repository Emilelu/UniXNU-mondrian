#!/usr/bin/env python3
"""Host check for the K60 brightness encoder (drivers/PongAdreno/K60BacklightCodec.h).

The K60 panel takes its brightness as the two-byte DSI DCS 0x51 value (online
12 bit DBV); the OS talks in a 0..2047 level plus a 16.16 FadePeriod. Everything
between the two is pure arithmetic, so it is verified here on the host: no
hardware, no IOKit.

What is asserted:
  * 0..4095 DBV conversion: endpoints, monotonicity, no lit level maps to 0, and
    the DBV -> level inverse round trips within one DBV step.
  * brightness-nits requests (iPadOS 27 form): 5 / 140 / 400 nits map onto the
    panel range end to end (dimmest request -> DBV 0x14, brightest -> DBV 0xfff),
    <= 0 maps to off, and the result never exceeds the level domain.
  * FadePeriod: 16.16 seconds -> milliseconds, clamped at 5000 ms.
  * The fade sequence: monotonic, starts at "from", lands exactly on "to", and
    the step count matches the 16 ms cadence.

Run: python3 scripts/check-brightness-encoder.py
"""

import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADER = os.path.join(REPO, "drivers", "PongAdreno", "K60BacklightCodec.h")

HARNESS = r"""
#include <stdio.h>
#include <stdint.h>
#include "K60BacklightCodec.h"
#include "PongDsiPanel.h"

using namespace k60backlight;

static int failures;

static void check(bool ok, const char *what, long got, long want)
{
    if (!ok) {
        printf("FAIL %s: got %ld want %ld\n", what, got, want);
        ++failures;
    }
}

int main(void)
{
    /* --- 0..4095 DBV conversion ------------------------------------------ */
    check(dbvFromLevel(0) == 0, "dbv(0) is off", dbvFromLevel(0), 0);
    check(dbvFromLevel(kMaxLevel) == kMaxDbv, "dbv(max) is 0xfff", dbvFromLevel(kMaxLevel), kMaxDbv);
    check(dbvFromLevel(1) >= kMinDbvOn, "dbv(1) still lit", dbvFromLevel(1), kMinDbvOn);
    check(dbvFromLevel(1) < dbvFromLevel(64), "dbv monotonic low", dbvFromLevel(1), dbvFromLevel(64));
    check(dbvFromLevel(2000) > dbvFromLevel(1024), "dbv monotonic high", dbvFromLevel(2000), dbvFromLevel(1024));

    int prev = -1;
    for (uint32_t level = 0; level <= kMaxLevel; ++level) {
        const uint32_t dbv = dbvFromLevel(level);
        check((int)dbv >= prev, "dbv non-decreasing", (long)dbv, prev);
        check(dbv <= kMaxDbv, "dbv in range", dbv, kMaxDbv);
        if (level) check(dbv >= kMinDbvOn, "lit level has lit dbv", dbv, kMinDbvOn);
        prev = (int)dbv;
    }

    /* The panel has 4095 DBV steps for 2047 OS levels, so not every DBV step is
       addressable; the inverse only has to come back within one DBV step. */
    for (uint32_t dbv = kMinDbvOn; dbv <= kMaxDbv; ++dbv) {
        const uint32_t back = dbvFromLevel(levelFromDbv(dbv));
        const long diff = (long)back - (long)dbv;
        check(diff >= -1 && diff <= 1, "dbv/level round trip", diff, 0);
    }
    check(levelFromDbv(0) == 0, "level(0) is off", levelFromDbv(0), 0);
    check(levelFromDbv(kMaxDbv) == kMaxLevel, "level(0xfff) is max", levelFromDbv(kMaxDbv), kMaxLevel);

    /* Clamping of out-of-range requests. */
    check(clampLevel(-5) == 0, "clamp low", clampLevel(-5), 0);
    check(clampLevel(99999) == kMaxLevel, "clamp high", clampLevel(99999), kMaxLevel);

    /* --- brightness-nits (iPadOS 27 form) -------------------------------- */
    check(levelFromNits(0) == 0, "nits 0 is off", levelFromNits(0), 0);
    check(levelFromNits(-(1 << 16)) == 0, "nits negative is off", levelFromNits(-(1 << 16)), 0);
    check(levelFromNits(kMinNits << 16) == kDarkestLevel, "nits min", levelFromNits(kMinNits << 16), kDarkestLevel);
    check(levelFromNits(kMidNits << 16) == 700, "nits mid", levelFromNits(kMidNits << 16), 700);
    check(levelFromNits(kMaxNits << 16) == kMaxLevel, "nits max", levelFromNits(kMaxNits << 16), kMaxLevel);
    /* The two ends of the slider reach the two ends of the panel: this is what
       brightness-15 got wrong (top stopped at DBV 0xcc, bottom at DBV 0x03). */
    check(dbvFromLevel(levelFromNits(kMinNits << 16)) == kMinDbvOn, "dimmest request reaches the floor",
          dbvFromLevel(levelFromNits(kMinNits << 16)), kMinDbvOn);
    check(dbvFromLevel(levelFromNits(kMaxNits << 16)) == kMaxDbv, "brightest request reaches dbv 0xfff",
          dbvFromLevel(levelFromNits(kMaxNits << 16)), kMaxDbv);
    check(levelFromNits((kMaxNits + 100) << 16) == kMaxLevel, "nits above max clamps", levelFromNits((kMaxNits + 100) << 16), kMaxLevel);
    check(dbvFromLevel(levelFromNits(1 << 8)) >= kMinDbvOn, "tiny nits still lit",
          dbvFromLevel(levelFromNits(1 << 8)), kMinDbvOn);

    /* MilliNits reported next to the level. */
    check(milliNitsFromLevel(0) == 0, "mNits 0", milliNitsFromLevel(0), 0);
    check(milliNitsFromLevel(kMaxLevel) == (long)kMaxNits * 1000, "mNits max", milliNitsFromLevel(kMaxLevel), (long)kMaxNits * 1000);
    check(milliNitsFromLevel(1024) == 200097, "mNits half", milliNitsFromLevel(1024), 200097);

    /* --- FadePeriod: 16.16 seconds -> milliseconds ----------------------- */
    check(fadeMsFromFixed(0) == 0, "fade 0", fadeMsFromFixed(0), 0);
    check(fadeMsFromFixed((uint64_t)1 << 16) == 1000, "fade 1s", fadeMsFromFixed((uint64_t)1 << 16), 1000);
    check(fadeMsFromFixed((uint64_t)1 << 15) == 500, "fade 0.5s", fadeMsFromFixed((uint64_t)1 << 15), 500);
    check(fadeMsFromFixed((uint64_t)10 << 16) == kMaxFadeMs, "fade clamps at 5s", fadeMsFromFixed((uint64_t)10 << 16), kMaxFadeMs);

    /* --- The fade sequence ---------------------------------------------- */
    const uint32_t from = 200, to = 1800, period = 512;
    check(fadeLevel(from, to, 0, period) == from, "fade starts at from", fadeLevel(from, to, 0, period), from);
    check(fadeLevel(from, to, period, period) == to, "fade lands on to", fadeLevel(from, to, period, period), to);
    check(fadeLevel(from, to, period * 2, period) == to, "fade does not overshoot", fadeLevel(from, to, period * 2, period), to);
    check(fadeLevel(from, to, 0, 0) == to, "zero period jumps", fadeLevel(from, to, 0, 0), to);
    check(fadeLevel(to, from, 256, period) == 1000, "fade downwards", fadeLevel(to, from, 256, period), 1000);

    prev = -1;
    for (uint32_t ms = 0; ms <= period; ms += kStepMs) {
        const uint32_t level = fadeLevel(from, to, ms, period);
        check((int)level >= prev, "fade monotonic", (long)level, prev);
        prev = (int)level;
    }
    check(fadeStepCount(512) == 33, "step count", fadeStepCount(512), 33);
    check(fadeStepCount(0) == 1, "step count zero period", fadeStepCount(0), 1);

    /* A fade in DBV never goes dark on the way down to a lit level. */
    for (uint32_t ms = 0; ms <= period; ms += kStepMs) {
        const uint32_t dbv = fadeDbv(to, from, ms, period, false);
        check(dbv >= kMinDbvOn, "fade dbv stays lit", dbv, kMinDbvOn);
        check(dbv <= kMaxDbv, "fade dbv in range", dbv, kMaxDbv);
    }
    /* Fading all the way to off does reach 0 at the end. */
    check(fadeDbv(800, 0, 512, 512, false) == 0, "fade to off ends at 0", fadeDbv(800, 0, 512, 512, false), 0);

    /* Inverted wiring flips the 12 bit value. */
    check(applyInvert(kMaxDbv, true) == 0, "invert max", applyInvert(kMaxDbv, true), 0);
    check(applyInvert(0x00, true) == kMaxDbv, "invert zero", applyInvert(0x00, true), kMaxDbv);
    check(applyInvert(0x40, false) == 0x40, "no invert", applyInvert(0x40, false), 0x40);

    /* The exact bytes handed to DCS 0x51: 12 bit, most significant byte first. */
    uint8_t wire[2];
    pong_panel_dbv_bytes(kMaxDbv, wire);
    check(wire[0] == 0x0f && wire[1] == 0xff, "max dbv wire bytes",
          (long)((wire[0] << 8) | wire[1]), 0x0fff);
    pong_panel_dbv_bytes(kMinDbvOn, wire);
    check(wire[0] == 0x00 && wire[1] == 0x14, "min dbv wire bytes",
          (long)((wire[0] << 8) | wire[1]), 0x0014);

    if (failures) {printf("%d check(s) failed\n", failures); return 1;}
    printf("all brightness encoder checks passed\n");
    return 0;
}
"""


def compiler():
    for candidate in ("g++", "clang++", "c++"):
        path = shutil.which(candidate)
        if path:
            return path
    raise SystemExit("no C++ compiler found (need g++ or clang++)")


def main():
    if not os.path.exists(HEADER):
        raise SystemExit("missing %s" % HEADER)
    work = tempfile.mkdtemp(prefix="k60-brightness-")
    src = os.path.join(work, "harness.cpp")
    exe = os.path.join(work, "harness")
    with open(src, "w") as handle:
        handle.write(HARNESS)
    build = subprocess.run(
        [compiler(), "-std=gnu++17", "-Wall", "-Wextra", "-Werror", "-O1",
         "-I", os.path.dirname(HEADER), src, "-o", exe],
        capture_output=True, text=True)
    if build.returncode:
        print(build.stdout + build.stderr)
        raise SystemExit("harness did not compile")
    run = subprocess.run([exe], capture_output=True, text=True)
    sys.stdout.write(run.stdout)
    sys.stderr.write(run.stderr)
    if run.returncode:
        raise SystemExit("brightness encoder checks failed")
    print("check-brightness-encoder: ok")


if __name__ == "__main__":
    main()