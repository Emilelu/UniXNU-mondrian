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
#define K60_CPU_FREQ_STATES 4u
#define K60_CPU_FREQ_LUT_ROWS 40u
#define K60_CPU_FREQ_XO_KHZ 19200u        /* bi_tcxo_div2 */
#define K60_CPU_FREQ_GPLL_HALF_KHZ 300000u /* GPLL0 600 MHz / CLK_HW_DIV 2 */
#define K60_CPU_FREQ_HISPEED 900u          /* busy per mille: jump to the top */
#define K60_CPU_FREQ_MARGIN 125u           /* percent over the busy estimate */
#define K60_CPU_FREQ_DOWN_WINDOWS 4u       /* windows before a lower level lands */
/* A window counts as quiet below this busy share (per mille), matching the
 * reference's busy < 100 test. The shared-cluster floor is released after
 * K60_CPU_FREQ_QUIET_WINDOWS consecutive quiet windows and must not be
 * re-armed by the down-steps that release takes. */
#define K60_CPU_FREQ_QUIET_BUSY 100u
#define K60_CPU_FREQ_QUIET_WINDOWS 12u     /* shared clusters stay high this long */
#define K60_CPU_FREQ_FRAME_PCT 60u         /* frame floor, percent of the top */

/* EPSS register offsets inside one 0x1000 domain window. */
#define K60_CPU_FREQ_REG_ENABLE 0x00u
#define K60_CPU_FREQ_REG_DOMAIN_STATE 0x20u
#define K60_CPU_FREQ_REG_DCVS_CTRL 0xb0u
#define K60_CPU_FREQ_REG_FREQ_LUT 0x100u
#define K60_CPU_FREQ_REG_PERF_STATE 0x320u
#define K60_CPU_FREQ_REG_L3_VOTE 0x90u

/* PDMEM perf-lock votes. The live K60 device tree lists the three domains as
 * 0x17d09804/0x17d09808/0x17d0980c with qcom,perf-lock-support, inside the
 * 0x17d09000 page. The t970 and zizhan SM8475 policies write this vote before
 * the perf-state row; a bare perf-state write is ignored by the shared
 * clusters. The offset is relative to the PDMEM page, not the domain window. */
#define K60_CPU_FREQ_PDMEM_BASE 0x17d09000ull
#define K60_CPU_FREQ_PDMEM_VOTE_OFFSET 0x804u

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

/* Lowest entry. Used by the down-only first write test: lowering a level never
 * needs a voltage raise, so it is the safe direction before the rail/thermal
 * ordering exists. Returns 0 on success. */
int k60_cpufreq_pick_lowest(const K60CpuFreqTable *table, unsigned *index,
    uint32_t *khz);

/* Lowest entry whose frequency is at least khz. Returns 0 on success and -1
 * when the table is empty or every entry is below khz. */
int k60_cpufreq_pick_at_least(const K60CpuFreqTable *table, uint32_t khz,
    unsigned *index, uint32_t *out);

/* L3 follow target from the same-SoC reference policy: take the largest domain
 * share (current / top, in millionths) and place L3 at the lowest level at or
 * above that share of the L3 top. boost selects the top row. Returns 0 on
 * success, -1 for a missing table or when no domain has a valid top/current
 * pair. */
int k60_cpufreq_l3_target(const K60CpuFreqTable *l3,
    const uint32_t *domain_khz, const uint32_t *domain_top, unsigned boost,
    unsigned *index, uint32_t *khz);

/* One governor window. busy_permille is the busiest CPU of the domain;
 * boost pins the top for every domain (touch hold). shared_cluster is 0 for
 * the boot cluster (domain 0) and 1 for the others,
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

/* Scheduler idle accounting for one window: idle_delta and elapsed are in the
 * same tick unit. Mirrors the reference (CpuFreqProbe.cpp): a CPU that logged
 * at least the whole window idle contributes 0, otherwise the busy share is
 * (elapsed - idle) * 1000 / elapsed. A zero window or an over-counted idle
 * delta also yields 0; the result is clamped to 1000. */
unsigned k60_cpufreq_busy_permille(uint64_t idle_delta, uint64_t elapsed);

/* Busiest CPU of one domain, 0 for a bad domain/null/count outside 1..8. This
 * is the value the governor window wants: the reference takes the maximum over
 * the domain's CPUs, not the average. */
