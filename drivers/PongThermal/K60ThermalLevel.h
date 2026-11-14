/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* The board's temperatures as macOS's thermal pressure level (OSThermalPressureLevel).
 *
 * This is the half of the thermal line that does not touch hardware: the mapping from
 * the 32 tsens sensors to five frequency/voltage domains and from those domains to the
 * pressure level macOS acts on. Every threshold here is a trip point of the board DTB,
 * cited by line in docs/research/thermal/05-PRESSURE-LEVEL.md; nothing is invented.
 *
 * The consumer side is macOS's: thermalmonitord copies the SMC key 'mTPL' into the
 * notification com.apple.system.thermalpressurelevel once a second (ThermalLevel.h:6-25
 * of the UniXNU-sheng port, which read that out of thermalmonitord of 27.3 26C5035r).
 * Publishing that service needs IOKit and a kernel link, so it stays out of this file:
 * here are the data and the arithmetic a host test can run, as in the reference port. */
#ifndef K60_THERMAL_LEVEL_H
#define K60_THERMAL_LEVEL_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

/* OSThermalPressureLevel (libkern/OSThermalNotification.h). Sleeping is never reported:
 * no trip point of this board stands for it. */
enum { K60TlNominal = 0, K60TlModerate = 1, K60TlHeavy = 2, K60TlTrapping = 3,
       K60TlSleeping = 4 };

/* The domains. Two CPU clusters, the GPU, the NPU and DDR: the five groups whose trip
 * points differ on this board (docs/research/thermal/01-SAME-HARDWARE.md §5.1). */
enum { K60TlInputs = 5,
       K60TlCpuLittle = 0, K60TlCpuBig = 1, K60TlGpu = 2, K60TlNpu = 3, K60TlDdr = 4 };

/* Three trip points per input: the domain's own warning trip, its reset-monitor trip and
 * the board-wide thermal-engine trip. Ascending, each with the DT's hysteresis. */
enum { K60TlTrips = 3 };

/* A reading that does not exist. A sensor without a reading counts as nominal and
 * forgets what it had crossed, so an unreadable sensor can neither raise the level nor
 * hold it up (ThermalLevel.h:56-59). */
#define K60TL_NO_READING INT32_MIN

typedef struct { int32_t milli_c, hysteresis_mc; } K60TlTrip;

/* Sensor index (0..31, the K60TsensTable order: tsens0 idx 0..15 then tsens1 0..15) to
 * the domain it feeds, or K60TlNoInput for sensors the level does not use (aoss, cpuss,
 * video, mdmss, camera: they have trips but no cooling action on this board). */
enum { K60TlNoInput = 0xffu };

typedef struct {
    uint8_t crossed[K60TlInputs]; /* trip points crossed per input at the last step */
} K60TlState;

/* The trip table of one input, and its name. NULL / "?" for an out-of-range input. */
const K60TlTrip *k60tl_trips(unsigned input);
const char *k60tl_input_name(unsigned input);
const char *k60tl_level_name(unsigned level);
unsigned k60tl_input_of_sensor(unsigned sensor);

/* The level of one input given how many of its trips were crossed before. A trip stays
 * crossed until the reading falls below its temperature less its hysteresis, which is
 * the thermal core's rule (ThermalLevel.h:73-83). Returns the new count (0..3) and
 * writes it to *crossed_after when that is not NULL. */
unsigned k60tl_input_level(unsigned crossed_before, int32_t milli_c,
                           const K60TlTrip *trips, unsigned trips_count,
                           unsigned *crossed_after);

/* One sampling round over all inputs; milli_c[i] is the hottest sensor of input i, or
 * K60TL_NO_READING. Returns the highest input level (the level macOS gets). state may be
 * NULL for a stateless query. */
unsigned k60tl_step(K60TlState *state, const int32_t *milli_c);

/* The number IOPMrootDomain understands for this level (iokit/IOKit/pwr_mgt/IOPM.h:763-772):
 * nominal 0, moderate 5, heavy 100, trapping 110. Only 100 and 110 move
 * IOPMrootDomain::thermalWarningState (iokit/Kernel/IOPMrootDomain.cpp:8133-8134); 0 and 5 are
 * recorded in the "Power Status" dictionary and broadcast, but change no policy. That
 * asymmetry is Apple's and it is why heavy, not moderate, is the first level with an effect.
 * bsd/dev/pong_thermal_pm.cpp hands this number to systemPowerEventOccurred under
 * kIOPMThermalLevelWarningKey; keeping the numbers here is what makes them host-testable. */
unsigned k60tl_platform_value(unsigned level);

#ifdef __cplusplus
}
#endif
#endif /* K60_THERMAL_LEVEL_H */
