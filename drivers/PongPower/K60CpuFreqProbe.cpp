/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/*
 * EPSS probe and level vote for the K60. The read-only mode answers what the
 * CPU-frequency block contains before anything votes: per domain the enable
 * bit, the current domain-state level, the APSS perf-state vote and the
 * decoded look-up table, and the same for L3. The vote modes place one level
 * through the write set the reference uses (perf_state row, plus one row per
 * extra core when dcvs control is on, and the L3 shared vote).
 *
 * Off by default, and never automatic: boot argument k60_cpufreq selects the
 * mode. 1 is read-only, 2 votes domain 0 to its highest non-turbo level, 3
 * votes every domain and L3, 5 samples idle time read-only, 6 votes domain 0
 * down to its lowest level, 7 runs the idle sampler and applies the governor's
 * down steps inside a bounded window, then restores the original votes, and 8
 * does the same in both directions. Mode 9 (dcvs control bit plus every core
 * row) is disabled: both images that carried it, one with the thermal patch
 * and one without, hung before the console appeared, so the probe is the
 * common factor and must not run again without new firmware evidence.
 * Touch and frame activity re-arm a short window (1 s and 300 ms) so the
 * section 5 :115-:116 holds can reach the registers after boot.
 * Raises are safe to place because the EPSS
 * firmware owns the CPU rail and performs the voltage transition itself: the
 * reference CpuFreqProbe.cpp, the file the official page points at for the
 * work-point access, writes the same perf-state rows for raises and never
 * calls a regulator (package/CpuFreqProbe.cpp:198-203, 293-296), and the
 * read-only runs already saw EPSS move d2 to 2.9952 GHz on its own. Mode 6
 * was the first step because it needed no such argument. Any other value is
 * logged and ignored so a typo cannot
 * start a path that has never been measured. This runs from
 * k60_physical_battery_start(), which is the only userland-triggered IOKit
 * entry the archive owns today; it does not need the ADSP handoff lease.
 */
#include <IOKit/IOLib.h>
#include <IOKit/IOMemoryDescriptor.h>
#include <IOKit/IODeviceMemory.h>
#include <pexpert/pexpert.h>
#include <kern/processor.h>
#include <kern/thread.h>
#include <mach/processor_info.h>
#include "K60CpuFreqPlan.h"
#include "K60BoostPlan.h"

/* The SDK header hides the array behind KERNEL_PRIVATE, but the kernel exports
 * it and processor_info() needs the processor_t. The declared extent only has
 * to cover the eight CPUs this board has. */
extern "C" processor_t processor_array[64];

/* The CP ring read lives in the Adreno code, but the image links both objects
 * into the kernel: llvm-nm -g on kernel.macho shows _pong_adreno_cp_pending as
 * a defined global next to _k60_physical_battery_start, so this direct call is
 * resolved at kernel link and needs no exported trampoline. -1 means the CP is
 * not running yet, which counts as "no submission". */
extern "C" int pong_adreno_cp_pending(void);

/* Official section 5 :115: touch holds the performance cluster at its top
 * level for 1 s after the last report. Patch 0622 exports the kernel touch
 * queue counter; a changed count is one report, and the boost plan owns the
 * 1 s window. */
extern "C" uint32_t pong_touch_report_count(void);

