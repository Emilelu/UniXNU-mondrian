/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* The board DTS's own thermal ladder: one zone per tsens sensor, and the levels each
 * zone can reach.
 *
 * The board declares 154 trip points under /thermal-zones (mondrian.dts:6643-8422); 146
 * are passive and 8 are active. Every zone that reads a tsens sensor directly raises its
 * own short ladder of passive trips: the thermal-engine and thermal-hal copies, the reset
 * monitor, and for the CPU clusters the emergency shutdown trip. This module keeps that
 * ladder, one row per sensor in the order the driver samples them (tsens0 idx 0..15 then
 * tsens1 idx 0..15), so the level it reports is the board's own number and not a table
 * invented here.
 *
 * What a level means (docs/research/thermal/LEVEL-MAP.md section 3):
 *   0  no passive trip of this zone is crossed
 *   1  the zone's lowest passive trip is crossed
 *   2  its second one is crossed
 *   3  its third one is crossed (zones with two trips stop at 2)
 * A crossed trip is released only below its temperature minus the DT hysteresis, the
 * thermal core's rule; k60tl_input_level in pong_thermal_level.h does that arithmetic and
 * is reused here rather than duplicated.
 *
 * The board level is the highest zone level. Two kinds of DTS zone are deliberately not
 * in the table: the 25 zones that read the QMI proxy (thermal-sensors = <0x5c ...>,
 * phandle 0x5c is qmi-ts-sensors at mondrian.dts:16774), whose temperatures come from the
 * modem and are not in any window this kernel maps; and the two zones whose "trips" are
 * not temperatures at all (mx-pe, passive 1/2/3 with status = "disabled" at
 * mondrian.dts:8336; isense_trim, passive 2 at :8397). LEVEL-MAP.md section 2 lists both.
 *
 * The same file ships twice: as this master copy and as bsd/sys/pong_thermal_zones.h
 * inside patches/xnu/0617-k60-thermal-tsens.patch, where the level header is
 * bsd/sys/pong_thermal_level.h. scripts/check-thermal-kernel-patch.py fails when the two
 * copies differ. */
#ifndef K60_THERMAL_ZONES_H
#define K60_THERMAL_ZONES_H

#include <stdint.h>
#if defined(KERNEL)
#include <sys/pong_thermal_level.h>
#else
#include "K60ThermalLevel.h"
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* One row per sampled sensor, in the driver's sensor order. */
enum { K60TzZones = 32, K60TzTiers = 3 };

/* The passive trips of one zone ascending by temperature, each with the DT hysteresis.
 * A zone with fewer trips than K60TzTiers leaves the rest at zero and reports tiers. */
typedef struct {
	uint8_t tiers;
	K60TlTrip trips[K60TzTiers];
} K60TzZone;

/* Trips crossed per zone at the last step, so a trip is only released below its
 * temperature minus hysteresis. */
typedef struct {
	uint8_t crossed[K60TzZones];
} K60TzState;

/* The zone closest to its next trip. The sampler logs this, because a boot at 45 C still
 * has to show how far the board is from level 1 (LEVEL-MAP.md section 5.2). */
struct K60TzClosest {
	int32_t milli_c;   /* the reading */
	int32_t margin_mc; /* mC left before the next trip; -1 when every trip is crossed */
	uint8_t slot;      /* sensor slot 0..31 */
	uint8_t level;     /* that zone's level now */
	uint8_t next_tier; /* index into the zone's trips, clamped to tiers - 1 */
};

/* The row of one sensor and the board DTS's name for its zone ("cpu-1-0", "ddr", ...).
 * NULL and "?" for an out-of-range slot. */
const K60TzZone *k60tz_zone(unsigned slot);
const char *k60tz_name(unsigned slot);

/* The level of one zone given how many of its trips were crossed before, with the new
 * count in *crossed_after (may be NULL). A missing reading gives level 0 and forgets the
 * crossings, so an unreadable sensor can neither raise the level nor hold it up. */
unsigned k60tz_zone_level(uint8_t crossed_before, int32_t milli_c, unsigned slot,
    uint8_t *crossed_after);

/* One sampling round over all 32 zones; milli_c[slot] is that sensor's reading or
 * K60TL_NO_READING. Returns the board level 0..3. state may be NULL for a stateless
 * query. */
unsigned k60tz_step(K60TzState *state, const int32_t *milli_c);

/* The zone closest to its next trip. Returns 0 and fills *out when at least one sensor has
 * a reading, -1 otherwise. */
int k60tz_closest(const int32_t *milli_c, struct K60TzClosest *out);

#ifdef __cplusplus
}
#endif
#endif /* K60_THERMAL_ZONES_H */
