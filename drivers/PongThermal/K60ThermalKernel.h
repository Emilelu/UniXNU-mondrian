/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* Board thermal-sensor description shared by the in-kernel tsens reader and its
 * host test. Read-only by construction: nothing here writes a register.
 *
 * patches/xnu/0617-k60-thermal-tsens.patch carries a verbatim copy of this file
 * into the XNU tree as bsd/sys/pong_thermal.h, because the kernel cannot see
 * drivers/PongThermal. scripts/tests/test-k60-thermal-kernel.c extracts the copy
 * out of the patch and fails if the two ever differ, so the code that ships is
 * the code that is tested.
 *
 * Register map and field layout: mainline Linux drivers/thermal/qcom/tsens-v2.c
 * (v6.6) lines 12-27 and 94-101, cross-checked against the vendor qcom_tsens.ko
 * (see docs/research/thermal/04-ANDROID-EVIDENCE.md). Sensor order: board DTB
 * /soc/thermal-zones, see docs/research/thermal/01-SAME-HARDWARE.md section 5.1. */
#ifndef _SYS_PONG_THERMAL_H_
#define _SYS_PONG_THERMAL_H_

#include <stdint.h>

/* /soc/thermal-sensor@c263000 and @c265000, each with #qcom,sensors = <16>. */
enum {
	PONG_THERMAL_CONTROLLERS = 2,
	PONG_THERMAL_SENSORS_PER_CONTROLLER = 16,
	PONG_THERMAL_SENSOR_COUNT = 32,
	PONG_THERMAL_DOMAINS = 5
};

/* Pressure-level domains, the same five the macOS side consumes. */
enum {
	PONG_THERMAL_DOMAIN_LITTLE = 0,
	PONG_THERMAL_DOMAIN_BIG = 1,
	PONG_THERMAL_DOMAIN_GPU = 2,
	PONG_THERMAL_DOMAIN_NPU = 3,
	PONG_THERMAL_DOMAIN_DDR = 4,
	PONG_THERMAL_DOMAIN_NONE = 0xff
};

/* TM block, tsens-v2.c:25-26. Byte offsets; the driver converts to word indexes. */
#define PONG_THERMAL_TM_SN_STATUS(n) (0x0a0u + 4u * (uint32_t)(n))
#define PONG_THERMAL_TM_TRDY         0x0e4u
/* SROT block, tsens-v2.c:12-13. Read only: TSENS_EN is never set by this code. */
#define PONG_THERMAL_SROT_HW_VER     0x000u
#define PONG_THERMAL_SROT_CTRL       0x004u

/* TM_Sn_STATUS fields, tsens-v2.c:94-101. */
#define PONG_THERMAL_STATUS_TEMP_MASK 0x00000fffu
#define PONG_THERMAL_STATUS_VALID     (1u << 21)
#define PONG_THERMAL_STATUS_FLAG_MASK 0x001f0000u
#define PONG_THERMAL_STATUS_FLAG_SHIFT 16

/* SROT_HW_VER fields, tsens-v2.c:56-58. */
#define PONG_THERMAL_VER_MAJOR(v) (((v) >> 28) & 0x0fu)
#define PONG_THERMAL_VER_MINOR(v) (((v) >> 16) & 0x0fffu)
#define PONG_THERMAL_VER_STEP(v)  ((v) & 0xffffu)

/* Plausibility window used by the POCO X5 Pro port, hakios.thermal.c:15-16. */
enum {
	PONG_THERMAL_MIN_MILLI_C = -40000,
	PONG_THERMAL_MAX_MILLI_C = 160000
};

enum {
	PONG_THERMAL_OK = 0,
	PONG_THERMAL_NO_VALID = -1,
	PONG_THERMAL_BAD_ARG = -2,
	PONG_THERMAL_OUT_OF_RANGE = -3
};

struct pong_thermal_reading {
	int32_t milli_c;   /* meaningful only when valid != 0 */
	uint32_t flags;    /* bits 0..4: min, lower, upper, critical, max */
	int valid;
};

struct pong_thermal_sensor {
	uint8_t controller;  /* 0 = 0xc263000, 1 = 0xc265000 */
	uint8_t index;       /* 0..15, the DT thermal-sensor-cells argument */
	uint8_t zone;        /* live Android thermal_zone id, cross-check only */
	uint8_t domain;      /* PONG_THERMAL_DOMAIN_* */
	const char *name;    /* DT thermal-zone name */
};

/* tsens.c:346-347: the v2 status word already holds deci-Celsius, so the value is
 * sign_extend32(temp, 12) * 100 and no calibration slope/offset is applied. */
static inline int32_t
pong_thermal_status_to_mc(uint32_t status)
{
	int32_t raw = (int32_t)(status & PONG_THERMAL_STATUS_TEMP_MASK);

	raw = (raw << 20) >> 20;   /* sign-extend the 12-bit field */
	return raw * 100;
}

static inline uint32_t
pong_thermal_status_flags(uint32_t status)
{
	return (status & PONG_THERMAL_STATUS_FLAG_MASK) >> PONG_THERMAL_STATUS_FLAG_SHIFT;
}

static inline int
pong_thermal_decode(uint32_t status, struct pong_thermal_reading *out)
{
	int32_t mc;

	if (out == 0) {
		return PONG_THERMAL_BAD_ARG;
	}
	out->milli_c = 0;
	out->flags = pong_thermal_status_flags(status);
	out->valid = 0;
	if ((status & PONG_THERMAL_STATUS_VALID) == 0) {
		return PONG_THERMAL_NO_VALID;
	}
	mc = pong_thermal_status_to_mc(status);
	if (mc < PONG_THERMAL_MIN_MILLI_C || mc > PONG_THERMAL_MAX_MILLI_C) {
		return PONG_THERMAL_OUT_OF_RANGE;
	}
	out->milli_c = mc;
	out->valid = 1;
	return PONG_THERMAL_OK;
}

