/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* Physical resource/SMEM/IPCC glue. Discovery never creates/reset SMEM items.
 * Main's PAS1 owner must provide the exclusive fresh authenticated lease; an
 * Android rpmsg path, current reading or an enable boot argument is no lease. */
#include <IOKit/IOLib.h>
#include <IOKit/IOPlatformExpert.h>
#include <kern/clock.h>
#include <libkern/c++/OSSharedPtr.h>
#include "K60PmicGlink.h"
extern "C" { extern unsigned long gPhysBase, gPhysSize; }

namespace {
constexpr uint32_t kSmp2pMagic = 0x504d5324u;
constexpr uint32_t kIpccSend = 0x0c;
uint64_t microseconds()
{
    clock_sec_t seconds; clock_usec_t fraction;
    clock_get_system_microtime(&seconds, &fraction);
    return uint64_t(seconds) * 1000000 + fraction;
}
}

bool K60PmicGlink::map(Mapping &m, uint64_t physical, size_t bytes)
{
    OSSharedPtr<IOMemoryDescriptor> memory(IOMemoryDescriptor::withPhysicalAddress(
        physical, bytes, kIODirectionInOut), OSNoRetain);
    if (memory) m.map = memory->map(kIOMapAnywhere | kIOMapInhibitCache);
    if (!m.map) return false;
    m.va = reinterpret_cast<volatile uint8_t *>(m.map->getVirtualAddress()); m.bytes = bytes;
    return m.va != nullptr;
}
void K60PmicGlink::unmap(Mapping &m)
{
    if (m.map) m.map->release();
    m = {};
}
bool K60PmicGlink::lockSmem()
{
    auto mutex = reinterpret_cast<volatile uint32_t *>(mutexWindow.va);
    const uint64_t began = microseconds();
    do {
        *mutex = 1; /* Qualcomm TCSR APSS processor owner ID, not a SW lock. */
        __asm__ volatile("dsb sy" ::: "memory");
        if (*mutex == 1) {__asm__ volatile("dmb osh" ::: "memory"); return true;}
        IODelay(10);
    } while (microseconds() - began < 1000);
    return false;
}
void K60PmicGlink::unlockSmem()
{
    auto mutex = reinterpret_cast<volatile uint32_t *>(mutexWindow.va);
    __asm__ volatile("dmb osh" ::: "memory");
    if (*mutex == 1) *mutex = 0;
    __asm__ volatile("dsb sy" ::: "memory");
}
bool K60PmicGlink::discover()
{
    if (!lockSmem()) {error = -20; return false;}
    int rc = k60_smem_partition(&smem, 0, uint16_t(config.remote_pid), &partition);
    const uint32_t ids[] = {config.desc_item, config.tx_item, config.rx_item, config.smp2p_item};
    uint32_t offsets[4] = {}, sizes[4] = {};
    for (unsigned i = 0; !rc && i < 4; ++i)
        rc = k60_smem_find(&smem, &partition, uint16_t(ids[i]), &offsets[i], &sizes[i]);
    unlockSmem();
    if (rc) {error = rc; return false;}
    if (offsets[0] != lease.desc_offset || sizes[0] != lease.desc_bytes ||
        offsets[1] != lease.tx_offset || sizes[1] != lease.tx_bytes ||
        offsets[2] != lease.rx_offset || sizes[2] != lease.rx_bytes ||
        (offsets[3] & 3) || sizes[3] < 20 || sizes[3] > 340) {error = -21; return false;}
    remoteState = reinterpret_cast<volatile uint32_t *>(smemWindow.va + offsets[3]);
    remoteStateBytes = sizes[3];
    if (!remoteReady()) {error = -22; return false;}
    auto desc = reinterpret_cast<volatile uint32_t *>(smemWindow.va + offsets[0]);
    /* APSS head/remote tail and remote head/APSS tail use the descriptor's
     * native order. The platform lease is checked against both SMEM lookup
     * and the live APSS-owned indices, without resetting a single word. */
    if (desc[1] != lease.host_tx_head || desc[2] != lease.host_rx_tail) {error = -23; return false;}
    const QcomGlinkFifo tx = {&desc[1], &desc[0], smemWindow.va + offsets[1], sizes[1]};
    const QcomGlinkFifo rx = {&desc[3], &desc[2], smemWindow.va + offsets[2], sizes[2]};
    rc = qcom_glink_adopt(&native, tx, rx, kick, this);
    if (rc) {error = rc; return false;}
    const QcomGlinkClient callbacks = {channelState, channelReceive};
    channel = qcom_glink_channel(&native, "PMIC_RTR_ADSP_APPS", 256, 4, intents, &callbacks, this, 1);
    if (!channel) {error = -24; return false;}
    return true;
}
bool K60PmicGlink::remoteReady() const
{
    if (!remoteState || remoteState[0] != kSmp2pMagic || (remoteState[1] & 255) != 1 ||
        remoteState[2] != config.remote_pid) return false;
    const uint32_t count = remoteState[3], total = count & 65535, valid = count >> 16;
    __asm__ volatile("dmb osh" ::: "memory");
    if (total > 16 || valid > total || uint64_t(20) + uint64_t(valid) * 20 > remoteStateBytes ||
        (remoteState[4] & 1) != lease.remote_restart_flag) return false;
    static const char name[16] = "slave-kernel";
    for (uint32_t i = 0; i < valid; ++i) {
        bool same = true;
        for (uint32_t word = 0; word < 4; ++word) {
            const uint32_t got = remoteState[5 + i * 5 + word];
            for (unsigned byte = 0; byte < 4; ++byte)
                if (uint8_t(got >> (byte * 8)) != uint8_t(name[word * 4 + byte])) same = false;
        }
        if (!same) continue;
        const uint32_t state = remoteState[5 + i * 5 + 4];
        return (state & 2) != 0 && !(state & 1); /* ready, not fatal */
    }
    return false;
}
bool K60PmicGlink::open(const K60BatteryConfig &c, const K60AdspGlinkHandoff &h, const Client &callbacks, void *owner)
{
    if (opened || !callbacks.state || !callbacks.receive || !owner || h.flags != K60AdspHandoffRequired || !h.epoch)
        return false;
    config = c; lease = h; client = callbacks; context = owner;
    if (k60_battery_range_overlaps(config.smem_base, config.smem_bytes, gPhysBase, gPhysSize) ||
        k60_battery_range_overlaps(config.adsp_base, config.adsp_bytes, gPhysBase, gPhysSize)) {
        error = -25;
        IOLog("K60Battery: refusing DSP lease overlapping XNU-owned RAM base=%lx bytes=%lx\n", gPhysBase, gPhysSize);
        return false;
    }
    if (!map(smemWindow, config.smem_base, size_t(config.smem_bytes)) ||
        !map(mutexWindow, config.mutex_base, 4) || !map(ipccWindow, config.ipcc_base, 4096)) {
        error = -26; close(); return false;
    }
    smem = {smemWindow.va, uint32_t(config.smem_bytes)};
    if (!discover()) {close(); return false;}
    opened = true;
    IOLog("K60Battery: adopting authenticated PAS1 GLINK epoch=%llu desc=%x tx=%x/%x rx=%x/%x (no FIFO reset)\n",
        lease.epoch, lease.desc_offset, lease.tx_offset, lease.tx_bytes, lease.rx_offset, lease.rx_bytes);
    return true;
}
void K60PmicGlink::revoke(int rc)
{
    error = rc;
    qcom_glink_stop(&native);
}
void K60PmicGlink::close()
{
    /* stop() never touches physical FIFOs or sends a shutdown to PAS1. */
    qcom_glink_stop(&native);
    opened = false; channel = nullptr; remoteState = nullptr; remoteStateBytes = 0;
    unmap(ipccWindow); unmap(mutexWindow); unmap(smemWindow);
}
int K60PmicGlink::poll()
{
    if (!opened || native.broken) return QcomGlinkNotOpen;
    if (!remoteReady()) {revoke(-27); return QcomGlinkNotOpen;}
    const int rc = qcom_glink_poll(&native);
    if (rc < 0) error = rc;
    return rc;
}
int K60PmicGlink::send(const uint8_t *data, unsigned bytes)
{
    if (!opened || !channel || !remoteReady()) {revoke(-28); return QcomGlinkNotOpen;}
    return qcom_glink_send(&native, channel, data, bytes);
}
bool K60PmicGlink::reopen()
{
    if (!opened || !channel || !remoteReady()) {revoke(-29); return false;}
    return qcom_glink_reopen(&native, channel) == QcomGlinkOk;
}
void K60PmicGlink::kick(void *owner)
{
    auto self = static_cast<K60PmicGlink *>(owner);
    if (self->native.broken || !self->ipccWindow.va) return;
    const uint32_t id = self->config.ipcc_client << 16 | self->config.ipcc_signal;
    __asm__ volatile("dmb oshst" ::: "memory");
    *reinterpret_cast<volatile uint32_t *>(self->ipccWindow.va + kIpccSend) = id;
    __asm__ volatile("dsb sy" ::: "memory");
}
void K60PmicGlink::channelState(void *owner, QcomGlinkChannel *, int up)
{
    auto self = static_cast<K60PmicGlink *>(owner);
    self->client.state(self->context, up != 0);
}
void K60PmicGlink::channelReceive(void *owner, QcomGlinkChannel *, const uint8_t *data, uint32_t bytes)
{
    auto self = static_cast<K60PmicGlink *>(owner);
    self->client.receive(self->context, data, bytes);
}