unsigned k60_cpufreq_domain_busy(const uint64_t *idle_delta, unsigned count,
    uint64_t elapsed, unsigned domain);

/* Per-CPU window form of the same maximum. elapsed differs per CPU because
 * ticks only advance while that CPU accounts time, so each CPU is divided by
 * its own window. Returns 0 for a bad domain/null/count outside 1..8. */
unsigned k60_cpufreq_domain_busy_elapsed(const uint64_t *idle_delta,
    const uint64_t *elapsed, unsigned count, unsigned domain);

/* Decode two cumulative CPU_STATE_* snapshots into one window. Ticks are
 * 32-bit and wrap; every delta is taken modulo 2^32. idle receives the IDLE
 * delta and elapsed the sum of all four states. Returns 0 on success, -1 for a
 * null pointer or an empty window. The state order matches XNU's
 * processor_cpu_load_info: user, system, idle, nice. */
#define K60_CPU_FREQ_STATE_IDLE 2u
int k60_cpufreq_tick_delta(const uint32_t previous[4], const uint32_t current[4],
    uint64_t *idle, uint64_t *elapsed);

/* The write set the reference uses to place one domain at a level: the
 * perf_state row always, plus one row per extra core when the dcvs control
 * bit is set. "level" is the LUT row index, not the table index.
 * k60_cpufreq_build_votes returns the number of writes, or 0 when the caller's
 * buffer is too small (nothing is written in that case). */
#define K60_CPU_FREQ_MAX_WRITES 8u
typedef struct {
    uint32_t offset; /* register offset inside the domain window */
    uint32_t value;
} K60CpuFreqWrite;

unsigned k60_cpufreq_build_votes(unsigned domain, unsigned dcvs_ctrl, unsigned level,
    K60CpuFreqWrite *out, unsigned capacity);
unsigned k60_cpufreq_build_l3_vote(unsigned level, K60CpuFreqWrite *out, unsigned capacity);

/* PDMEM perf-lock write for one domain. Returns the offset inside the PDMEM
 * page (0x804 + 4 * domain), or 0 for a bad domain. */
unsigned k60_cpufreq_pdmem_offset(unsigned domain);

/* Build the one-entry PDMEM vote. Returns 1, or 0 for a bad domain/level or a
 * missing output buffer. level is a hardware LUT row index, as with votes. */
unsigned k60_cpufreq_build_pdmem_vote(unsigned domain, unsigned level,
    K60CpuFreqWrite *out, unsigned capacity);

/* Safety guard for a write set: the domain must be enabled, the level must be
 * one of the table's hardware rows, and the write count must fit. The probe
 * refuses a vote when this returns 0 instead of writing a disabled domain or
 * an unlisted level. */
int k60_cpufreq_vote_allowed(unsigned enable, const K60CpuFreqTable *table,
    unsigned level, unsigned writes);

/* Read back one value per write, in the same order. Returns 1 only when every
 * value equals the requested one. */
int k60_cpufreq_check_readback(const K60CpuFreqWrite *writes,
    const uint32_t *readback, unsigned count);

/* Build the undo set for a vote from the values read before the write. The
 * offsets are copied and the values come from original[]. Returns the number
 * of writes, or 0 when the buffer is too small or an argument is bad. */
unsigned k60_cpufreq_build_restore(const K60CpuFreqWrite *writes,
    const uint32_t *original, unsigned count, K60CpuFreqWrite *out,
    unsigned capacity);

/* Per-domain governor state for the reference's 16 ms window loop. Keeping the
 * state here, instead of in the probe, lets the host test drive a whole
 * sequence of windows without any kernel timer or idle counter. */
typedef struct {
    unsigned current[K60_CPU_FREQ_DOMAINS];
    unsigned down[K60_CPU_FREQ_DOMAINS];
    unsigned quiet[K60_CPU_FREQ_DOMAINS];
} K60CpuFreqGovernor;

void k60_cpufreq_governor_reset(K60CpuFreqGovernor *gov, unsigned level);

/* One 16 ms window for one domain. busy_permille is the busiest CPU of the
 * domain; boost is the touch boost, framing the frame-floor request. Returns 1
 * when the level changed, 0 when it did not, and -1 for a bad argument. */
int k60_cpufreq_governor_window(K60CpuFreqGovernor *gov, const K60CpuFreqTable *table,
    unsigned domain, unsigned busy_permille, unsigned boost, unsigned framing);

#ifdef __cplusplus
}
#endif
#endif