/* tsens-v2.c:60: TSENS_EN is SROT_CTRL[0]. Read only. */
static inline int
pong_thermal_ctrl_enabled(uint32_t ctrl)
{
	return (ctrl & 1u) != 0;
}

/* Zone order is the DT order: tsens0 index 0..15 = zones 24..39, then tsens1. */
static const struct pong_thermal_sensor pong_thermal_sensors[PONG_THERMAL_SENSOR_COUNT] = {
	{ 0,  0, 24, PONG_THERMAL_DOMAIN_NONE,   "aoss-0"   },
	{ 0,  1, 25, PONG_THERMAL_DOMAIN_NONE,   "cpuss-0"  },
	{ 0,  2, 26, PONG_THERMAL_DOMAIN_NONE,   "cpuss-1"  },
	{ 0,  3, 27, PONG_THERMAL_DOMAIN_NONE,   "cpuss-2"  },
	{ 0,  4, 28, PONG_THERMAL_DOMAIN_NONE,   "cpuss-3"  },
	{ 0,  5, 29, PONG_THERMAL_DOMAIN_BIG,    "cpu-1-0"  },
	{ 0,  6, 30, PONG_THERMAL_DOMAIN_BIG,    "cpu-1-1"  },
	{ 0,  7, 31, PONG_THERMAL_DOMAIN_BIG,    "cpu-1-2"  },
	{ 0,  8, 32, PONG_THERMAL_DOMAIN_BIG,    "cpu-1-3"  },
	{ 0,  9, 33, PONG_THERMAL_DOMAIN_BIG,    "cpu-1-4"  },
	{ 0, 10, 34, PONG_THERMAL_DOMAIN_BIG,    "cpu-1-5"  },
	{ 0, 11, 35, PONG_THERMAL_DOMAIN_BIG,    "cpu-1-6"  },
	{ 0, 12, 36, PONG_THERMAL_DOMAIN_BIG,    "cpu-1-7"  },
	{ 0, 13, 37, PONG_THERMAL_DOMAIN_BIG,    "cpu-1-8"  },
	{ 0, 14, 38, PONG_THERMAL_DOMAIN_GPU,    "gpuss-0"  },
	{ 0, 15, 39, PONG_THERMAL_DOMAIN_GPU,    "gpuss-1"  },
	{ 1,  0, 40, PONG_THERMAL_DOMAIN_NONE,   "aoss-1"   },
	{ 1,  1, 41, PONG_THERMAL_DOMAIN_LITTLE, "cpu-0-0"  },
	{ 1,  2, 42, PONG_THERMAL_DOMAIN_LITTLE, "cpu-0-1"  },
	{ 1,  3, 43, PONG_THERMAL_DOMAIN_LITTLE, "cpu-0-2"  },
	{ 1,  4, 44, PONG_THERMAL_DOMAIN_LITTLE, "cpu-0-3"  },
	{ 1,  5, 45, PONG_THERMAL_DOMAIN_NPU,    "nspss-0"  },
	{ 1,  6, 46, PONG_THERMAL_DOMAIN_NPU,    "nspss-1"  },
	{ 1,  7, 47, PONG_THERMAL_DOMAIN_NPU,    "nspss-2"  },
	{ 1,  8, 48, PONG_THERMAL_DOMAIN_NONE,   "video"    },
	{ 1,  9, 49, PONG_THERMAL_DOMAIN_DDR,    "ddr"      },
	{ 1, 10, 50, PONG_THERMAL_DOMAIN_NONE,   "mdmss-0"  },
	{ 1, 11, 51, PONG_THERMAL_DOMAIN_NONE,   "mdmss-1"  },
	{ 1, 12, 52, PONG_THERMAL_DOMAIN_NONE,   "mdmss-2"  },
	{ 1, 13, 53, PONG_THERMAL_DOMAIN_NONE,   "mdmss-3"  },
	{ 1, 14, 54, PONG_THERMAL_DOMAIN_NONE,   "camera-0" },
	{ 1, 15, 55, PONG_THERMAL_DOMAIN_NONE,   "camera-1" },
};

static inline const struct pong_thermal_sensor *
pong_thermal_sensor_at(unsigned slot)
{
	if (slot >= PONG_THERMAL_SENSOR_COUNT) {
		return 0;
	}
	return &pong_thermal_sensors[slot];
}

/* Hottest reading per domain; domains without a valid sensor keep INT32_MIN. */
static inline void
pong_thermal_domain_max(const int32_t milli_c[PONG_THERMAL_SENSOR_COUNT],
    int32_t out[PONG_THERMAL_DOMAINS])
{
	unsigned d, slot;

	for (d = 0; d < PONG_THERMAL_DOMAINS; d++) {
		out[d] = INT32_MIN;
	}
	for (slot = 0; slot < PONG_THERMAL_SENSOR_COUNT; slot++) {
		unsigned domain = pong_thermal_sensors[slot].domain;

		if (domain >= PONG_THERMAL_DOMAINS) {
			continue;
		}
		if (milli_c[slot] > out[domain]) {
			out[domain] = milli_c[slot];
		}
	}
}

#endif /* _SYS_PONG_THERMAL_H_ */