namespace {

constexpr uint64_t kDomainBase[K60_CPU_FREQ_DOMAINS] = {0x17d91000, 0x17d92000, 0x17d93000};
constexpr uint64_t kL3Base = 0x17d90000;
constexpr uint64_t kPdmemBase = K60_CPU_FREQ_PDMEM_BASE;
constexpr uint32_t kDomainWindow = 0x1000;
constexpr uint32_t kL3Window = 0x4000;
constexpr uint32_t kPdmemWindow = 0x1000;
constexpr unsigned kLutRows = K60_CPU_FREQ_LUT_ROWS;

struct Window {
    IOMemoryMap *map;
    uintptr_t va;
};

uint32_t rd32(uintptr_t base, uint32_t reg)
{
    return *reinterpret_cast<volatile uint32_t *>(base + reg);
}

void wr32(uintptr_t base, uint32_t reg, uint32_t value)
{
    *reinterpret_cast<volatile uint32_t *>(base + reg) = value;
}

/* The reference policies write PDMEM first and order both writes before the
 * next read. Without this barrier the perf-state row can become visible while
 * the perf-lock vote is still in flight. */
void barrier()
{
    __asm__ volatile("dsb oshst" ::: "memory");
}

bool mapWindow(Window *window, uint64_t base, uint32_t bytes)
{
    IODeviceMemory *memory = IODeviceMemory::withRange(base, bytes);
    window->map = memory ? memory->map(kIOMapAnywhere | kIOMapInhibitCache) : nullptr;
    if (memory) memory->release();
    window->va = window->map ? static_cast<uintptr_t>(window->map->getVirtualAddress()) : 0;
    return window->va != 0;
}

void unmapWindow(Window *window)
{
    if (window->map) window->map->release();
    window->map = nullptr;
    window->va = 0;
}

void readRows(Window *window, uint32_t *rows)
{
    for (unsigned i = 0; i < kLutRows; ++i)
        rows[i] = rd32(window->va, K60_CPU_FREQ_REG_FREQ_LUT + i * 4);
}

bool readTable(Window *window, K60CpuFreqTable *table)
{
    uint32_t rows[kLutRows];

    readRows(window, rows);
    return k60_cpufreq_build_table(rows, kLutRows, 0, table) == 0;
}

void dumpRows(const char *tag, const uint32_t *rows, unsigned count)
{
    for (unsigned i = 0; i < count && i < kLutRows; ++i) {
        IOLog("K60CpuFreq: %srow=%u raw=0x%08x khz=%u cores=%u turbo=%u\n",
            tag, i, rows[i], k60_cpufreq_row_khz(rows[i]),
            k60_cpufreq_row_cores(rows[i]), k60_cpufreq_row_turbo(rows[i]));
    }
}

void probeDomain(unsigned domain, bool dump)
{
    Window window = {};
    Window pdmem = {};
    K60CpuFreqTable table = {};
    uint32_t rows[kLutRows] = {};
    unsigned index = 0, pdmemOffset = k60_cpufreq_pdmem_offset(domain);
    uint32_t topKhz = 0, stateKhz = 0, state, control, vote, pdmemVote = 0;

    if (!mapWindow(&window, kDomainBase[domain], kDomainWindow)) {
        IOLog("K60CpuFreq: d%u nomap base=0x%llx\n", domain,
            static_cast<unsigned long long>(kDomainBase[domain]));
        return;
    }
    state = rd32(window.va, K60_CPU_FREQ_REG_DOMAIN_STATE);
    control = rd32(window.va, K60_CPU_FREQ_REG_DCVS_CTRL);
    vote = rd32(window.va, K60_CPU_FREQ_REG_PERF_STATE) & 0xffu;
    if (state & 0xffu) stateKhz = (state & 0xffu) * K60_CPU_FREQ_XO_KHZ;
    if (readTable(&window, &table)) k60_cpufreq_pick_highest(&table, 0, &index, &topKhz);
    if (pdmemOffset && mapWindow(&pdmem, kPdmemBase, kPdmemWindow)) {
        pdmemVote = rd32(pdmem.va, pdmemOffset) & 0xffu;
        unmapWindow(&pdmem);
    }
    IOLog("K60CpuFreq: d%u base=0x%llx enable=%u state=%u (%ukHz) dcvs=%u vote=%u pdmem=%u rows=%u top=%ukHz level=%u mode1=read-only\n",
        domain, static_cast<unsigned long long>(kDomainBase[domain]),
        rd32(window.va, K60_CPU_FREQ_REG_ENABLE) & 1u, state & 0xffu, stateKhz,
        control & 1u, vote, pdmemVote, table.count, topKhz, index);
    if (dump && table.count) {
        readRows(&window, rows);
        dumpRows("", rows, table.count);
    }
    unmapWindow(&window);
}

void voteDomain(unsigned domain, unsigned mode, bool lowest)
{
    Window window = {};
    Window pdmem = {};
    K60CpuFreqTable table = {};
    K60CpuFreqWrite writes[K60_CPU_FREQ_MAX_WRITES] = {};
    K60CpuFreqWrite restore[K60_CPU_FREQ_MAX_WRITES] = {};
    uint32_t original[K60_CPU_FREQ_MAX_WRITES] = {};
    uint32_t readback[K60_CPU_FREQ_MAX_WRITES] = {};
    unsigned index = 0, n, i, enabled, dcvs, restored, pdmemOffset;
    unsigned stateBefore, stateAfter, stateRestored;
    uint32_t topKhz = 0, pdmemOriginal = 0, pdmemAfter = 0;
    bool pdmemMapped;
    int ok;

    if (!mapWindow(&window, kDomainBase[domain], kDomainWindow)) {
        IOLog("K60CpuFreq: d%u nomap base=0x%llx\n", domain,
            static_cast<unsigned long long>(kDomainBase[domain]));
        return;
    }
    enabled = rd32(window.va, K60_CPU_FREQ_REG_ENABLE) & 1u;
    dcvs = rd32(window.va, K60_CPU_FREQ_REG_DCVS_CTRL) & 1u;
    pdmemOffset = k60_cpufreq_pdmem_offset(domain);
    pdmemMapped = pdmemOffset && mapWindow(&pdmem, kPdmemBase, kPdmemWindow);
    if (pdmemMapped) pdmemOriginal = rd32(pdmem.va, pdmemOffset);
    if (!readTable(&window, &table)) {
        IOLog("K60CpuFreq: d%u vote skipped: no non-turbo table\n", domain);
        if (pdmemMapped) unmapWindow(&pdmem);
        unmapWindow(&window);
        return;
    }
    if (lowest) {
        if (k60_cpufreq_pick_lowest(&table, &index, &topKhz)) {
            IOLog("K60CpuFreq: d%u vote skipped: no non-turbo table\n", domain);
            if (pdmemMapped) unmapWindow(&pdmem);
            unmapWindow(&window);
            return;
        }
    } else if (k60_cpufreq_pick_highest(&table, 0, &index, &topKhz)) {
        IOLog("K60CpuFreq: d%u vote skipped: no non-turbo table\n", domain);
        if (pdmemMapped) unmapWindow(&pdmem);
        unmapWindow(&window);
        return;
    }
    n = k60_cpufreq_build_votes(domain, dcvs, table.level[index], writes,
        K60_CPU_FREQ_MAX_WRITES);
    if (!k60_cpufreq_vote_allowed(enabled, &table, table.level[index], n)) {
        IOLog("K60CpuFreq: mode%u d%u vote skipped: enable=%u table=%u level=%u writes=%u\n",
            mode, domain, enabled, table.count, table.level[index], n);
        if (pdmemMapped) unmapWindow(&pdmem);
        unmapWindow(&window);
        return;
    }
    for (i = 0; i < n; ++i) original[i] = rd32(window.va, writes[i].offset);
    stateBefore = rd32(window.va, K60_CPU_FREQ_REG_DOMAIN_STATE) & 0xffu;
    if (pdmemMapped) {
        K60CpuFreqWrite vote = {};
        if (k60_cpufreq_build_pdmem_vote(domain, table.level[index], &vote, 1) == 1)
            wr32(pdmem.va, vote.offset, vote.value);
    }
    for (i = 0; i < n; ++i) wr32(window.va, writes[i].offset, writes[i].value);
    barrier();
    for (i = 0; i < n; ++i) readback[i] = rd32(window.va, writes[i].offset);
    if (pdmemMapped) pdmemAfter = rd32(pdmem.va, pdmemOffset) & 0xffu;
    ok = k60_cpufreq_check_readback(writes, readback, n);
    IOSleep(20);
    stateAfter = rd32(window.va, K60_CPU_FREQ_REG_DOMAIN_STATE) & 0xffu;
    restored = k60_cpufreq_build_restore(writes, original, n, restore,
        K60_CPU_FREQ_MAX_WRITES);
    for (i = 0; i < restored; ++i) wr32(window.va, restore[i].offset, restore[i].value);
    if (pdmemMapped) wr32(pdmem.va, pdmemOffset, pdmemOriginal);
    barrier();
    IOSleep(20);
    stateRestored = rd32(window.va, K60_CPU_FREQ_REG_DOMAIN_STATE) & 0xffu;
    IOLog("K60CpuFreq: mode%u vote d%u level=%u (%ukHz) dcvs=%u writes=%u readback=%s restored=%u state=%u->%u->%u\n",
        mode, domain, table.level[index], topKhz, dcvs, n,
        ok ? "ok" : "mismatch", restored, stateBefore, stateAfter, stateRestored);
    if (pdmemMapped) {
        IOLog("K60CpuFreq: mode%u d%u pdmem=%u->%u->%u\n", mode, domain,
            pdmemOriginal & 0xffu, pdmemAfter, rd32(pdmem.va, pdmemOffset) & 0xffu);
        unmapWindow(&pdmem);
    } else {
        IOLog("K60CpuFreq: mode%u d%u pdmem=unmapped\n", mode, domain);
    }
    unmapWindow(&window);
}

void probeL3(bool dump)
{
    Window window = {};
    K60CpuFreqTable table = {};
    uint32_t rows[kLutRows] = {};
    unsigned index = 0;
    uint32_t topKhz = 0;

    if (!mapWindow(&window, kL3Base, kL3Window)) {
        IOLog("K60CpuFreq: L3 nomap base=0x%llx\n",
            static_cast<unsigned long long>(kL3Base));
        return;
    }
    if (readTable(&window, &table)) k60_cpufreq_pick_highest(&table, 0, &index, &topKhz);
    IOLog("K60CpuFreq: L3 base=0x%llx vote=%u rows=%u top=%ukHz level=%u\n",
        static_cast<unsigned long long>(kL3Base),
        rd32(window.va, K60_CPU_FREQ_REG_L3_VOTE) & 0xffu, table.count, topKhz, index);
    if (dump && table.count) {
        readRows(&window, rows);
        dumpRows("L3 ", rows, table.count);
    }
    unmapWindow(&window);
}

void voteL3(unsigned mode)
{
    Window window = {};
    K60CpuFreqTable table = {};
    K60CpuFreqWrite writes[1] = {};
    K60CpuFreqWrite restore[1] = {};
    uint32_t original[1] = {}, readback[1] = {};
    unsigned index = 0, n, restored;
    uint32_t topKhz = 0;
    int ok;

    if (!mapWindow(&window, kL3Base, kL3Window)) {
        IOLog("K60CpuFreq: L3 nomap base=0x%llx\n",
            static_cast<unsigned long long>(kL3Base));
        return;
    }
    if (!readTable(&window, &table) || k60_cpufreq_pick_highest(&table, 0, &index, &topKhz)) {
        IOLog("K60CpuFreq: L3 vote skipped: no non-turbo table\n");
        unmapWindow(&window);
        return;
    }
    n = k60_cpufreq_build_l3_vote(table.level[index], writes, 1);
    if (!k60_cpufreq_vote_allowed(1, &table, table.level[index], n)) {
        IOLog("K60CpuFreq: mode%u L3 vote skipped: table=%u level=%u writes=%u\n",
            mode, table.count, table.level[index], n);
        unmapWindow(&window);
        return;
    }
    original[0] = rd32(window.va, writes[0].offset);
    wr32(window.va, writes[0].offset, writes[0].value);
    readback[0] = rd32(window.va, writes[0].offset);
    ok = k60_cpufreq_check_readback(writes, readback, n);
    restored = k60_cpufreq_build_restore(writes, original, n, restore, 1);
    if (restored) wr32(window.va, restore[0].offset, restore[0].value);
    IOLog("K60CpuFreq: mode%u vote L3 level=%u (%ukHz) writes=%u readback=%s restored=%u\n",
        mode, table.level[index], topKhz, n, ok ? "ok" : "mismatch", restored);
    unmapWindow(&window);
}

/* Mode 9: why the big clusters ignore the vote. Domain 0 follows its
 * perf-state row in both directions (mode 8), while a domain-1 write reads
 * back and leaves the running level at the top. This probe separates the two
 * variables on the disabled-by-default path: first one row with the control
 * bit as the firmware left it, then every core's row with bit 0 set, reading
 * the domain state after each step. Every register it touches is written back,
 * so the firmware keeps ownership whatever the answer. */
void probeDcvsControl(unsigned domain)
{
    Window window = {};
    K60CpuFreqTable table = {};
    K60CpuFreqWrite single[K60_CPU_FREQ_MAX_WRITES] = {};
    K60CpuFreqWrite all[K60_CPU_FREQ_MAX_WRITES] = {};
    uint32_t original[K60_CPU_FREQ_MAX_WRITES] = {};
    uint32_t topKhz = 0, bottomKhz = 0, control, state, stateA, stateB, stateC, stateD, stateE;
    unsigned topIndex = 0, bottomIndex = 0, n, i;

    if (!mapWindow(&window, kDomainBase[domain], kDomainWindow)) {
        IOLog("K60CpuFreq: d%u nomap base=0x%llx\n", domain,
            static_cast<unsigned long long>(kDomainBase[domain]));
        return;
    }
    if (!readTable(&window, &table) ||
        k60_cpufreq_pick_highest(&table, 0, &topIndex, &topKhz) ||
        k60_cpufreq_pick_lowest(&table, &bottomIndex, &bottomKhz)) {
        IOLog("K60CpuFreq: mode9 d%u skipped: no non-turbo table\n", domain);
        unmapWindow(&window);
        return;
    }
    control = rd32(window.va, K60_CPU_FREQ_REG_DCVS_CTRL);
    state = rd32(window.va, K60_CPU_FREQ_REG_DOMAIN_STATE) & 0xffu;
    n = k60_cpufreq_build_votes(domain, 1u, table.level[topIndex], all,
        K60_CPU_FREQ_MAX_WRITES);
    for (i = 0; i < n; ++i) original[i] = rd32(window.va, all[i].offset);
    IOLog("K60CpuFreq: mode9 d%u enable=%u ctrl=0x%x vote=%u state=%u (%ukHz) rows=%u top=%u (%ukHz) bottom=%u (%ukHz) extra=%u\n",
        domain, rd32(window.va, K60_CPU_FREQ_REG_ENABLE) & 1u, control,
        rd32(window.va, K60_CPU_FREQ_REG_PERF_STATE) & 0xffu, state,
        state * K60_CPU_FREQ_XO_KHZ, table.count, table.level[topIndex], topKhz,
        table.level[bottomIndex], bottomKhz, n);

    /* Phase A: one row, control unchanged - the mode 7/8 write set. */
    k60_cpufreq_build_votes(domain, 0, table.level[topIndex], single,
        K60_CPU_FREQ_MAX_WRITES);
    wr32(window.va, single[0].offset, single[0].value);
    IOSleep(50);
    stateA = rd32(window.va, K60_CPU_FREQ_REG_DOMAIN_STATE) & 0xffu;
    single[0].value = table.level[bottomIndex];
    wr32(window.va, single[0].offset, single[0].value);
    IOSleep(50);
    stateB = rd32(window.va, K60_CPU_FREQ_REG_DOMAIN_STATE) & 0xffu;
    wr32(window.va, K60_CPU_FREQ_REG_PERF_STATE, original[0]);
    IOSleep(20);
    IOLog("K60CpuFreq: mode9 d%u a ctrl=0x%x top=%u -> %u (%ukHz) bottom=%u -> %u (%ukHz)\n",
        domain, control, table.level[topIndex], stateA, stateA * K60_CPU_FREQ_XO_KHZ,
        table.level[bottomIndex], stateB, stateB * K60_CPU_FREQ_XO_KHZ);

    /* Phase B: every core row, but never write DCVS_CTRL. Sheng's latest
     * CpuFreqProbe.cpp votes the perf-state row and writes the per-core rows
     * only when bit 0 is already set; setting it ourselves is what hung image
     * t/u before the console. Respect the firmware's ownership. */
    if (control & 1u) {
        for (i = 0; i < n; ++i) wr32(window.va, all[i].offset, table.level[topIndex]);
        IOSleep(50);
        stateC = rd32(window.va, K60_CPU_FREQ_REG_DOMAIN_STATE) & 0xffu;
        for (i = 0; i < n; ++i) wr32(window.va, all[i].offset, table.level[bottomIndex]);
        IOSleep(50);
        stateD = rd32(window.va, K60_CPU_FREQ_REG_DOMAIN_STATE) & 0xffu;
        for (i = 0; i < n; ++i) wr32(window.va, all[i].offset, original[i]);
        IOSleep(50);
        stateE = rd32(window.va, K60_CPU_FREQ_REG_DOMAIN_STATE) & 0xffu;
        IOLog("K60CpuFreq: mode9 d%u b ctrl=0x%x rows=%u top -> %u (%ukHz) bottom -> %u (%ukHz) restored state=%u (%ukHz)\n",
            domain, control, n, stateC, stateC * K60_CPU_FREQ_XO_KHZ,
            stateD, stateD * K60_CPU_FREQ_XO_KHZ,
            stateE, stateE * K60_CPU_FREQ_XO_KHZ);
    } else {
        IOLog("K60CpuFreq: mode9 d%u ctrl=0x%x bit0=0; leaving the firmware control alone\n",
            domain, control);
    }
    unmapWindow(&window);
}

void probeAll(bool dump)
{
    for (unsigned domain = 0; domain < K60_CPU_FREQ_DOMAINS; ++domain)
        probeDomain(domain, dump);
    probeL3(dump);
}

/* Mode 5: the 16 ms scheduler-idle sampler the official page asks for, with
 * every vote suppressed. processor_info(PROCESSOR_CPU_LOAD_INFO) is the kernel
 * face of the scheduler's per-CPU recount: four cumulative tick counters. One
 * window is the delta of those counters, so a sleeping CPU (idle == elapsed)
 * contributes 0 and a busy one approaches 1000 permille. The governor is fed
 * the real numbers and its chosen level is logged next to the hardware state,
 * but nothing is written. Modes 7 and 8 reuse the same loop and place the
 * governor's decisions: 7 only the down steps, 8 both directions. Each keeps
 * the first value it touched and restores it after ten seconds or when the
 * thread stops. */
constexpr unsigned kSampleSleepMs = 16;
constexpr unsigned kSampleLogWindows = 64;

/* Modes 7 and 8 only: the thread waits for the first window where the
 * governor has already stepped a domain away from the level it started from
 * (the boot burst pins every domain at the top for the first minute, so a
 * fixed time window would miss the drop), then applies steps for
 * kApplySpanWindows and restores. kApplyLatestEndWindow bounds the whole
 * experiment at 100 s even if the device never goes idle. The bound keeps an
 * unattended run from holding a vote for the whole boot. Mode 8 alternates
 * directions, so it gets twice the vote budget of mode 7. */
constexpr unsigned kApplyArmWindow = 625;
constexpr unsigned kApplySpanWindows = 625;
constexpr unsigned kApplyLatestEndWindow = 6250;
constexpr unsigned kApplyMaxVotes = 32;
/* Official section 5 :115 holds the performance cluster for one second after
 * a touch; section 5 :116 holds the CPU floor for 300 ms after a frame. Both
 * windows are re-armed by their own signal, not only by the boot-time down
 * step, so a touch after SpringBoard can reach the hardware too. */
constexpr unsigned kTouchSpanWindows = 63;
constexpr unsigned kFrameSpanWindows = 19;

/* Votes written by modes 7 and 8 for one domain, kept so the stop path can put
 * the registers back the way the firmware left them. */
struct Applied {
    K60CpuFreqWrite writes[K60_CPU_FREQ_MAX_WRITES];
    uint32_t originals[K60_CPU_FREQ_MAX_WRITES];
    uint32_t pdmemOriginal;
    unsigned count;
    bool touched;
    bool pdmemTouched;
};

unsigned restoreApplied(Window *windows, Window *pdmem, Applied *applied)
{
    unsigned domains = 0;

    for (unsigned domain = 0; domain < K60_CPU_FREQ_DOMAINS; ++domain) {
        Applied *a = &applied[domain];
        if (!a->touched) continue;
        for (unsigned i = 0; i < a->count; ++i)
            wr32(windows[domain].va, a->writes[i].offset, a->originals[i]);
        if (a->pdmemTouched && pdmem->va) {
            const unsigned offset = k60_cpufreq_pdmem_offset(domain);
            if (offset) wr32(pdmem->va, offset, a->pdmemOriginal);
            a->pdmemTouched = false;
        }
        a->touched = false;
        ++domains;
    }
    barrier();
    return domains;
}

/* DOMAIN_STATE reports the L field of the row the firmware is running, not the
 * row index: the mode-6 log shows 81 before a write and 15 after placing row 0,
 * whose L field is 15. Map the field back through the raw LUT so the governor
 * starts where the hardware actually is. Returns the table index, or -1 when
 * the row is not in the non-turbo table. */
int stateTableIndex(Window *window, const K60CpuFreqTable *table, uint32_t state)
{
    uint32_t rows[K60_CPU_FREQ_LUT_ROWS];

    readRows(window, rows);
    for (unsigned row = 0; row < K60_CPU_FREQ_LUT_ROWS; ++row) {
        if ((rows[row] & 0xffu) != state) continue;
        for (unsigned i = 0; i < table->count; ++i)
            if (table->level[i] == row) return static_cast<int>(i);
        return -1;
    }
    return -1;
}

volatile unsigned sSampleStop;
unsigned sSampleStarted;
volatile unsigned sSampleApply;

void samplerThread(void *, wait_result_t)
{
    K60CpuFreqTable tables[K60_CPU_FREQ_DOMAINS] = {};
    Window windows[K60_CPU_FREQ_DOMAINS] = {};
    Window pdmem = {};
    K60CpuFreqGovernor gov = {};
    Applied applied[K60_CPU_FREQ_DOMAINS] = {};
    bool ready[K60_CPU_FREQ_DOMAINS] = {};
    bool applyReady[K60_CPU_FREQ_DOMAINS] = {};
    bool raiseLogged[K60_CPU_FREQ_DOMAINS] = {};
    unsigned votedIndex[K60_CPU_FREQ_DOMAINS] = {};
    bool forceVote[K60_CPU_FREQ_DOMAINS] = {};
    unsigned appliedVotes = 0;
    bool deviationArmed = false;
    bool armed = false;
    bool signalArmed = false;
    uint64_t applyStart = 0;
    uint64_t applySpan = kApplySpanWindows;
    unsigned applyMode = sSampleApply;
    bool apply = applyMode != 0;
    bool allowRaise = applyMode >= 8;
    uint32_t previous[K60_CPU_FREQ_CPUS][K60_CPU_FREQ_STATES] = {};
    uint64_t idle[K60_CPU_FREQ_CPUS] = {}, elapsed[K60_CPU_FREQ_CPUS] = {};
    unsigned busy[K60_CPU_FREQ_DOMAINS] = {};
    K60BoostState boost = {};
    int frameActive = 0, framePrevious = 0;
    uint32_t touchReports = 0;
    int touchActive = 0, touchPrevious = 0;
    uint64_t window = 0;
    bool havePrevious = false;
    host_t host = nullptr;

    k60_cpufreq_governor_reset(&gov, 0);
    k60_boost_reset(&boost);
    for (unsigned domain = 0; domain < K60_CPU_FREQ_DOMAINS; ++domain) {
        uint32_t state;
        unsigned current = 0;
        bool matched = false;

        if (!mapWindow(&windows[domain], kDomainBase[domain], kDomainWindow)) continue;
        if (!readTable(&windows[domain], &tables[domain])) {
            unmapWindow(&windows[domain]);
            continue;
        }
        state = rd32(windows[domain].va, K60_CPU_FREQ_REG_DOMAIN_STATE) & 0xffu;
        {
            int index = stateTableIndex(&windows[domain], &tables[domain], state);
            if (index >= 0) {current = static_cast<unsigned>(index); matched = true;}
        }
        gov.current[domain] = current;
        gov.down[domain] = 0;
        gov.quiet[domain] = 0;
        votedIndex[domain] = current;
        applyReady[domain] = matched;
        ready[domain] = true;
        if (!matched)
            IOLog("K60CpuFreq: d%u state=%u not in table; apply disabled\n", domain, state);
    }
    if (mapWindow(&pdmem, kPdmemBase, kPdmemWindow))
        IOLog("K60CpuFreq: PDMEM base=0x%llx votes=0x804/0x808/0x80c\n",
            static_cast<unsigned long long>(kPdmemBase));
    else
        IOLog("K60CpuFreq: PDMEM unavailable; perf-lock votes skipped\n");
    IOLog("K60CpuFreq: sample start every=%ums log-every=%u domains=%u apply=%u\n",
        kSampleSleepMs, kSampleLogWindows, K60_CPU_FREQ_DOMAINS, applyMode);
    while (!sSampleStop) {
        IOSleep(kSampleSleepMs);
        if (sSampleStop) break;
        ++window;
        for (unsigned cpu = 0; cpu < K60_CPU_FREQ_CPUS; ++cpu) {
            processor_cpu_load_info_data_t load = {};
            mach_msg_type_number_t count = PROCESSOR_CPU_LOAD_INFO_COUNT;
            uint32_t now[K60_CPU_FREQ_STATES];

            idle[cpu] = 0;
            elapsed[cpu] = 0;
            if (!processor_array[cpu]) continue;
            if (processor_info(processor_array[cpu], PROCESSOR_CPU_LOAD_INFO, &host,
                    reinterpret_cast<processor_info_t>(&load), &count) != KERN_SUCCESS)
                continue;
            for (unsigned state = 0; state < K60_CPU_FREQ_STATES; ++state)
                now[state] = load.cpu_ticks[state];
            if (havePrevious)
                (void)k60_cpufreq_tick_delta(previous[cpu], now, &idle[cpu], &elapsed[cpu]);
            for (unsigned state = 0; state < K60_CPU_FREQ_STATES; ++state)
                previous[cpu][state] = now[state];
        }
        if (!havePrevious) {
            havePrevious = true;
            continue;
        }
        /* Official section 5 :116: when two of the last four 16 ms windows
         * carried a GPU submission, every CPU domain is held at 60 % of its
         * top for 300 ms. The submit window is the CP ring occupancy the DCVS
         * thread already reads, sampled here too so the read-only mode 5 also
         * reports the floor it would request. */
        {
            const uint64_t boostNow = window * kSampleSleepMs;
            int pending = pong_adreno_cp_pending();
            if (pending < 0) pending = 0;
            k60_boost_window(&boost, boostNow, pending > 0);
            frameActive = k60_boost_frame_active(&boost, boostNow);
            const uint32_t reports = pong_touch_report_count();
            if (reports != touchReports) {
                k60_boost_touch(&boost, boostNow);
                touchReports = reports;
            }
            touchActive = k60_boost_touch_active(&boost, boostNow);
        }
        for (unsigned domain = 0; domain < K60_CPU_FREQ_DOMAINS; ++domain) {
            if (!ready[domain]) continue;
            busy[domain] = k60_cpufreq_domain_busy_elapsed(idle, elapsed,
                K60_CPU_FREQ_CPUS, domain);
            (void)k60_cpufreq_governor_window(&gov, &tables[domain], domain,
                busy[domain], static_cast<unsigned>(touchActive),
                static_cast<unsigned>(frameActive));
        }
        if (frameActive != framePrevious) {
            const uint32_t top = tables[0].count ? tables[0].khz[tables[0].count - 1] : 0;
            IOLog("K60CpuFreq: mode%u frame floor %s win=%llu subs=%u floor=%ukHz\n",
                applyMode, frameActive ? "active" : "released",
                static_cast<unsigned long long>(window),
                k60_boost_frame_count(&boost), k60_boost_cpu_floor_khz(top));
            framePrevious = frameActive;
        }
        if (touchActive != touchPrevious) {
            IOLog("K60CpuFreq: mode%u touch boost %s win=%llu reports=%u\n",
                applyMode, touchActive ? "active" : "released",
                static_cast<unsigned long long>(window), touchReports);
            touchPrevious = touchActive;
        }

        /* Domains 1 and 2 are still disabled when the first read runs, so
         * their state is 0 and no table row matches. Retry the match while
         * the experiment runs: once ArmCpu has started the secondary CPUs the
         * domain reports a real level and can join the loop. */
        if (apply && window % kSampleLogWindows == 0) {
            for (unsigned domain = 0; domain < K60_CPU_FREQ_DOMAINS; ++domain) {
                uint32_t state;
                int index;

                if (!ready[domain] || applyReady[domain]) continue;
                state = rd32(windows[domain].va, K60_CPU_FREQ_REG_DOMAIN_STATE) & 0xffu;
                index = stateTableIndex(&windows[domain], &tables[domain], state);
                if (index < 0) continue;
                gov.current[domain] = static_cast<unsigned>(index);
                gov.down[domain] = 0;
                gov.quiet[domain] = 0;
                votedIndex[domain] = static_cast<unsigned>(index);
                forceVote[domain] = false;
                applyReady[domain] = true;
                IOLog("K60CpuFreq: mode%u reseed d%u state=%u level=%u\n",
                    applyMode, domain, state, tables[domain].level[index]);
            }
        }
        if (apply && !armed && !deviationArmed && window >= kApplyArmWindow) {
            for (unsigned domain = 0; domain < K60_CPU_FREQ_DOMAINS; ++domain) {
                if (!ready[domain] || !applyReady[domain]) continue;
                if (applyMode < 8) {
                    if (gov.current[domain] >= votedIndex[domain]) continue;
                } else if (gov.current[domain] == votedIndex[domain]) continue;
                armed = true;
                deviationArmed = true;
                applyStart = window;
                applySpan = kApplySpanWindows;
                appliedVotes = 0;
                signalArmed = false;
                IOLog("K60CpuFreq: mode%u armed win=%llu d%u level=%u\n",
                    applyMode, static_cast<unsigned long long>(window), domain,
                    tables[domain].level[gov.current[domain]]);
                break;
            }
        }
        if (apply && !armed && (touchActive || frameActive) &&
            appliedVotes < kApplyMaxVotes) {
            armed = true;
            applyStart = window;
            applySpan = touchActive ? kTouchSpanWindows : kFrameSpanWindows;
            signalArmed = true;
            /* The vote budget bounds one window, not the whole run: a boot
             * window that already spent votes must not end a later touch
             * window in its first millisecond. */
            appliedVotes = 0;
            /* The restore handed the domain back to firmware, but gov.current
             * still names the level this driver voted last, so the equality
             * check would skip the vote the signal just asked for. Force one
             * fresh vote per signal window; the span and the vote budget still
             * bound it. */
            if (allowRaise) {
                for (unsigned domain = 0; domain < K60_CPU_FREQ_DOMAINS; ++domain)
                    if (ready[domain] && applyReady[domain]) forceVote[domain] = true;
            }
            IOLog("K60CpuFreq: mode%u %s window win=%llu span=%llu\n", applyMode,
                touchActive ? "touch" : "frame",
                static_cast<unsigned long long>(window),
                static_cast<unsigned long long>(applySpan));
        }
        if (apply) {
            for (unsigned domain = 0; domain < K60_CPU_FREQ_DOMAINS; ++domain) {
                K60CpuFreqWrite set[K60_CPU_FREQ_MAX_WRITES] = {};
                uint32_t readback[K60_CPU_FREQ_MAX_WRITES] = {};
                uint32_t before, after, pdmemAfter = 0;
                unsigned n, i, pdmemOffset = k60_cpufreq_pdmem_offset(domain);
                bool ok;

                if (!ready[domain] || !applyReady[domain]) continue;
                if (gov.current[domain] > votedIndex[domain] && !allowRaise) {
                    /* Mode 7 keeps the mode-6 rule: no raise is written. */
                    gov.current[domain] = votedIndex[domain];
                    if (!raiseLogged[domain]) {
                        IOLog("K60CpuFreq: mode%u d%u raise refused; down-only run\n",
                            applyMode, domain);
                        raiseLogged[domain] = true;
                    }
                    continue;
                }
                if (!forceVote[domain] && gov.current[domain] == votedIndex[domain]) continue;
                if (!armed || window < applyStart || window > applyStart + applySpan ||
                    (window > kApplyLatestEndWindow && !signalArmed) ||
                    appliedVotes >= kApplyMaxVotes) continue;
                n = k60_cpufreq_build_votes(domain,
                    rd32(windows[domain].va, K60_CPU_FREQ_REG_DCVS_CTRL) & 1u,
                    tables[domain].level[gov.current[domain]], set, K60_CPU_FREQ_MAX_WRITES);
                if (!k60_cpufreq_vote_allowed(rd32(windows[domain].va,
                        K60_CPU_FREQ_REG_ENABLE) & 1u, &tables[domain],
                        tables[domain].level[gov.current[domain]], n)) {
                    gov.current[domain] = votedIndex[domain];
                    forceVote[domain] = false;
                    continue;
                }
                before = rd32(windows[domain].va, K60_CPU_FREQ_REG_DOMAIN_STATE) & 0xffu;
                if (!applied[domain].touched) {
                    for (i = 0; i < n; ++i) {
                        applied[domain].writes[i] = set[i];
                        applied[domain].originals[i] = rd32(windows[domain].va, set[i].offset);
                    }
                    applied[domain].count = n;
                    applied[domain].touched = true;
                    if (pdmem.va && pdmemOffset) {
                        applied[domain].pdmemOriginal = rd32(pdmem.va, pdmemOffset);
                        applied[domain].pdmemTouched = true;
                    }
                }
                if (pdmem.va && pdmemOffset) {
                    K60CpuFreqWrite vote = {};
                    if (k60_cpufreq_build_pdmem_vote(domain, tables[domain].level[gov.current[domain]],
                        &vote, 1) == 1)
                        wr32(pdmem.va, vote.offset, vote.value);
                }
                for (i = 0; i < n; ++i) wr32(windows[domain].va, set[i].offset, set[i].value);
                barrier();
                for (i = 0; i < n; ++i) readback[i] = rd32(windows[domain].va, set[i].offset);
                if (pdmem.va && pdmemOffset) pdmemAfter = rd32(pdmem.va, pdmemOffset) & 0xffu;
                ok = k60_cpufreq_check_readback(set, readback, n) != 0;
                ++appliedVotes;
                IOSleep(1);
                after = rd32(windows[domain].va, K60_CPU_FREQ_REG_DOMAIN_STATE) & 0xffu;
                IOLog("K60CpuFreq: mode%u apply d%u level=%u (%ukHz) busy=%u writes=%u pdmem=%u readback=%s state=%u->%u\n",
                    applyMode, domain, tables[domain].level[gov.current[domain]],
                    tables[domain].khz[gov.current[domain]], busy[domain], n, pdmemAfter,
                    ok ? "ok" : "mismatch", before, after);
                if (!ok) {
                    for (i = 0; i < n; ++i)
                        wr32(windows[domain].va, set[i].offset, applied[domain].originals[i]);
                    if (applied[domain].pdmemTouched && pdmem.va && pdmemOffset) {
                        wr32(pdmem.va, pdmemOffset, applied[domain].pdmemOriginal);
                        applied[domain].pdmemTouched = false;
                    }
                    barrier();
                    applied[domain].touched = false;
                    applyReady[domain] = false;
                    gov.current[domain] = votedIndex[domain];
                    forceVote[domain] = false;
                } else {
                    votedIndex[domain] = gov.current[domain];
                    forceVote[domain] = false;
                }
            }
            if (armed && (window >= applyStart + applySpan ||
                    (!signalArmed && window >= kApplyLatestEndWindow) ||
                    appliedVotes >= kApplyMaxVotes)) {
                unsigned domains = restoreApplied(windows, &pdmem, applied);
                IOLog("K60CpuFreq: mode%u restore domains=%u votes=%u\n",
                    applyMode, domains, appliedVotes);
                armed = false;
                signalArmed = false;
            }
        }
        if ((window % kSampleLogWindows) == 0) {
            uint32_t hardware[K60_CPU_FREQ_DOMAINS] = {};
            for (unsigned domain = 0; domain < K60_CPU_FREQ_DOMAINS; ++domain)
                if (ready[domain])
                    hardware[domain] = (rd32(windows[domain].va,
                        K60_CPU_FREQ_REG_DOMAIN_STATE) & 0xffu) * K60_CPU_FREQ_XO_KHZ;
            IOLog("K60CpuFreq: sample win=%llu d0=%u/%ukHz/hw%ukHz d1=%u/%ukHz/hw%ukHz d2=%u/%ukHz/hw%ukHz fr=%d tb=%d\n",
                static_cast<unsigned long long>(window),
                busy[0], tables[0].khz[gov.current[0]], hardware[0],
                busy[1], tables[1].khz[gov.current[1]], hardware[1],
                busy[2], tables[2].khz[gov.current[2]], hardware[2], frameActive,
                touchActive);
        }
    }
    if (apply) {
        unsigned domains = restoreApplied(windows, &pdmem, applied);
        IOLog("K60CpuFreq: mode%u restore domains=%u votes=%u\n",
            applyMode, domains, appliedVotes);
    }
    for (unsigned domain = 0; domain < K60_CPU_FREQ_DOMAINS; ++domain)
        if (windows[domain].map) unmapWindow(&windows[domain]);
    if (pdmem.map) unmapWindow(&pdmem);
    IOLog("K60CpuFreq: sample stop win=%llu\n", static_cast<unsigned long long>(window));
}

void startSampler(unsigned mode)
{
    thread_t thread = nullptr;

    if (__atomic_exchange_n(&sSampleStarted, 1u, __ATOMIC_ACQ_REL)) return;
    sSampleStop = 0;
    sSampleApply = mode;
    if (kernel_thread_start(samplerThread, nullptr, &thread) != KERN_SUCCESS) {
        IOLog("K60CpuFreq: sample thread failed\n");
        sSampleStarted = 0;
        return;
    }
    thread_deallocate(thread);
}

} // namespace

