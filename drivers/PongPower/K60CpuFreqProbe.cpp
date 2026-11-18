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
 * down steps between ten and twenty seconds, then restores the original votes.
 * Mode 6 was
 * the safe first write: a lower level never needs a voltage raise, and mode 7
 * keeps that rule (it refuses every raise). Any other value is logged and
 * ignored so a typo cannot
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

/* The SDK header hides the array behind KERNEL_PRIVATE, but the kernel exports
 * it and processor_info() needs the processor_t. The declared extent only has
 * to cover the eight CPUs this board has. */
extern "C" processor_t processor_array[64];

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
    K60CpuFreqTable table = {};
    uint32_t rows[kLutRows] = {};
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
    if (dump && table.count) {
        readRows(&window, rows);
        dumpRows("", rows, table.count);
    }
    unmapWindow(&window);
}

void voteDomain(unsigned domain, unsigned mode, bool lowest)
{
    Window window = {};
    K60CpuFreqTable table = {};
    K60CpuFreqWrite writes[K60_CPU_FREQ_MAX_WRITES] = {};
    K60CpuFreqWrite restore[K60_CPU_FREQ_MAX_WRITES] = {};
    uint32_t original[K60_CPU_FREQ_MAX_WRITES] = {};
    uint32_t readback[K60_CPU_FREQ_MAX_WRITES] = {};
    unsigned index = 0, n, i, enabled, dcvs, restored;
    unsigned stateBefore, stateAfter, stateRestored;
    uint32_t topKhz = 0;
    int ok;

    if (!mapWindow(&window, kDomainBase[domain], kDomainWindow)) {
        IOLog("K60CpuFreq: d%u nomap base=0x%llx\n", domain,
            static_cast<unsigned long long>(kDomainBase[domain]));
        return;
    }
    enabled = rd32(window.va, K60_CPU_FREQ_REG_ENABLE) & 1u;
    dcvs = rd32(window.va, K60_CPU_FREQ_REG_DCVS_CTRL) & 1u;
    if (!readTable(&window, &table)) {
        IOLog("K60CpuFreq: d%u vote skipped: no non-turbo table\n", domain);
        unmapWindow(&window);
        return;
    }
    if (lowest) {
        if (k60_cpufreq_pick_lowest(&table, &index, &topKhz)) {
            IOLog("K60CpuFreq: d%u vote skipped: no non-turbo table\n", domain);
            unmapWindow(&window);
            return;
        }
    } else if (k60_cpufreq_pick_highest(&table, 0, &index, &topKhz)) {
        IOLog("K60CpuFreq: d%u vote skipped: no non-turbo table\n", domain);
        unmapWindow(&window);
        return;
    }
    n = k60_cpufreq_build_votes(domain, dcvs, table.level[index], writes,
        K60_CPU_FREQ_MAX_WRITES);
    if (!k60_cpufreq_vote_allowed(enabled, &table, table.level[index], n)) {
        IOLog("K60CpuFreq: mode%u d%u vote skipped: enable=%u table=%u level=%u writes=%u\n",
            mode, domain, enabled, table.count, table.level[index], n);
        unmapWindow(&window);
        return;
    }
    for (i = 0; i < n; ++i) original[i] = rd32(window.va, writes[i].offset);
    stateBefore = rd32(window.va, K60_CPU_FREQ_REG_DOMAIN_STATE) & 0xffu;
    for (i = 0; i < n; ++i) wr32(window.va, writes[i].offset, writes[i].value);
    for (i = 0; i < n; ++i) readback[i] = rd32(window.va, writes[i].offset);
    ok = k60_cpufreq_check_readback(writes, readback, n);
    IOSleep(20);
    stateAfter = rd32(window.va, K60_CPU_FREQ_REG_DOMAIN_STATE) & 0xffu;
    restored = k60_cpufreq_build_restore(writes, original, n, restore,
        K60_CPU_FREQ_MAX_WRITES);
    for (i = 0; i < restored; ++i) wr32(window.va, restore[i].offset, restore[i].value);
    IOSleep(20);
    stateRestored = rd32(window.va, K60_CPU_FREQ_REG_DOMAIN_STATE) & 0xffu;
    IOLog("K60CpuFreq: mode%u vote d%u level=%u (%ukHz) dcvs=%u writes=%u readback=%s restored=%u state=%u->%u->%u\n",
        mode, domain, table.level[index], topKhz, dcvs, n,
        ok ? "ok" : "mismatch", restored, stateBefore, stateAfter, stateRestored);
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
 * but nothing is written: a write loop needs the rail/thermal ordering that
 * section 5 still lacks. Mode 7 reuses the same loop and applies only the
 * governor's down steps, under the mode-6 rule that lowering never needs a
 * voltage raise; it restores every vote it wrote after ten seconds or when the
 * thread stops. A raise is refused and logged, never written. */
constexpr unsigned kSampleSleepMs = 16;
constexpr unsigned kSampleLogWindows = 64;

/* Mode 7 only: the thread waits for the first window where the governor has
 * already stepped a domain below the level it started from (the boot burst
 * pins every domain at the top for the first minute, so a fixed time window
 * would miss the drop), then applies down steps for kApplySpanWindows and
 * restores. kApplyLatestEndWindow bounds the whole experiment at 100 s even
 * if the device never goes idle. The bound keeps an unattended run from
 * holding a low vote for the whole boot. */
constexpr unsigned kApplyArmWindow = 625;
constexpr unsigned kApplySpanWindows = 625;
constexpr unsigned kApplyLatestEndWindow = 6250;
constexpr unsigned kApplyMaxVotes = 16;

/* Votes written by mode 7 for one domain, kept so the stop path can put the
 * registers back the way the firmware left them. */
struct Applied {
    K60CpuFreqWrite writes[K60_CPU_FREQ_MAX_WRITES];
    uint32_t originals[K60_CPU_FREQ_MAX_WRITES];
    unsigned count;
    bool touched;
};

unsigned restoreApplied(Window *windows, Applied *applied)
{
    unsigned domains = 0;

    for (unsigned domain = 0; domain < K60_CPU_FREQ_DOMAINS; ++domain) {
        Applied *a = &applied[domain];
        if (!a->touched) continue;
        for (unsigned i = 0; i < a->count; ++i)
            wr32(windows[domain].va, a->writes[i].offset, a->originals[i]);
        a->touched = false;
        ++domains;
    }
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
    K60CpuFreqGovernor gov = {};
    Applied applied[K60_CPU_FREQ_DOMAINS] = {};
    bool ready[K60_CPU_FREQ_DOMAINS] = {};
    bool applyReady[K60_CPU_FREQ_DOMAINS] = {};
    bool raiseLogged[K60_CPU_FREQ_DOMAINS] = {};
    unsigned votedIndex[K60_CPU_FREQ_DOMAINS] = {};
    unsigned dcvsCtrl[K60_CPU_FREQ_DOMAINS] = {};
    unsigned appliedVotes = 0;
    bool restored = false;
    bool armed = false;
    uint64_t applyStart = 0;
    bool apply = sSampleApply != 0;
    uint32_t previous[K60_CPU_FREQ_CPUS][K60_CPU_FREQ_STATES] = {};
    uint64_t idle[K60_CPU_FREQ_CPUS] = {}, elapsed[K60_CPU_FREQ_CPUS] = {};
    unsigned busy[K60_CPU_FREQ_DOMAINS] = {};
    uint64_t window = 0;
    bool havePrevious = false;
    host_t host = nullptr;

    k60_cpufreq_governor_reset(&gov, 0);
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
        dcvsCtrl[domain] = rd32(windows[domain].va, K60_CPU_FREQ_REG_DCVS_CTRL) & 1u;
        applyReady[domain] = matched;
        ready[domain] = true;
        if (!matched)
            IOLog("K60CpuFreq: d%u state=%u not in table; apply disabled\n", domain, state);
    }
    IOLog("K60CpuFreq: sample start every=%ums log-every=%u domains=%u apply=%u\n",
        kSampleSleepMs, kSampleLogWindows, K60_CPU_FREQ_DOMAINS, apply ? 1u : 0u);
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
        for (unsigned domain = 0; domain < K60_CPU_FREQ_DOMAINS; ++domain) {
            if (!ready[domain]) continue;
            busy[domain] = k60_cpufreq_domain_busy_elapsed(idle, elapsed,
                K60_CPU_FREQ_CPUS, domain);
            (void)k60_cpufreq_governor_window(&gov, &tables[domain], domain,
                busy[domain], 0, 0);
        }
        if (apply && !armed && window >= kApplyArmWindow) {
            for (unsigned domain = 0; domain < K60_CPU_FREQ_DOMAINS; ++domain) {
                if (!ready[domain] || !applyReady[domain]) continue;
                if (gov.current[domain] >= votedIndex[domain]) continue;
                armed = true;
                applyStart = window;
                IOLog("K60CpuFreq: mode7 armed win=%llu d%u level=%u\n",
                    static_cast<unsigned long long>(window), domain,
                    tables[domain].level[gov.current[domain]]);
                break;
            }
        }
        if (apply) {
            for (unsigned domain = 0; domain < K60_CPU_FREQ_DOMAINS; ++domain) {
                K60CpuFreqWrite set[K60_CPU_FREQ_MAX_WRITES] = {};
                uint32_t readback[K60_CPU_FREQ_MAX_WRITES] = {};
                uint32_t before, after;
                unsigned n, i;
                bool ok;

                if (!ready[domain] || !applyReady[domain] || restored) continue;
                if (gov.current[domain] > votedIndex[domain]) {
                    /* Raising needs the rail/thermal ordering section 5 still
                     * lacks; keep the governor honest about what is set. */
                    gov.current[domain] = votedIndex[domain];
                    if (!raiseLogged[domain]) {
                        IOLog("K60CpuFreq: mode7 d%u raise refused; no voltage ordering yet\n", domain);
                        raiseLogged[domain] = true;
                    }
                    continue;
                }
                if (gov.current[domain] == votedIndex[domain]) continue;
                if (!armed || window < applyStart || window > applyStart + kApplySpanWindows ||
                    window > kApplyLatestEndWindow || appliedVotes >= kApplyMaxVotes) continue;
                n = k60_cpufreq_build_votes(domain, dcvsCtrl[domain],
                    tables[domain].level[gov.current[domain]], set, K60_CPU_FREQ_MAX_WRITES);
                if (!k60_cpufreq_vote_allowed(rd32(windows[domain].va,
                        K60_CPU_FREQ_REG_ENABLE) & 1u, &tables[domain],
                        tables[domain].level[gov.current[domain]], n)) {
                    gov.current[domain] = votedIndex[domain];
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
                }
                for (i = 0; i < n; ++i) wr32(windows[domain].va, set[i].offset, set[i].value);
                for (i = 0; i < n; ++i) readback[i] = rd32(windows[domain].va, set[i].offset);
                ok = k60_cpufreq_check_readback(set, readback, n) != 0;
                ++appliedVotes;
                IOSleep(1);
                after = rd32(windows[domain].va, K60_CPU_FREQ_REG_DOMAIN_STATE) & 0xffu;
                IOLog("K60CpuFreq: mode7 apply d%u level=%u (%ukHz) busy=%u writes=%u readback=%s state=%u->%u\n",
                    domain, tables[domain].level[gov.current[domain]],
                    tables[domain].khz[gov.current[domain]], busy[domain], n,
                    ok ? "ok" : "mismatch", before, after);
                if (!ok) {
                    for (i = 0; i < n; ++i)
                        wr32(windows[domain].va, set[i].offset, applied[domain].originals[i]);
                    applied[domain].touched = false;
                    applyReady[domain] = false;
                    gov.current[domain] = votedIndex[domain];
                } else {
                    votedIndex[domain] = gov.current[domain];
                }
            }
            if (!restored && armed && (window >= applyStart + kApplySpanWindows ||
                    window >= kApplyLatestEndWindow || appliedVotes >= kApplyMaxVotes)) {
                unsigned domains = restoreApplied(windows, applied);
                IOLog("K60CpuFreq: mode7 restore domains=%u votes=%u\n", domains, appliedVotes);
                restored = true;
            }
        }
        if ((window % kSampleLogWindows) == 0) {
            uint32_t hardware[K60_CPU_FREQ_DOMAINS] = {};
            for (unsigned domain = 0; domain < K60_CPU_FREQ_DOMAINS; ++domain)
                if (ready[domain])
                    hardware[domain] = (rd32(windows[domain].va,
                        K60_CPU_FREQ_REG_DOMAIN_STATE) & 0xffu) * K60_CPU_FREQ_XO_KHZ;
            IOLog("K60CpuFreq: sample win=%llu d0=%u/%ukHz/hw%ukHz d1=%u/%ukHz/hw%ukHz d2=%u/%ukHz/hw%ukHz\n",
                static_cast<unsigned long long>(window),
                busy[0], tables[0].khz[gov.current[0]], hardware[0],
                busy[1], tables[1].khz[gov.current[1]], hardware[1],
                busy[2], tables[2].khz[gov.current[2]], hardware[2]);
        }
    }
    if (apply && !restored) {
        unsigned domains = restoreApplied(windows, applied);
        IOLog("K60CpuFreq: mode7 restore domains=%u votes=%u\n", domains, appliedVotes);
    }
    for (unsigned domain = 0; domain < K60_CPU_FREQ_DOMAINS; ++domain)
        if (windows[domain].map) unmapWindow(&windows[domain]);
    IOLog("K60CpuFreq: sample stop win=%llu\n", static_cast<unsigned long long>(window));
}

void startSampler(bool apply)
{
    thread_t thread = nullptr;

    if (__atomic_exchange_n(&sSampleStarted, 1u, __ATOMIC_ACQ_REL)) return;
    sSampleStop = 0;
    sSampleApply = apply ? 1u : 0u;
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
    if (mode == 4 || mode > 7) {
        IOLog("K60CpuFreq: mode=%u ignored; modes 1-3, 5, 6 and 7 are implemented\n", mode);
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
    if (mode == 5) {
        probeAll(false);
        startSampler(false);
        return;
    }
    if (mode == 7) {
        probeAll(false);
        startSampler(true);
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
