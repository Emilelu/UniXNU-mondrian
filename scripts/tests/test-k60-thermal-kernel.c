/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Host test for the board description shared by the in-kernel tsens reader
 * (bsd/dev/pong_thermal.c) and the macOS side.
 *
 * The kernel copy lives inside patches/xnu/0617-k60-thermal-tsens.patch; this
 * test compiles the repository master copy (drivers/PongThermal/K60ThermalKernel.h)
 * and scripts/check-thermal-kernel-patch.py proves the patch carries the same
 * bytes. Everything here is pure arithmetic: no MMIO, no kernel headers.
 *
 *   cc -std=c11 -O1 -Wall -Wextra -Werror -I drivers/PongThermal \
 *      -o build/thermal/test-kernel scripts/tests/test-k60-thermal-kernel.c */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../../drivers/PongThermal/K60ThermalKernel.h"

static int failures;
static int checks;

#define CHECK(cond) do { \
	checks++; \
	if (!(cond)) { \
		failures++; \
		printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); \
	} \
} while (0)

#define CHECK_EQ(actual, expected) do { \
	long long a_ = (long long)(actual); \
	long long e_ = (long long)(expected); \
	checks++; \
	if (a_ != e_) { \
		failures++; \
		printf("FAIL %s:%d: %s == %lld, want %lld\n", \
		    __FILE__, __LINE__, #actual, a_, e_); \
	} \
} while (0)

static void
test_status_to_mc(void)
{
	/* 60.0 C: the v2 status word already holds deci-Celsius. */
	CHECK_EQ(pong_thermal_status_to_mc(0x00000258u), 60000);
	/* -10.0 C: 12-bit two's complement, 0xf9c. */
	CHECK_EQ(pong_thermal_status_to_mc(0x00000f9cu), -10000);
	/* 0 C and the extremes of the 12-bit field. */
	CHECK_EQ(pong_thermal_status_to_mc(0x00000000u), 0);
	CHECK_EQ(pong_thermal_status_to_mc(0x000007ffu), 204700);
	CHECK_EQ(pong_thermal_status_to_mc(0x00000800u), -204800);
	/* Upper status bits must not leak into the temperature. */
	CHECK_EQ(pong_thermal_status_to_mc(0x003ff258u), 60000);
	CHECK_EQ(pong_thermal_status_to_mc(0xfffff258u), 60000);
}

static void
test_status_flags(void)
{
	CHECK_EQ(pong_thermal_status_flags(0x00000000u), 0);
	CHECK_EQ(pong_thermal_status_flags(0x001f0000u), 31);
	CHECK_EQ(pong_thermal_status_flags(0x00030000u), 3);
	/* Temperature and VALID bits are not flags. */
	CHECK_EQ(pong_thermal_status_flags(0x00200258u), 0);
}

static void
test_decode(void)
{
	struct pong_thermal_reading reading;

	/* VALID plus 45.5 C: 0x1c7 = 455 deci-Celsius. */
	memset(&reading, 0xa5, sizeof(reading));
	CHECK_EQ(pong_thermal_decode(0x002001c7u, &reading), PONG_THERMAL_OK);
	CHECK_EQ(reading.valid, 1);
	CHECK_EQ(reading.milli_c, 45500);
	CHECK_EQ(reading.flags, 0);

	/* No VALID bit: no reading, but the flags are still reported. */
	memset(&reading, 0xa5, sizeof(reading));
	CHECK_EQ(pong_thermal_decode(0x00010258u, &reading), PONG_THERMAL_NO_VALID);
	CHECK_EQ(reading.valid, 0);
	CHECK_EQ(reading.flags, 1);

	/* VALID but far outside the plausibility window. */
	memset(&reading, 0xa5, sizeof(reading));
	CHECK_EQ(pong_thermal_decode(0x002007ffu, &reading), PONG_THERMAL_OUT_OF_RANGE);
	CHECK_EQ(reading.valid, 0);

	/* Negative but plausible. */
	memset(&reading, 0xa5, sizeof(reading));
	CHECK_EQ(pong_thermal_decode(0x00200f9cu, &reading), PONG_THERMAL_OK);
	CHECK_EQ(reading.milli_c, -10000);

	/* A null output pointer is a caller bug, not a crash. */
	CHECK_EQ(pong_thermal_decode(0x002001c7u, NULL), PONG_THERMAL_BAD_ARG);
}

