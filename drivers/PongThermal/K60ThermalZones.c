/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* Data and arithmetic for the board's own thermal ladder. No register, no IOKit, no
 * allocation: the whole file runs on the host (scripts/tests/test-k60-thermal-zones.c).
 *
 * Every row below is one zone of /thermal-zones in the decompiled board DTS
 * (mondrian.dts:6643-8422), reduced to the passive trips that zone raises: ascending, with
 * the hysteresis the DT gives each one, duplicates by temperature removed (a zone that
 * carries both a thermal-engine and a thermal-hal copy of a trip has one temperature). The
 * comment above each row cites the DTS line of every trip it keeps, plus any active trip
 * the zone also has, which this layer does not use (active trips drive the modem gateway
 * cooling devices, docs/research/thermal/TRIP-DESIGN.md section 2.2).
 *
 * Only the tsens-backed zones are here, in the driver's sensor order; LEVEL-MAP.md
 * section 2 lists what is left out and why. */
#if defined(KERNEL)
#include <sys/pong_thermal_zones.h>
#else
#include "K60ThermalZones.h"
#endif

static const K60TzZone k60tz_table[K60TzZones] = {
	/* tsens0[0] aoss-0: 115000/5000 @7121, 125000/1000 @7115 */
	{ 2, { { 115000, 5000 }, { 125000, 1000 }, { 0, 0 } } },
	/* tsens0[1] cpuss-0: 115000/5000 @7142, 125000/1000 @7136 */
	{ 2, { { 115000, 5000 }, { 125000, 1000 }, { 0, 0 } } },
	/* tsens0[2] cpuss-1: 115000/5000 @7163, 125000/1000 @7157 */
	{ 2, { { 115000, 5000 }, { 125000, 1000 }, { 0, 0 } } },
	/* tsens0[3] cpuss-2: 115000/5000 @7184, 125000/1000 @7178 */
	{ 2, { { 115000, 5000 }, { 125000, 1000 }, { 0, 0 } } },
	/* tsens0[4] cpuss-3: 115000/5000 @7205, 125000/1000 @7199 */
	{ 2, { { 115000, 5000 }, { 125000, 1000 }, { 0, 0 } } },
	/* tsens0[5] cpu-1-0: 110000/10000 @7238, 115000/5000 @7232, 125000/1000 @7220 */
	{ 3, { { 110000, 10000 }, { 115000, 5000 }, { 125000, 1000 } } },
	/* tsens0[6] cpu-1-1: 110000/10000 @7272, 115000/5000 @7266, 125000/1000 @7254 */
	{ 3, { { 110000, 10000 }, { 115000, 5000 }, { 125000, 1000 } } },
	/* tsens0[7] cpu-1-2: 110000/10000 @7306, 115000/5000 @7300, 125000/1000 @7288 */
	{ 3, { { 110000, 10000 }, { 115000, 5000 }, { 125000, 1000 } } },
	/* tsens0[8] cpu-1-3: 110000/10000 @7348, 115000/5000 @7342, 125000/1000 @7330 */
	{ 3, { { 110000, 10000 }, { 115000, 5000 }, { 125000, 1000 } } },
	/* tsens0[9] cpu-1-4: 110000/10000 @7390, 115000/5000 @7384, 125000/1000 @7372 */
	{ 3, { { 110000, 10000 }, { 115000, 5000 }, { 125000, 1000 } } },
	/* tsens0[10] cpu-1-5: 110000/10000 @7432, 115000/5000 @7426, 125000/1000 @7414 */
	{ 3, { { 110000, 10000 }, { 115000, 5000 }, { 125000, 1000 } } },
	/* tsens0[11] cpu-1-6: 110000/10000 @7474, 115000/5000 @7468, 125000/1000 @7456 */
	{ 3, { { 110000, 10000 }, { 115000, 5000 }, { 125000, 1000 } } },
	/* tsens0[12] cpu-1-7: 110000/10000 @7516, 115000/5000 @7510, 125000/1000 @7498 */
	{ 3, { { 110000, 10000 }, { 115000, 5000 }, { 125000, 1000 } } },
	/* tsens0[13] cpu-1-8: 110000/10000 @7558, 115000/5000 @7552, 125000/1000 @7540 */
	{ 3, { { 110000, 10000 }, { 115000, 5000 }, { 125000, 1000 } } },
	/* tsens0[14] gpuss-0: 95000/5000 @7600, 115000/5000 @7594, 125000/1000 @7582 */
	{ 3, { { 95000, 5000 }, { 115000, 5000 }, { 125000, 1000 } } },
	/* tsens0[15] gpuss-1: 95000/5000 @7642, 115000/5000 @7636, 125000/1000 @7624 */
	{ 3, { { 95000, 5000 }, { 115000, 5000 }, { 125000, 1000 } } },
	/* tsens1[0] aoss-1: 115000/5000 @7672, 125000/1000 @7666 */
	{ 2, { { 115000, 5000 }, { 125000, 1000 }, { 0, 0 } } },
	/* tsens1[1] cpu-0-0: 110000/10000 @7705, 115000/5000 @7699, 125000/1000 @7687 */
	{ 3, { { 110000, 10000 }, { 115000, 5000 }, { 125000, 1000 } } },
	/* tsens1[2] cpu-0-1: 110000/10000 @7747, 115000/5000 @7741, 125000/1000 @7729 */
	{ 3, { { 110000, 10000 }, { 115000, 5000 }, { 125000, 1000 } } },
	/* tsens1[3] cpu-0-2: 110000/10000 @7789, 115000/5000 @7783, 125000/1000 @7771 */
	{ 3, { { 110000, 10000 }, { 115000, 5000 }, { 125000, 1000 } } },
	/* tsens1[4] cpu-0-3: 110000/10000 @7831, 115000/5000 @7825, 125000/1000 @7813 */
	{ 3, { { 110000, 10000 }, { 115000, 5000 }, { 125000, 1000 } } },
	/* tsens1[5] nspss-0: 95000/5000 @7873, 115000/5000 @7867, 125000/1000 @7855 */
	{ 3, { { 95000, 5000 }, { 115000, 5000 }, { 125000, 1000 } } },
	/* tsens1[6] nspss-1: 95000/5000 @7915, 115000/5000 @7909, 125000/1000 @7897 */
	{ 3, { { 95000, 5000 }, { 115000, 5000 }, { 125000, 1000 } } },
	/* tsens1[7] nspss-2: 95000/5000 @7957, 115000/5000 @7951, 125000/1000 @7939 */
	{ 3, { { 95000, 5000 }, { 115000, 5000 }, { 125000, 1000 } } },
	/* tsens1[8] video: 115000/5000 @7987, 125000/1000 @7981 */
	{ 2, { { 115000, 5000 }, { 125000, 1000 }, { 0, 0 } } },
	/* tsens1[9] ddr: 90000/5000 @8008, 115000/5000 @8015, 125000/1000 @8002 */
	{ 3, { { 90000, 5000 }, { 115000, 5000 }, { 125000, 1000 } } },
	/* tsens1[10] mdmss-0: 115000/5000 @8068, 125000/1000 @8048 active 102000 @8054, 105000 @8061 not used */
	{ 2, { { 115000, 5000 }, { 125000, 1000 }, { 0, 0 } } },
	/* tsens1[11] mdmss-1: 115000/5000 @8131, 125000/1000 @8111 active 102000 @8117, 105000 @8124 not used */
	{ 2, { { 115000, 5000 }, { 125000, 1000 }, { 0, 0 } } },
	/* tsens1[12] mdmss-2: 115000/5000 @8194, 125000/1000 @8174 active 102000 @8180, 105000 @8187 not used */
	{ 2, { { 115000, 5000 }, { 125000, 1000 }, { 0, 0 } } },
	/* tsens1[13] mdmss-3: 115000/5000 @8257, 125000/1000 @8237 active 102000 @8243, 105000 @8250 not used */
	{ 2, { { 115000, 5000 }, { 125000, 1000 }, { 0, 0 } } },
	/* tsens1[14] camera-0: 115000/5000 @8306, 125000/1000 @8300 */
	{ 2, { { 115000, 5000 }, { 125000, 1000 }, { 0, 0 } } },
	/* tsens1[15] camera-1: 115000/5000 @8327, 125000/1000 @8321 */
	{ 2, { { 115000, 5000 }, { 125000, 1000 }, { 0, 0 } } },
};

