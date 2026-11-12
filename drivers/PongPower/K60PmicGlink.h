/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#ifndef K60_PMIC_GLINK_H
#define K60_PMIC_GLINK_H
#include <IOKit/IOMemoryDescriptor.h>
#include "K60BatteryConfig.h"
#include "K60Smem.h"
#include "QcomGlink.h"

/* Every method and callback is serialized by the battery's workloop. No DSP
 * startup, APSS FIFO reset, charger-control writes, synthetic callback or RX
 * snapshot. Native GLINK messages use the actual hardware-shared FIFOs. */
class K60PmicGlink {
public:
    struct Client {
        void (*state)(void *, bool);
        void (*receive)(void *, const uint8_t *, unsigned);
    };
    bool open(const K60BatteryConfig &, const K60AdspGlinkHandoff &, const Client &, void *);
    void close();
    int poll();
    int send(const uint8_t *, unsigned);
    bool reopen();
    bool ready() const { return channel && channel->up && !native.broken; }
    bool alive() const { return opened && !native.broken; }
    uint32_t received() const { return native.rx_messages; }
    uint32_t transmitted() const { return native.tx_messages; }
    uint64_t epoch() const { return lease.epoch; }
    int lastError() const { return error; }
private:
    struct Mapping { IOMemoryMap *map = nullptr; volatile uint8_t *va = nullptr; size_t bytes = 0; };
    Mapping smemWindow, mutexWindow, ipccWindow;
    K60BatteryConfig config = {};
    K60AdspGlinkHandoff lease = {};
    K60Smem smem = {};
    K60SmemPartition partition = {};
    QcomGlink native = {};
    QcomGlinkChannel *channel = nullptr;
    volatile uint32_t *remoteState = nullptr;
    uint32_t remoteStateBytes = 0;
    Client client = {};
    void *context = nullptr;
    uint8_t intents[4 * 256] = {};
    bool opened = false;
    int error = 0;
    bool map(Mapping &, uint64_t, size_t);
    void unmap(Mapping &);
    bool lockSmem();
    void unlockSmem();
    bool discover();
    bool remoteReady() const;
    void revoke(int);
    static void kick(void *);
    static void channelState(void *, QcomGlinkChannel *, int);
    static void channelReceive(void *, QcomGlinkChannel *, const uint8_t *, uint32_t);
};
#endif