static void
test_ctrl(void)
{
	CHECK_EQ(pong_thermal_ctrl_enabled(0x00000001u), 1);
	CHECK_EQ(pong_thermal_ctrl_enabled(0xfffffffeu), 0);
	CHECK_EQ(pong_thermal_ctrl_enabled(0x00000000u), 0);
	CHECK_EQ(pong_thermal_ctrl_enabled(0x00000003u), 1);
}

static void
test_version(void)
{
	/* SROT_HW_VER: major 28..31, minor 16..27, step 0..15. */
	CHECK_EQ(PONG_THERMAL_VER_MAJOR(0x10020003u), 1);
	CHECK_EQ(PONG_THERMAL_VER_MINOR(0x10020003u), 2);
	CHECK_EQ(PONG_THERMAL_VER_STEP(0x10020003u), 3);
	CHECK_EQ(PONG_THERMAL_VER_MAJOR(0xf0000000u), 15);
	CHECK_EQ(PONG_THERMAL_VER_MINOR(0x0ffff000u), 0xfff);
	CHECK_EQ(PONG_THERMAL_VER_STEP(0x0000ffffu), 0xffff);
}

static void
test_offsets(void)
{
	CHECK_EQ(PONG_THERMAL_TM_SN_STATUS(0), 0x0a0);
	CHECK_EQ(PONG_THERMAL_TM_SN_STATUS(1), 0x0a4);
	CHECK_EQ(PONG_THERMAL_TM_SN_STATUS(15), 0x0dc);
	/* The last sensor word stays inside the 0x200-byte TM window. */
	CHECK(PONG_THERMAL_TM_SN_STATUS(15) + 4 <= 0x200);
	CHECK_EQ(PONG_THERMAL_TM_TRDY, 0x0e4);
	CHECK_EQ(PONG_THERMAL_SROT_HW_VER, 0x000);
	CHECK_EQ(PONG_THERMAL_SROT_CTRL, 0x004);
}

static void
test_sensor_table(void)
{
	unsigned seen[PONG_THERMAL_CONTROLLERS][PONG_THERMAL_SENSORS_PER_CONTROLLER];
	unsigned slot, c, i;
	unsigned domains[PONG_THERMAL_DOMAINS];

	memset(seen, 0, sizeof(seen));
	memset(domains, 0, sizeof(domains));
	for (slot = 0; slot < PONG_THERMAL_SENSOR_COUNT; slot++) {
		const struct pong_thermal_sensor *sensor = &pong_thermal_sensors[slot];

		CHECK(sensor->name != NULL);
		CHECK(sensor->controller < PONG_THERMAL_CONTROLLERS);
		CHECK(sensor->index < PONG_THERMAL_SENSORS_PER_CONTROLLER);
		/* Zone ids are the live Android ids 24..55 in DT order. */
		CHECK_EQ(sensor->zone, 24 + slot);
		if (sensor->controller < PONG_THERMAL_CONTROLLERS &&
		    sensor->index < PONG_THERMAL_SENSORS_PER_CONTROLLER) {
			seen[sensor->controller][sensor->index]++;
		}
		if (sensor->domain < PONG_THERMAL_DOMAINS) {
			domains[sensor->domain]++;
		}
	}
	/* Every controller/index pair appears exactly once: 2 x 16 = 32. */
	for (c = 0; c < PONG_THERMAL_CONTROLLERS; c++) {
		for (i = 0; i < PONG_THERMAL_SENSORS_PER_CONTROLLER; i++) {
			CHECK_EQ(seen[c][i], 1);
		}
	}
	/* All five pressure-level domains are covered by at least one sensor. */
	for (i = 0; i < PONG_THERMAL_DOMAINS; i++) {
		CHECK(domains[i] > 0);
	}
	CHECK_EQ(domains[PONG_THERMAL_DOMAIN_LITTLE], 4);
	CHECK_EQ(domains[PONG_THERMAL_DOMAIN_BIG], 9);
	CHECK_EQ(domains[PONG_THERMAL_DOMAIN_GPU], 2);
	CHECK_EQ(domains[PONG_THERMAL_DOMAIN_NPU], 3);
	CHECK_EQ(domains[PONG_THERMAL_DOMAIN_DDR], 1);
}