/* The DTS name of each zone, in the same order. scripts/tests/test-k60-thermal-zones.c
 * checks these against the sensor table in pong_thermal.h, which names the same zones. */
static const char *const k60tz_names[K60TzZones] = {
	"aoss-0", "cpuss-0", "cpuss-1", "cpuss-2",
	"cpuss-3", "cpu-1-0", "cpu-1-1", "cpu-1-2",
	"cpu-1-3", "cpu-1-4", "cpu-1-5", "cpu-1-6",
	"cpu-1-7", "cpu-1-8", "gpuss-0", "gpuss-1",
	"aoss-1", "cpu-0-0", "cpu-0-1", "cpu-0-2",
	"cpu-0-3", "nspss-0", "nspss-1", "nspss-2",
	"video", "ddr", "mdmss-0", "mdmss-1",
	"mdmss-2", "mdmss-3", "camera-0", "camera-1",
};

const K60TzZone *
k60tz_zone(unsigned slot)
{
	return slot < K60TzZones ? &k60tz_table[slot] : (const K60TzZone *)0;
}

const char *
k60tz_name(unsigned slot)
{
	return slot < K60TzZones ? k60tz_names[slot] : "?";
}

unsigned
k60tz_zone_level(uint8_t crossed_before, int32_t milli_c, unsigned slot,
    uint8_t *crossed_after)
{
	const K60TzZone *zone = k60tz_zone(slot);
	unsigned after = 0;
	unsigned level;

	if (crossed_after != (uint8_t *)0) {
		*crossed_after = 0;
	}
	if (zone == (const K60TzZone *)0) {
		return 0;
	}
	level = k60tl_input_level(crossed_before, milli_c, zone->trips, zone->tiers, &after);
	if (crossed_after != (uint8_t *)0) {
		*crossed_after = (uint8_t)after;
	}
	return level;
}

