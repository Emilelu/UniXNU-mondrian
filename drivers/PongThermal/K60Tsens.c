/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* Adapted from mainline Linux drivers/thermal/qcom/tsens.c (tsens_hw_to_mC,
 * tsens.c:318-348) and drivers/thermal/qcom/tsens-v2.c (register map and fields).
 * Read-only: see K60Tsens.h. */
#include "K60Tsens.h"

/* tsens.c:346-347: for adc=0 hardware the status word already holds deci-Celsius,
 * so the conversion is sign_extend32(temp, resolution) * 100 and no calibration
 * slope/offset is applied. resolution = 12 (tsens-v2.c:94-101). */
int32_t k60tsens_status_to_mc(uint32_t status)
{
    int32_t raw = (int32_t)((status & K60TSENS_STATUS_TEMP_MASK) >> K60TSENS_STATUS_TEMP_SHIFT);
    /* sign-extend the 12-bit field (tsens.c:318-348) */
    raw = (raw << 20) >> 20;
    return raw * 100;
}

uint32_t k60tsens_status_flags(uint32_t status)
{
    return (status & K60TSENS_STATUS_FLAG_MASK) >> K60TSENS_STATUS_FLAG_SHIFT;
}

int k60tsens_decode(uint32_t status, K60TsensReading *out)
{
    int32_t mc;

    if (out == 0) {
        return K60TsensBadArg;
    }
    out->milli_c = 0;
    out->flags = k60tsens_status_flags(status);
    out->valid = 0;

    /* tsens-v2.c:101 - bit 21 says the last conversion is complete and usable. */
    if ((status & K60TSENS_STATUS_VALID) == 0) {
        return K60TsensNoValid;
    }
    mc = k60tsens_status_to_mc(status);
    if (mc < K60TsensMinMilliC || mc > K60TsensMaxMilliC) {
        return K60TsensOutOfRange;
    }
    out->milli_c = mc;
    out->valid = 1;
    return K60TsensOk;
}

int k60tsens_decode_hw_ver(uint32_t ver, uint32_t *major, uint32_t *minor, uint32_t *step)
{
    if (major == 0 || minor == 0 || step == 0) {
        return K60TsensBadArg;
    }
    *major = K60TSENS_VER_MAJOR(ver);
    *minor = K60TSENS_VER_MINOR(ver);
    *step = K60TSENS_VER_STEP(ver);
    return K60TsensOk;
}

int k60tsens_ctrl_enabled(uint32_t ctrl)
{
    /* tsens-v2.c:60 - TSENS_EN is SROT_CTRL[0]. Read only; the driver must never
     * set it (tsens.c:970-979 only writes it for the pre-v2 VER_0 hardware). */
    return (ctrl & 1u) != 0;
}

int k60tsens_read(const volatile uint32_t *tm, uint32_t sensor, K60TsensReading *out)
{
    uint32_t status;

    if (tm == 0 || out == 0 || sensor >= K60TsensSensorsPerController) {
        return K60TsensBadArg;
    }
    /* byte offset 0xa0 + 4n, expressed as a word index into the TM window. */
    status = tm[K60TSENS_TM_SN_STATUS(sensor) / 4u];
    return k60tsens_decode(status, out);
}

int k60tsens_read_controller(const volatile uint32_t *tm,
                             K60TsensReading out[K60TsensSensorsPerController])
{
    int valid = 0;
    uint32_t s;

    if (tm == 0 || out == 0) {
        return K60TsensBadArg;
    }
    for (s = 0; s < K60TsensSensorsPerController; s++) {
        if (k60tsens_read(tm, s, &out[s]) == K60TsensOk) {
            valid++;
        }
    }
    return valid;
}

int k60tsens_trdy(const volatile uint32_t *tm)
{
    if (tm == 0) {
        return K60TsensBadArg;
    }
    /* tsens-v2.c:104 - TM_TRDY bit 0 means the last measurement is done. */
    return (tm[K60TSENS_TM_TRDY / 4u] & 1u) != 0;
}

/* Order taken from the DT: /soc/thermal-zones zones that point at phandle 0x5d
 * (tsens0) then 0x6b (tsens1), each with its thermal-sensor-cells index. The zone
 * numbers are the live Android thermal_zone ids, which happen to be 24..55. */
static const K60TsensSensor k60TsensTable[K60TsensSensorCount] = {
    { 0,  0, 24, "aoss-0"   }, { 0,  1, 25, "cpuss-0"  },
    { 0,  2, 26, "cpuss-1"  }, { 0,  3, 27, "cpuss-2"  },
    { 0,  4, 28, "cpuss-3"  }, { 0,  5, 29, "cpu-1-0"  },
    { 0,  6, 30, "cpu-1-1"  }, { 0,  7, 31, "cpu-1-2"  },
    { 0,  8, 32, "cpu-1-3"  }, { 0,  9, 33, "cpu-1-4"  },
    { 0, 10, 34, "cpu-1-5"  }, { 0, 11, 35, "cpu-1-6"  },
    { 0, 12, 36, "cpu-1-7"  }, { 0, 13, 37, "cpu-1-8"  },
    { 0, 14, 38, "gpuss-0"  }, { 0, 15, 39, "gpuss-1"  },
    { 1,  0, 40, "aoss-1"   }, { 1,  1, 41, "cpu-0-0"  },
    { 1,  2, 42, "cpu-0-1"  }, { 1,  3, 43, "cpu-0-2"  },
    { 1,  4, 44, "cpu-0-3"  }, { 1,  5, 45, "nspss-0"  },
    { 1,  6, 46, "nspss-1"  }, { 1,  7, 47, "nspss-2"  },
    { 1,  8, 48, "video"    }, { 1,  9, 49, "ddr"      },
    { 1, 10, 50, "mdmss-0"  }, { 1, 11, 51, "mdmss-1"  },
    { 1, 12, 52, "mdmss-2"  }, { 1, 13, 53, "mdmss-3"  },
    { 1, 14, 54, "camera-0" }, { 1, 15, 55, "camera-1" },
};

const K60TsensSensor *k60tsens_sensor_table(uint32_t *count)
{
    if (count != 0) {
        *count = K60TsensSensorCount;
    }
    return k60TsensTable;
}

const char *k60tsens_sensor_name(uint32_t controller, uint32_t index)
{
    uint32_t i;

    for (i = 0; i < K60TsensSensorCount; i++) {
        if (k60TsensTable[i].controller == controller && k60TsensTable[i].index == index) {
            return k60TsensTable[i].name;
        }
    }
    return 0;
}