static void
test_sensor_names(void)
{
	unsigned slot;
	static const char *const expected[PONG_THERMAL_SENSOR_COUNT] = {
		"aoss-0", "cpuss-0", "cpuss-1", "cpuss-2", "cpuss-3",
		"cpu-1-0", "cpu-1-1", "cpu-1-2", "cpu-1-3", "cpu-1-4",
		"cpu-1-5", "cpu-1-6", "cpu-1-7", "cpu-1-8", "gpuss-0", "gpuss-1",
		"aoss-1", "cpu-0-0", "cpu-0-1", "cpu-0-2", "cpu-0-3",
		"nspss-0", "nspss-1", "nspss-2", "video", "ddr",
		"mdmss-0", "mdmss-1", "mdmss-2", "mdmss-3", "camera-0", "camera-1",
	};

	for (slot = 0; slot < PONG_THERMAL_SENSOR_COUNT; slot++) {
		CHECK(strcmp(pong_thermal_sensors[slot].name, expected[slot]) == 0);
	}
	/* Out of range lookups return null instead of reading past the table. */
	CHECK(pong_thermal_sensor_at(PONG_THERMAL_SENSOR_COUNT) == NULL);
	CHECK(pong_thermal_sensor_at(1000) == NULL);
	CHECK(pong_thermal_sensor_at(0) == &pong_thermal_sensors[0]);
	CHECK(pong_thermal_sensor_at(PONG_THERMAL_SENSOR_COUNT - 1) ==
	    &pong_thermal_sensors[PONG_THERMAL_SENSOR_COUNT - 1]);
}

static void
test_domain_max(void)
{
	int32_t milli_c[PONG_THERMAL_SENSOR_COUNT];
	int32_t out[PONG_THERMAL_DOMAINS];
	unsigned slot;

	/* Nothing valid anywhere: every domain keeps INT32_MIN. */
	for (slot = 0; slot < PONG_THERMAL_SENSOR_COUNT; slot++) {
		milli_c[slot] = INT32_MIN;
	}
	pong_thermal_domain_max(milli_c, out);
	for (slot = 0; slot < PONG_THERMAL_DOMAINS; slot++) {
		CHECK_EQ(out[slot], INT32_MIN);
	}

	/* Distinct temperatures: each domain reports its own hottest sensor. */
	for (slot = 0; slot < PONG_THERMAL_SENSOR_COUNT; slot++) {
		milli_c[slot] = (int32_t)(40000 + slot * 1000);
	}
	pong_thermal_domain_max(milli_c, out);
	CHECK_EQ(out[PONG_THERMAL_DOMAIN_LITTLE], 60000);  /* slot 20, cpu-0-3 */
	CHECK_EQ(out[PONG_THERMAL_DOMAIN_BIG], 53000);     /* slot 13, cpu-1-8 */
	CHECK_EQ(out[PONG_THERMAL_DOMAIN_GPU], 55000);     /* slot 15, gpuss-1 */
	CHECK_EQ(out[PONG_THERMAL_DOMAIN_NPU], 63000);     /* slot 23, nspss-2 */
	CHECK_EQ(out[PONG_THERMAL_DOMAIN_DDR], 65000);     /* slot 25, ddr */

	/* A single hot sensor lifts only its own domain. */
	for (slot = 0; slot < PONG_THERMAL_SENSOR_COUNT; slot++) {
		milli_c[slot] = 40000;
	}
	milli_c[6] = 99000;   /* cpu-1-1 -> big */
	pong_thermal_domain_max(milli_c, out);
	CHECK_EQ(out[PONG_THERMAL_DOMAIN_BIG], 99000);
	CHECK_EQ(out[PONG_THERMAL_DOMAIN_LITTLE], 40000);
	CHECK_EQ(out[PONG_THERMAL_DOMAIN_GPU], 40000);

	/* Sensors without a domain never appear in the output. */
	for (slot = 0; slot < PONG_THERMAL_SENSOR_COUNT; slot++) {
		milli_c[slot] = 40000;
	}
	milli_c[0] = 150000;   /* aoss-0 -> no domain */
	milli_c[24] = 150000;  /* video -> no domain */
	milli_c[31] = 150000;  /* camera-1 -> no domain */
	pong_thermal_domain_max(milli_c, out);
	for (slot = 0; slot < PONG_THERMAL_DOMAINS; slot++) {
		CHECK_EQ(out[slot], 40000);
	}
}

int
main(void)
{
	test_status_to_mc();
	test_status_flags();
	test_decode();
	test_ctrl();
	test_version();
	test_offsets();
	test_sensor_table();
	test_sensor_names();
	test_domain_max();

	if (failures != 0) {
		printf("TESTS FAILED %d of %d\n", failures, checks);
		return 1;
	}
	printf("TESTS OK %d\n", checks);
	return 0;
}
