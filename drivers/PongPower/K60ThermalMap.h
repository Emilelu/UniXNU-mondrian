/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/*
 * Trip map for the AP-side thermal zones of the K60, taken from the live
 * device tree (E:/k60-work/reports/live-6033dbec-fdt.dts, 82 zones, 18 cooling
 * devices). This module is the contract half of the thermal line: it answers
 * "how hot is too hot, and what does that forbid" with no sensor, no IOKit and
 * no MMIO. A caller owns the sensor read (tsens, ADC or PMIC alarm) and passes
 * the millidegrees in.
 *
 * Trip ladder, as the live FDT declares it for the AP-side zones:
 *   90000  thermal-engine-config / active-config / ddr0-config / PMIC trip0
 *   95000  tj_cfg, junction and PMIC junction
 *   110000 per-CPU emergency
 *   115000 reset-mon-cfg
 *   125000 thermal-engine / thermal-hal shutdown
 *
 * Policy derived from those numbers:
 *   - an upward work point is refused from the emergency trip on, which is the
 *     thermal gate section 5 :108 asks for (k60_rail_plan takes allow_raise);
 *   - the junction trip engages the cooling device of the hot domain only;
 *   - the emergency trip engages both domains regardless of which zone read it.
 * The zones listed here are the ones an AP driver can act on. Modem, camera,
 * NSP, video and QMI zones are deliberately absent: their owner is a remote
 * processor, and a K60 kernel driver must not throttle them.
 */
#ifndef K60_THERMAL_MAP_H
#define K60_THERMAL_MAP_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

enum k60_thermal_zone {
    K60ThermalZoneCpu0 = 0,   /* cpu-0-0..3, tsens1 ids 1..4 */
    K60ThermalZoneCpu1,       /* cpu-1-0..8, tsens0 ids 5..13 */
    K60ThermalZoneCpuss,      /* cpuss-0..3, tsens0 ids 0..3 */
    K60ThermalZoneGpuss,      /* gpuss-0/1, tsens0 ids 14/15 */
    K60ThermalZoneDdr,        /* ddr, tsens0 id 9 */
    K60ThermalZoneAoss,       /* aoss-0/1, always-on subsystem */
    K60ThermalZonePm8350,     /* pm8350 temp-alarm, trip0 95 C */
    K60ThermalZonePm8350C,    /* pm8350c temp-alarm */
    K60ThermalZonePm8450,     /* pm8450 temp-alarm */
    K60ThermalZoneCount
};

enum k60_thermal_level {
    K60ThermalLevelNone = 0,
    K60ThermalLevelWarm,
    K60ThermalLevelJunction,
    K60ThermalLevelEmergency,
    K60ThermalLevelReset,
    K60ThermalLevelShutdown,
    K60ThermalLevelCount
};

#define K60_THERMAL_TRIP_WARM 90000
#define K60_THERMAL_TRIP_JUNCTION 95000
#define K60_THERMAL_TRIP_EMERGENCY 110000
#define K60_THERMAL_TRIP_RESET 115000
#define K60_THERMAL_TRIP_SHUTDOWN 125000
#define K60_THERMAL_MAX_READINGS 16

typedef struct {
    int zone;
    int32_t millideg;
} K60ThermalReading;

typedef struct {
    int zone;                 /* -1 when nothing crossed a trip */
    int32_t millideg;         /* the winning reading, 0 when nothing crossed */
    enum k60_thermal_level level;
    int allow_raise;          /* 0 from the emergency trip on */
    int throttle_cpu;         /* 1 when this reading throttles the CPU domains */
    int throttle_gpu;         /* 1 when this reading throttles the GPU domain */
} K60ThermalAdvisory;

/* Zone and level names, "invalid" for an unknown argument. */
const char *k60_thermal_zone_name(int zone);
const char *k60_thermal_level_name(enum k60_thermal_level level);

/* Level for a plain temperature. Negative values are None. */
enum k60_thermal_level k60_thermal_level_at(int32_t millideg);

/* Level for one zone reading; -1 when the zone is unknown. */
int k60_thermal_zone_level(int zone, int32_t millideg);

/* Aggregate the readings into the advisory the rail planner consumes. The
 * worst reading wins: highest level, then highest temperature, then the lowest
 * zone index. Returns 0 on success, -1 for a null output, -2 for a null reading
 * array with a non-zero count, -3 when count exceeds K60_THERMAL_MAX_READINGS
 * and -4 for an unknown zone. An empty input is a valid None advisory. */
int k60_thermal_advise(const K60ThermalReading *readings, unsigned count,
                       K60ThermalAdvisory *out);

#ifdef __cplusplus
}
#endif
#endif
