// SPDX-License-Identifier: BSD-2-Clause-Patent
// What this driver does with a scan request while a network is joined, and with held records that have
// gone stale. The rules and their constants are the reference port's (sheng 27, package/WifiScanPolicy.h):
// they decide whether the radio is taken off channel during a join, and when a network that was not heard
// is allowed to leave the list the framework reads.
#ifndef PONG_WIFI_SCAN_POLICY_H
#define PONG_WIFI_SCAN_POLICY_H

#include <stdint.h>

#define PONG_SCAN_HELD_MS 60000u        // a network not heard for this long is not handed out
#define PONG_SCAN_LINK_SETTLE_MS 15000u // a scan in this window after the link came up stays off the air
#define PONG_SCAN_RESCAN_MS 20000u      // a channel scanned this recently is not scanned again
#define PONG_SCAN_AIR_CHANNELS 64u

enum { PONG_LINK_NONE, PONG_LINK_JOINING, PONG_LINK_UP };

// When each channel was last scanned on the air, in ms of a clock that starts above 0; 0: not yet.
struct pong_scan_air {
    uint64_t every_ms;                       // a scan that named no channel: every channel
    uint32_t mhz[PONG_SCAN_AIR_CHANNELS];
    uint64_t at_ms[PONG_SCAN_AIR_CHANNELS];
};

// A held network older than a minute is stale: its access point may be out of range.
static inline int pong_scan_held_stale(uint32_t age_ms) { return age_ms > PONG_SCAN_HELD_MS; }

// A scan of these channels (count 0: every channel) went on the air at now_ms. A channel beyond the
// places takes the oldest one.
static inline void pong_scan_air_mark(struct pong_scan_air *air, const uint32_t *mhz, unsigned count, uint64_t now_ms)
{
    if (!count) {
        air->every_ms = now_ms;
        return;
    }
    for (unsigned i = 0; i < count; ++i) {
        unsigned place = 0;
        for (unsigned slot = 0; slot < PONG_SCAN_AIR_CHANNELS; ++slot) {
            if (air->mhz[slot] == mhz[i]) {
                place = slot;
                break;
            }
            if (air->at_ms[slot] < air->at_ms[place]) place = slot;   // an empty place is the oldest
        }
        air->mhz[place] = mhz[i];
        air->at_ms[place] = now_ms;
    }
}

static inline int pong_scan_air_recent(uint64_t at_ms, uint64_t now_ms)
{
    return at_ms && now_ms >= at_ms && now_ms - at_ms < PONG_SCAN_RESCAN_MS;
}

// Whether a scan request goes on the air. link_ms: how long the link has been up; held: there are held
// networks to answer with; mhz, count: the channels asked for (count 0: every channel).
static inline int pong_scan_on_air(const struct pong_scan_air *air, int link, uint64_t link_ms, int held,
                                   const uint32_t *mhz, unsigned count, uint64_t now_ms)
{
    if (link == PONG_LINK_NONE || !held) return 1;
    if (link == PONG_LINK_JOINING || link_ms < PONG_SCAN_LINK_SETTLE_MS) return 0;
    if (pong_scan_air_recent(air->every_ms, now_ms)) return 0;
    if (!count) return 1;
    for (unsigned i = 0; i < count; ++i) {
        unsigned slot = 0;
        while (slot < PONG_SCAN_AIR_CHANNELS && air->mhz[slot] != mhz[i]) ++slot;
        if (slot == PONG_SCAN_AIR_CHANNELS || !pong_scan_air_recent(air->at_ms[slot], now_ms)) return 1;
    }
    return 0;
}
#endif
