/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* Adapted from mainline Linux drivers/thermal/qcom/tsens-v2.c and tsens.c (v6.6).
 * Read-only by construction: nothing here writes a register, enables an interrupt,
 * or touches the SROT block. The caller maps the TM window and passes it in, so the
 * whole file builds and unit-tests on the host. */
#ifndef K60_TSENS_H
#define K60_TSENS_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

/* Board constants, all from the board DTB (/soc/thermal-sensor@c263000 and @c265000,
 * #qcom,sensors = <0x10>): docs/research/thermal/01-SAME-HARDWARE.md. */
enum { K60TsensControllers = 2,
       K60TsensSensorsPerController = 16,
       K60TsensSensorCount = 32 };

/* TM block offsets, tsens-v2.c:12-27. SROT offsets are listed only so that a later
 * bring-up can *read* TSENS_EN/HW_VER; this driver never writes them. */
#define K60TSENS_TM_SN_STATUS(n) (0x0a0u + 4u * (uint32_t)(n)) /* tsens-v2.c:25 */
#define K60TSENS_TM_TRDY         0x0e4u                         /* tsens-v2.c:26 */
#define K60TSENS_SROT_HW_VER     0x000u                         /* tsens-v2.c:12 */
#define K60TSENS_SROT_CTRL       0x004u                         /* tsens-v2.c:13 */

/* TM_Sn_STATUS fields, tsens-v2.c:94-101. */
#define K60TSENS_STATUS_TEMP_MASK  0x00000fffu
#define K60TSENS_STATUS_TEMP_SHIFT 0
#define K60TSENS_STATUS_MIN        (1u << 16)
#define K60TSENS_STATUS_LOWER      (1u << 17)
#define K60TSENS_STATUS_UPPER      (1u << 18)
#define K60TSENS_STATUS_CRITICAL   (1u << 19)
#define K60TSENS_STATUS_MAX        (1u << 20)
#define K60TSENS_STATUS_VALID      (1u << 21)
#define K60TSENS_STATUS_FLAG_SHIFT 16
#define K60TSENS_STATUS_FLAG_MASK  0x001f0000u

/* SROT_HW_VER fields, tsens-v2.c:56-58. */
#define K60TSENS_VER_MAJOR(v) (((v) >> 28) & 0x0fu)
#define K60TSENS_VER_MINOR(v) (((v) >> 16) & 0x0fffu)
#define K60TSENS_VER_STEP(v)  ((v) & 0xffffu)

/* Plausibility window used by the POCO X5 Pro port, hakios.thermal.c:15-16.
 * Outside it the status word is treated as garbage rather than reported. */
enum { K60TsensMinMilliC = -40000, K60TsensMaxMilliC = 160000 };

enum { K60TsensOk = 0, K60TsensNoValid = -1, K60TsensBadArg = -2,
       K60TsensOutOfRange = -3 };

typedef struct {
    int32_t  milli_c;   /* only meaningful when valid != 0 */
    uint32_t flags;     /* bits 0..4 = min, lower, upper, critical, max */
    int      valid;
} K60TsensReading;

typedef struct {
    uint8_t     controller;  /* 0 = 0xc263000 (tsens0), 1 = 0xc265000 (tsens1) */
    uint8_t     index;       /* 0..15, the DT thermal-sensor-cells argument */
    uint8_t     zone;        /* live Android thermal_zone number, cross-check only */
    const char *name;        /* DT thermal-zone name */
} K60TsensSensor;

/* Pure decoders: no MMIO, fully unit-tested on the host. */
int32_t  k60tsens_status_to_mc(uint32_t status);
uint32_t k60tsens_status_flags(uint32_t status);
int      k60tsens_decode(uint32_t status, K60TsensReading *out);
int      k60tsens_decode_hw_ver(uint32_t ver, uint32_t *major, uint32_t *minor, uint32_t *step);
int      k60tsens_ctrl_enabled(uint32_t ctrl);

/* MMIO readers. tm points at the TM window (0x1ff bytes, DT reg[0]); the caller owns
 * the mapping. Every access is a single 32-bit volatile load. */
int k60tsens_read(const volatile uint32_t *tm, uint32_t sensor, K60TsensReading *out);
int k60tsens_read_controller(const volatile uint32_t *tm,
                             K60TsensReading out[K60TsensSensorsPerController]);
int k60tsens_trdy(const volatile uint32_t *tm);

/* Board sensor table, generated from the DT (see docs/research/thermal/01 §5.1). */
const K60TsensSensor *k60tsens_sensor_table(uint32_t *count);
const char *k60tsens_sensor_name(uint32_t controller, uint32_t index);

#ifdef __cplusplus
}
#endif
#endif /* K60_TSENS_H */
