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
 * votes every domain and L3. Any other value is logged and ignored so a typo
 * cannot start a path that has never been measured. This runs from
 * k60_physical_battery_start(), which is the only userland-triggered IOKit
 * entry the archive owns today; it does not need the ADSP handoff lease.
 */
#include <IOKit/IOLib.h>
#include <IOKit/IOMemoryDescriptor.h>
#include <IOKit/IODeviceMemory.h>
#include <pexpert/pexpert.h>
#include "K60CpuFreqPlan.h"

namespace {

constexpr uint64_t kDomainBase[K60_CPU_FREQ_DOMAINS] = {0x17d91000, 0x17d92000, 0x17d93000};
constexpr uint64_t kL3Base = 0x17d90000;
constexpr uint32_t kDomainWindow = 0x1000;
constexpr uint32_t kL3Window = 0x4000;
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

bool readTable(Window *window, K60CpuFreqTable *table)
{
    uint32_t rows[kLutRows];
    unsigned i;

    for (i = 0; i < kLutRows; ++i) rows[i] = rd32(window->va, K60_CPU_FREQ_REG_FREQ_LUT + i * 4);
    return k60_cpufreq_build_table(rows, kLutRows, 0, table) == 0;
}

void probeDomain(unsigned domain)
{
    Window window = {};
    K60CpuFreqTable table = {};
    unsigned index = 0;
    uint32_t topKhz = 0, stateKhz = 0, state, control, vote;

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
    IOLog("K60CpuFreq: d%u base=0x%llx enable=%u state=%u (%ukHz) dcvs=%u vote=%u rows=%u top=%ukHz level=%u mode1=read-only\n",
        domain, static_cast<unsigned long long>(kDomainBase[domain]),
        rd32(window.va, K60_CPU_FREQ_REG_ENABLE) & 1u, state & 0xffu, stateKhz,
        control & 1u, vote, table.count, topKhz, index);
    unmapWindow(&window);
}

void voteDomain(unsigned domain, unsigned mode)
{
    Window window = {};
    K60CpuFreqTable table = {};
    K60CpuFreqWrite writes[K60_CPU_FREQ_MAX_WRITES] = {};
    unsigned index = 0, n, i;
    uint32_t topKhz = 0, dcvs;

    if (!mapWindow(&window, kDomainBase[domain], kDomainWindow)) {
        IOLog("K60CpuFreq: d%u nomap base=0x%llx\n", domain,
            static_cast<unsigned long long>(kDomainBase[domain]));
        return;
    }
    dcvs = rd32(window.va, K60_CPU_FREQ_REG_DCVS_CTRL) & 1u;
    if (!readTable(&window, &table) || k60_cpufreq_pick_highest(&table, 0, &index, &topKhz)) {
        IOLog("K60CpuFreq: d%u vote skipped: no non-turbo table\n", domain);
        unmapWindow(&window);
        return;
    }
    n = k60_cpufreq_build_votes(domain, dcvs, table.level[index], writes,
        K60_CPU_FREQ_MAX_WRITES);
    for (i = 0; i < n; ++i) wr32(window.va, writes[i].offset, writes[i].value);
    IOLog("K60CpuFreq: mode%u vote d%u level=%u (%ukHz) dcvs=%u writes=%u\n",
        mode, domain, table.level[index], topKhz, dcvs, n);
    unmapWindow(&window);
}

void probeL3()
{
    Window window = {};
    K60CpuFreqTable table = {};
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
    unmapWindow(&window);
}

void voteL3(unsigned mode)
{
    Window window = {};
    K60CpuFreqTable table = {};
    K60CpuFreqWrite writes[1] = {};
    unsigned index = 0, n;
    uint32_t topKhz = 0;

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
    if (n) wr32(window.va, writes[0].offset, writes[0].value);
    IOLog("K60CpuFreq: mode%u vote L3 level=%u (%ukHz) writes=%u\n",
        mode, table.level[index], topKhz, n);
    unmapWindow(&window);
}

} // namespace

extern "C" void k60_cpufreq_probe(void)
{
    static unsigned attempted;
    unsigned mode = 0;

    PE_parse_boot_argn("k60_cpufreq", &mode, sizeof(mode));
    if (!mode || __atomic_exchange_n(&attempted, 1u, __ATOMIC_ACQ_REL)) return;
    if (mode > 3) {
        IOLog("K60CpuFreq: mode=%u ignored; modes 1-3 are implemented\n", mode);
        return;
    }
    IOLog("K60CpuFreq: mode=%u EPSS domains=%u cpus=%u lut-rows=%u\n",
        mode, K60_CPU_FREQ_DOMAINS, K60_CPU_FREQ_CPUS, K60_CPU_FREQ_LUT_ROWS);
    if (mode == 1) {
        for (unsigned domain = 0; domain < K60_CPU_FREQ_DOMAINS; ++domain) probeDomain(domain);
        probeL3();
        return;
    }
    if (mode == 2) {
        voteDomain(0, mode);
        return;
    }
    for (unsigned domain = 0; domain < K60_CPU_FREQ_DOMAINS; ++domain) voteDomain(domain, mode);
    voteL3(mode);
}