extern "C" void k60_cpufreq_probe(void)
{
    static unsigned attempted;
    unsigned mode = 0;

    PE_parse_boot_argn("k60_cpufreq", &mode, sizeof(mode));
    if (!mode || __atomic_exchange_n(&attempted, 1u, __ATOMIC_ACQ_REL)) return;
    if (mode == 4 || mode == 9 || mode > 9) {
        IOLog("K60CpuFreq: mode=%u ignored; modes 1-3, 5, 6, 7 and 8 are implemented, mode 9 is disabled after two hangs\n", mode);
        return;
    }
    IOLog("K60CpuFreq: mode=%u EPSS domains=%u cpus=%u lut-rows=%u\n",
        mode, K60_CPU_FREQ_DOMAINS, K60_CPU_FREQ_CPUS, K60_CPU_FREQ_LUT_ROWS);
    if (mode == 1) {
        probeAll(true);
        return;
    }
    if (mode == 2) {
        voteDomain(0, mode, false);
        return;
    }
    if (mode == 6) {
        voteDomain(0, mode, true);
        return;
    }
    if (mode == 9) {
        /* Unreachable: the gate above rejects 9. The probe stays compiled so a
         * future firmware answer can reuse it, but it must not run on this
         * board - image t and image u both stopped before the console. */
        for (unsigned domain = 0; domain < K60_CPU_FREQ_DOMAINS; ++domain)
            probeDcvsControl(domain);
        return;
    }
    if (mode == 5) {
        probeAll(false);
        startSampler(0);
        return;
    }
    if (mode == 7 || mode == 8) {
        probeAll(false);
        startSampler(mode);
        return;
    }
    for (unsigned domain = 0; domain < K60_CPU_FREQ_DOMAINS; ++domain) voteDomain(domain, mode, false);
    voteL3(mode);
}

/* Second read-only pass for probe builds. The first pass runs before ArmCpu
 * starts the secondary CPUs, so domains 1 and 2 can still read as disabled.
 * This does nothing unless k60_cpufreq=1, and never votes. */
extern "C" void k60_cpufreq_probe_late(void)
{
    unsigned mode = 0;

    PE_parse_boot_argn("k60_cpufreq", &mode, sizeof(mode));
    if (mode != 1) return;
    IOLog("K60CpuFreq: late read begin (mode 1)\n");
    probeAll(false);
    IOLog("K60CpuFreq: late read end\n");
}

/* Stopped from K60Battery::cleanup; the sampler thread owns no resource the
 * battery path needs, so a flag is enough and the thread exits after its sleep. */
extern "C" void k60_cpufreq_sample_stop(void)
{
    sSampleStop = 1;
}
