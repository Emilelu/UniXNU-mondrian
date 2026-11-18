/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/*
 * Pure CPU-frequency planning for the K60 EPSS block: decode the hardware
 * look-up table, pick a level under a cap, and run the reference governor's
 * per-window decision. No MMIO and no IOKit here, so the host test can pin
 * every number; drivers/PongPower/K60CpuFreqProbe.cpp owns the registers.
 *
 * Register facts come from the live K60 device tree
 * (E:/k60-work/reports/live-6033dbec-fdt.dtb, decompiled 2026-11-18):
 *   /soc/qcom,cpufreq-hw-epss  reg 0x17d91000/0x17d92000/0x17d93000, 0x1000 each,
 *                             qcom,lut-row-size = 4, qcom,skip-enable-check;
 *   /soc/dcvs ... dcvs-hw-type 2, reg 0x17d90000 (0x4000) + 0x17d90100 (0xa0),
 *                             qcom,shared-offset = 0x90 for the L3 vote.
 * The same windows and the 19.2 MHz/GPLL0-half LUT arithmetic are used by the
 * SM8550 reference (UniXNU-sheng package/CpuFreqProbe.cpp), which is why this
 * file can be written before the K60 block is ever read.
 */
#ifndef K60_CPU_FREQ_PLAN_H
#define K60_CPU_FREQ_PLAN_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

#define K60_CPU_FREQ_DOMAINS 3u
#define K60_CPU_FREQ_CPUS 8u
#define K60_CPU_FREQ_LUT_ROWS 40u
#define K60_CPU_FREQ_XO_KHZ 19200u        /* bi_tcxo_div2 */
#define K60_CPU_FREQ_GPLL_HALF_KHZ 300000u /* GPLL0 600 MHz / CLK_HW_DIV 2 */
#define K60_CPU_FREQ_HISPEED 900u          /* busy per mille: jump to the top */
#define K60_CPU_FREQ_MARGIN 125u           /* percent over the busy estimate */
#define K60_CPU_FREQ_DOWN_WINDOWS 4u       /* windows before a lower level lands */
#define K60_CPU_FREQ_QUIET_WINDOWS 12u     /* shared clusters stay high this long */
#define K60_CPU_FREQ_FRAME_PCT 60u         /* frame floor, percent of the top */

/* EPSS register offsets inside one 0x1000 domain window. */
#define K60_CPU_FREQ_REG_ENABLE 0x00u
#define K60_CPU_FREQ_REG_DOMAIN_STATE 0x20u
#define K60_CPU_FREQ_REG_DCVS_CTRL 0xb0u
#define K60_CPU_FREQ_REG_FREQ_LUT 0x100u
#define K60_CPU_FREQ_REG_PERF_STATE 0x320u
#define K60_CPU_FREQ_REG_L3_VOTE 0x90u

typedef struct {
    uint32_t khz[K60_CPU_FREQ_LUT_ROWS]; /* ascending, turbo rows removed */
    uint8_t level[K60_CPU_FREQ_LUT_ROWS]; /* LUT row each frequency came from */
    unsigned count;
} K60CpuFreqTable;

/* LUT row: bits 31:30 source, 18:16 core count (1 = turbo), 7:0 L value.
 * Source 0 runs at GPLL0/2; any other source counts 19.2 MHz steps of L. */
uint32_t k60_cpufreq_row_khz(uint32_t row);
unsigned k60_cpufreq_row_cores(uint32_t row);
unsigned k60_cpufreq_row_turbo(uint32_t row);

/* Build the ascending non-turbo table used for voting. Reading stops at the
 * first repeated frequency, because the hardware ends the table with two
 * equal rows. cap_khz 0 means no cap. Returns 0 when at least one entry was
 * kept, -1 for a null/empty input or an all-turbo/over-cap table. */
int k60_cpufreq_build_table(const uint32_t *rows, unsigned row_count, uint32_t cap_khz,
    K60CpuFreqTable *out);

/* Highest entry at or below cap_khz (0 = none). Returns 0 on success. */
int k60_cpufreq_pick_highest(const K60CpuFreqTable *table, uint32_t cap_khz,
    unsigned *index, uint32_t *khz);

/* One governor window. busy_permille is the busiest CPU of the domain;
 * shared_cluster is 0 for the boot cluster (domain 0) and 1 for the others,
 * matching the reference where only shared clusters get the boost/quiet
 * floor. framing and boost are the caller's current flags. */
unsigned k60_cpufreq_target(const K60CpuFreqTable *table, unsigned current,
    unsigned busy_permille, unsigned shared_cluster, unsigned boost,
    unsigned framing, unsigned quiet_windows);

/* Apply a target with the reference down-delay latch. *down must persist
 * between windows. Returns 1 when *current changed. */
unsigned k60_cpufreq_step(const K60CpuFreqTable *table, unsigned *current,
    unsigned want, unsigned *down);

/* CPU to domain map measured from the live K60 device tree: cpus 0-3 are the
 * four little cores (domain 0), cpus 4-6 the three big cores (domain 1), cpu 7
 * the prime core (domain 2). The SM8550 reference splits 3/4/1 instead, so the
 * per-core perf_state rows and the quiet logic must not be copied as-is. */
unsigned k60_cpufreq_domain_of_cpu(unsigned cpu);
unsigned k60_cpufreq_domain_cores(unsigned domain);

#ifdef __cplusplus
}
#endif
#endif
