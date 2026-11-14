/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* Data and arithmetic for the board's thermal pressure level. No register, no IOKit, no
 * allocation: the whole file runs on the host (scripts/tests/test-k60-thermal-level.c).
 * Threshold provenance is in docs/research/thermal/05-PRESSURE-LEVEL.md §2, one line per
 * number, all from /tmp/mondrian.dts of this board. */
#include "K60ThermalLevel.h"

/* CPU cluster 0 (cpu-0-0..3): emerg 110 C / 10 C (:7706, :7707), reset-mon 115 C / 5 C
 * (:7700, :7701), thermal-engine 125 C / 1 C (:7688, :7689). The big cluster
 * (cpu-1-0..8) has the same three numbers (:7239, :7233, :7221), so both clusters share
 * one table. */
static const K60TlTrip k60tl_cpu_trips[K60TlTrips] = {
    {110000, 10000}, {115000, 5000}, {125000, 1000}
};

/* GPU: tj 95 C / 5 C (:7601, :7602), reset-mon 115 C / 5 C (:7595, :7596), engine
 * 125 C / 1 C (:7583, :7584). */
static const K60TlTrip k60tl_gpu_trips[K60TlTrips] = {
    {95000, 5000}, {115000, 5000}, {125000, 1000}
};

/* NPU: junction 95 C / 5 C (:7874, :7875), reset-mon 115 C / 5 C (:7868, :7869),
 * engine 125 C / 1 C (:7856, :7857). */
static const K60TlTrip k60tl_npu_trips[K60TlTrips] = {
    {95000, 5000}, {115000, 5000}, {125000, 1000}
};

/* DDR: ddr0 90 C / 5 C (:8009, :8010), reset-mon 115 C / 5 C (:8016, :8017), engine
 * 125 C / 1 C (:8003, :8004). */
static const K60TlTrip k60tl_ddr_trips[K60TlTrips] = {
    {90000, 5000}, {115000, 5000}, {125000, 1000}
};

static const char *const k60tl_input_names[K60TlInputs] = {
    "cpu-little", "cpu-big", "gpu", "npu", "ddr"
};

static const char *const k60tl_level_names[5] = {
    "nominal", "moderate", "heavy", "trapping", "sleeping"
};

/* tsens0 idx 0..15 then tsens1 idx 0..15 (drivers/PongThermal/K60Tsens.c table order). */
static const uint8_t k60tl_sensor_input[32] = {
    K60TlNoInput, K60TlNoInput, K60TlNoInput, K60TlNoInput,          /* aoss-0, cpuss-0..2 */
    K60TlNoInput,                                                    /* cpuss-3 */
    K60TlCpuBig, K60TlCpuBig, K60TlCpuBig, K60TlCpuBig,              /* cpu-1-0..3 */
    K60TlCpuBig, K60TlCpuBig, K60TlCpuBig, K60TlCpuBig,              /* cpu-1-4..7 */
    K60TlCpuBig,                                                     /* cpu-1-8 */
    K60TlGpu, K60TlGpu,                                              /* gpuss-0/1 */
    K60TlNoInput,                                                    /* aoss-1 */
    K60TlCpuLittle, K60TlCpuLittle, K60TlCpuLittle, K60TlCpuLittle,  /* cpu-0-0..3 */
    K60TlNpu, K60TlNpu, K60TlNpu,                                    /* nspss-0..2 */
    K60TlNoInput,                                                    /* video */
    K60TlDdr,                                                        /* ddr */
    K60TlNoInput, K60TlNoInput, K60TlNoInput, K60TlNoInput,          /* mdmss-0..3 */
    K60TlNoInput, K60TlNoInput                                       /* camera-0/1 */
};

const K60TlTrip *k60tl_trips(unsigned input)
{
    switch (input) {
    case K60TlCpuLittle:
    case K60TlCpuBig:   return k60tl_cpu_trips;
    case K60TlGpu:      return k60tl_gpu_trips;
    case K60TlNpu:      return k60tl_npu_trips;
    case K60TlDdr:      return k60tl_ddr_trips;
    default:            return (const K60TlTrip *)0;
    }
}

const char *k60tl_input_name(unsigned input)
{
    return input < K60TlInputs ? k60tl_input_names[input] : "?";
}

const char *k60tl_level_name(unsigned level)
{
    return level <= K60TlSleeping ? k60tl_level_names[level] : "?";
}

unsigned k60tl_input_of_sensor(unsigned sensor)
{
    return sensor < 32u ? k60tl_sensor_input[sensor] : K60TlNoInput;
}

unsigned k60tl_input_level(unsigned crossed_before, int32_t milli_c,
                           const K60TlTrip *trips, unsigned trips_count,
                           unsigned *crossed_after)
{
    unsigned level = 0;

    if (crossed_after != (unsigned *)0) *crossed_after = 0;
    if (trips == (const K60TlTrip *)0 || trips_count == 0u) return 0;
    if (milli_c == K60TL_NO_READING) return 0;

    for (unsigned t = 0; t < trips_count; ++t) {
        /* A trip already crossed is released only below temperature - hysteresis. */
        const int32_t threshold = crossed_before > t
            ? trips[t].milli_c - trips[t].hysteresis_mc
            : trips[t].milli_c;
        if (milli_c < threshold) break;
        level = t + 1u;
    }
    if (crossed_after != (unsigned *)0) *crossed_after = level;
    return level;
}

unsigned k60tl_step(K60TlState *state, const int32_t *milli_c)
{
    unsigned worst = K60TlNominal;

    for (unsigned i = 0; i < K60TlInputs; ++i) {
        const int32_t mc = milli_c != (const int32_t *)0 ? milli_c[i] : K60TL_NO_READING;
        const unsigned before = state != (K60TlState *)0 ? state->crossed[i] : 0u;
        unsigned after = 0;
        const unsigned level = k60tl_input_level(before, mc, k60tl_trips(i),
                                                 K60TlTrips, &after);
        if (state != (K60TlState *)0) state->crossed[i] = (uint8_t)after;
        if (level > worst) worst = level;
    }
    return worst;
}
