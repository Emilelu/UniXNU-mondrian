/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/*
 * Read-only EPSS probe. It answers one question before anything votes: what
 * does the K60's CPU-frequency block actually contain? For every domain it
 * reports the enable bit, the current domain-state level, the APSS perf-state
 * vote and the decoded look-up table; for L3 it reports the vote and the
 * table. No register is written and nothing is polled.
 *
 * Off by default: boot argument k60_cpufreq=1 turns it on. Only mode 1 is
 * implemented; larger values are logged and ignored so a typo cannot start a
 * vote path that has never been measured. This runs from
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

void probeDomain(unsigned domain)
{
    Window window = {};
    uint32_t rows[kLutRows];
    K60CpuFreqTable table;
    unsigned index = 0, i;
    uint32_t topKhz = 0, stateKhz = 0, state, control, vote;

    if (!mapWindow(&window, kDomainBase[domain], kDomainWindow)) {
        IOLog("K60CpuFreq: d%u nomap base=0x%llx\n", domain,
            static_cast<unsigned long long>(kDomainBase[domain]));
        return;
    }
    for (i = 0; i < kLutRows; ++i) rows[i] = rd32(window.va, K60_CPU_FREQ_REG_FREQ_LUT + i * 4);
    state = rd32(window.va, K60_CPU_FREQ_REG_DOMAIN_STATE);
    control = rd32(window.va, K60_CPU_FREQ_REG_DCVS_CTRL);
    vote = rd32(window.va, K60_CPU_FREQ_REG_PERF_STATE) & 0xffu;
    if (state & 0xffu) stateKhz = (state & 0xffu) * K60_CPU_FREQ_XO_KHZ;
    const int built = k60_cpufreq_build_table(rows, kLutRows, 0, &table);
    if (!built) k60_cpufreq_pick_highest(&table, 0, &index, &topKhz);
    IOLog("K60CpuFreq: d%u base=0x%llx enable=%u state=%u (%ukHz) dcvs=%u vote=%u rows=%u top=%ukHz level=%u mode1=read-only\n",
        domain, static_cast<unsigned long long>(kDomainBase[domain]),
        rd32(window.va, K60_CPU_FREQ_REG_ENABLE) & 1u, state & 0xffu, stateKhz,
        control & 1u, vote, table.count, topKhz, index);
    unmapWindow(&window);
}

void probeL3()
{
    Window window = {};
    uint32_t rows[kLutRows];
    K60CpuFreqTable table;
    unsigned index = 0, i;
    uint32_t topKhz = 0;

    if (!mapWindow(&window, kL3Base, kL3Window)) {
        IOLog("K60CpuFreq: L3 nomap base=0x%llx\n",
            static_cast<unsigned long long>(kL3Base));
        return;
    }
    for (i = 0; i < kLutRows; ++i) rows[i] = rd32(window.va, K60_CPU_FREQ_REG_FREQ_LUT + i * 4);
    const int built = k60_cpufreq_build_table(rows, kLutRows, 0, &table);
    if (!built) k60_cpufreq_pick_highest(&table, 0, &index, &topKhz);
    IOLog("K60CpuFreq: L3 base=0x%llx vote=%u rows=%u top=%ukHz level=%u\n",
        static_cast<unsigned long long>(kL3Base),
        rd32(window.va, K60_CPU_FREQ_REG_L3_VOTE) & 0xffu, table.count, topKhz, index);
    unmapWindow(&window);
}

} // namespace

extern "C" void k60_cpufreq_probe(void)
{
    static unsigned attempted;
    unsigned mode = 0;

    PE_parse_boot_argn("k60_cpufreq", &mode, sizeof(mode));
    if (!mode || __atomic_exchange_n(&attempted, 1u, __ATOMIC_ACQ_REL)) return;
    if (mode != 1) {
        IOLog("K60CpuFreq: mode=%u ignored; only mode 1 (read-only probe) is implemented\n", mode);
        return;
    }
    IOLog("K60CpuFreq: probing EPSS domains=%u cpus=%u lut-rows=%u (read-only)\n",
        K60_CPU_FREQ_DOMAINS, K60_CPU_FREQ_CPUS, K60_CPU_FREQ_LUT_ROWS);
    for (unsigned domain = 0; domain < K60_CPU_FREQ_DOMAINS; ++domain) probeDomain(domain);
    probeL3();
}