unsigned
k60tz_step(K60TzState *state, const int32_t *milli_c)
{
	unsigned worst = 0;

	for (unsigned slot = 0; slot < K60TzZones; slot++) {
		const int32_t mc = milli_c != (const int32_t *)0 ? milli_c[slot] : K60TL_NO_READING;
		const uint8_t before = state != (K60TzState *)0 ? state->crossed[slot] : 0u;
		uint8_t after = 0;
		const unsigned level = k60tz_zone_level(before, mc, slot, &after);

		if (state != (K60TzState *)0) {
			state->crossed[slot] = after;
		}
		if (level > worst) {
			worst = level;
		}
	}
	return worst;
}

int
k60tz_closest(const int32_t *milli_c, struct K60TzClosest *out)
{
	int found = 0;
	int32_t best_margin = 0;

	if (out == (struct K60TzClosest *)0) {
		return -1;
	}
	out->milli_c = K60TL_NO_READING;
	out->margin_mc = 0;
	out->slot = 0;
	out->level = 0;
	out->next_tier = 0;
	if (milli_c == (const int32_t *)0) {
		return -1;
	}
	for (unsigned slot = 0; slot < K60TzZones; slot++) {
		const K60TzZone *zone = &k60tz_table[slot];
		const int32_t mc = milli_c[slot];
		unsigned level;
		int32_t margin;

		if (mc == K60TL_NO_READING) {
			continue;
		}
		level = k60tz_zone_level(0u, mc, slot, (uint8_t *)0);
		if (level >= zone->tiers) {
			margin = -1;
		} else {
			margin = zone->trips[level].milli_c - mc;
		}
		if (found == 0 || margin < best_margin) {
			found = 1;
			best_margin = margin;
			out->milli_c = mc;
			out->margin_mc = margin;
			out->slot = (uint8_t)slot;
			out->level = (uint8_t)level;
			out->next_tier = (uint8_t)(level < zone->tiers ? level : zone->tiers - 1u);
		}
	}
	return found != 0 ? 0 : -1;
}
