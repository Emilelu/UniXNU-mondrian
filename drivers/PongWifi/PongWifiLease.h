/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#ifndef PONG_WIFI_LEASE_H
#define PONG_WIFI_LEASE_H
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>

#define PONG_WIFI_GET_LEASE 0x50574c01
#define PONG_WIFI_TEST_RECONNECT 0x50574c02
#define PONG_WIFI_LEASE_VERSION 2
#define PONG_WIFI_LEASE_DNS_MAX 4

struct pong_wifi_lease {
    uint32_t version, dns_count, lease_seconds, reserved;
    uint64_t link, sequence;
    uint8_t address[4], mask[4], router[4], dns[PONG_WIFI_LEASE_DNS_MAX][4];
};

static inline unsigned pong_wifi_be16(const uint8_t *p) { return (p[0] << 8) | p[1]; }

/* Shared parser for the live DHCP witness. It returns only the fields used to
 * restore native publication. It does not change, accept, or transmit packets. */
static inline unsigned pong_wifi_dhcp_fields(const uint8_t *b, size_t n,
    const uint8_t mac[6], struct pong_wifi_lease *lease)
{
    if (n < 241 || b[1] != 1 || b[2] != 6 || memcmp(b + 28, mac, 6) ||
        memcmp(b + 236, "\x63\x82\x53\x63", 4)) return 0;
    unsigned type = 0;
    bool end = false, classless = false, mask = false, router = false;
    struct pong_wifi_lease result = {};
    memcpy(result.address, b + 16, 4);
    for (size_t i = 240; i < n;) {
        const unsigned code = b[i++];
        if (!code) continue;
        if (code == 255) { end = true; break; }
        if (i == n) return 0;
        const unsigned len = b[i++];
        if (len > n - i) return 0;
        if (code == 53 && len == 1) type = b[i];
        if (code == 51 && len == 4)
            result.lease_seconds = ((uint32_t)b[i] << 24) | ((uint32_t)b[i + 1] << 16) |
                                   ((uint32_t)b[i + 2] << 8) | b[i + 3];
        if (code == 121 || code == 249) classless = true;
        if (code == 1 && len == 4) { memcpy(result.mask, b + i, 4); mask = true; }
        if (code == 3 && len >= 4 && len % 4 == 0) { memcpy(result.router, b + i, 4); router = true; }
        if (code == 6 && len % 4 == 0)
            for (unsigned j = 0; j < len && result.dns_count < PONG_WIFI_LEASE_DNS_MAX; j += 4)
                memcpy(result.dns[result.dns_count++], b + i + j, 4);
        i += len;
    }
    if (!end) return 0;
    if (type == 5 && b[0] == 2 && !classless && mask && router && result.dns_count && result.lease_seconds) {
        result.version = PONG_WIFI_LEASE_VERSION;
        *lease = result;
    }
    return type;
}
struct pong_wifi_lease_tracker {
    struct pong_wifi_lease current;
    uint64_t link, sequence, expires, request_until;
    uint8_t xid[4];
    bool up, requested;
};

static inline void pong_wifi_lease_link(struct pong_wifi_lease_tracker *t, bool up)
{
    if (up != t->up) ++t->link;
    t->up = up;
    t->requested = false;
    t->current.version = 0;
}

static inline void pong_wifi_lease_packet(struct pong_wifi_lease_tracker *t,
    bool out, unsigned type, const uint8_t *bootp, const struct pong_wifi_lease *ack, uint64_t seconds)
{
    if (!t->up) return;
    if (out && bootp[0] == 1) {
        if (type == 3) {
            memcpy(t->xid, bootp + 4, 4);
            t->request_until = seconds + 120;
            t->requested = true;
        } else if (type == 4 || type == 7) {
            t->current.version = 0;
            t->requested = false;
        }
    } else if (!out && bootp[0] == 2 && (type == 5 || type == 6) &&
               t->requested && seconds < t->request_until && !memcmp(t->xid, bootp + 4, 4)) {
        t->requested = false;
        t->current = *ack;
        t->current.sequence = ++t->sequence;
        t->expires = seconds + ack->lease_seconds;
    }
}

static inline struct pong_wifi_lease pong_wifi_lease_snapshot(const struct pong_wifi_lease_tracker *t, uint64_t seconds)
{
    struct pong_wifi_lease s = {};
    s.link = t->link;
    if (t->up && t->current.version && seconds < t->expires) {
        s = t->current;
        s.link = t->link;
    }
    return s;
}
#endif
