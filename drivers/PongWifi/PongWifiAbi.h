/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* The wireless-framework record shapes this driver can serve, and the
 * association event the newer one expects.
 *
 *  22H374 / 20G81 (iOS 16.6.1): a scan result is 1164 bytes, 1024 element
 *    bytes at 0x8c; the daemon asks for exactly that many bytes.
 *  24A446 (iPadOS 27.0.1): a scan result is 0x8e8 (2280) bytes, 2048 element
 *    bytes at 0x8c, 68 filler bytes, the timestamp at 0x8d0 and 16 trailing
 *    bytes. The association completion event is 540 bytes, with the result at
 *    0x214 and its validity flag at 0x218.
 *
 * The prefix through 0x8c is identical, so ONE 0x8e8 record serves both: the
 * framework asks for the byte count it knows and the answer is truncated to
 * the request. Only the element count has to follow the request, because a
 * client that asked for 1164 bytes must not read elements_length bytes past
 * what it received.
 *
 * Sizes and offsets are the ones the sheng port records for iPadOS 27.0.1
 * (board os_profile "ipados-27.0.1-24A446"). A build against a different
 * framework generation is meant to fail the static asserts below, not to
 * serve a record the daemon misreads. */
#ifndef PONG_WIFI_ABI_H
#define PONG_WIFI_ABI_H
#include <stddef.h>
#include <stdint.h>
#include <string.h>

/* Scan results. */
#define PONG_SCAN_RECORD_22H374 1164u
#define PONG_SCAN_RECORD_24A446 0x8e8u
#define PONG_SCAN_ELEMENTS_OFFSET 0x8cu
#define PONG_SCAN_ELEMENTS_BYTES 2048u
#define PONG_SCAN_TIMESTAMP_OFFSET 0x8d0u

/* Association requests. The fields this driver reads sit at the same offsets
 * in the 22H374 and 24A446 layouts; only the trailing remainder differs. */
#define PONG_ASSOC_REQUEST_LEGACY 0x250u
#define PONG_ASSOC_REQUEST_24A446 0x290u
#define PONG_ASSOC_REQUEST_22H374 0x384u
#define PONG_ASSOC_FIELDS_BYTES 0x8cu   /* through key[64] */

/* How many element bytes a scan request of request_bytes has room for. */
static inline uint32_t pong_scan_elements_room(uint32_t request_bytes)
{
    if (request_bytes <= PONG_SCAN_ELEMENTS_OFFSET) return 0;
    const uint32_t room = request_bytes - PONG_SCAN_ELEMENTS_OFFSET;
    return room < PONG_SCAN_ELEMENTS_BYTES ? room : PONG_SCAN_ELEMENTS_BYTES;
}

/* 24A446 _dispatchAsyncAssocEvent reads ten 52-byte AP records followed by
 * the result at 0x214 and its validity flag at 0x218. An empty event is
 * unsafe: the framework dereferences the result without checking the length
 * it received. */
struct pong_assoc_event27 {
    uint8_t attempts[10 * 52];
    uint32_t reserved[2];
    uint32_t reason, result, has_result;
};

/* Card capabilities (request 12). 24A446 reads two bits that decide whether a scan reaches
 * the driver at all: 22 (byte 2 bit 6) lets a scan that NAMES networks through - without it
 * such a scan fails at once with -3903 in Apple80211Scan - and 46 (byte 5 bit 6) makes the
 * framework wait for the scan-done event instead of reading the results at once. */
#define PONG_WIFI_CAPS_BYTES 12u
#define PONG_WIFI_CAP_NAMED_SCAN 22u
#define PONG_WIFI_CAP_SCAN_DONE_EVENT 46u

static inline void pong_wifi_caps_fill(uint8_t caps[PONG_WIFI_CAPS_BYTES])
{
    /* AES, AES-CCM, power management, short slot and preamble, WPA2, WME, short guard
     * interval at 20 MHz, then the two scan bits above. */
    static const uint8_t has[] = { 2, 3, 6, 9, 10, 14, 17, 19,
                                   PONG_WIFI_CAP_NAMED_SCAN, PONG_WIFI_CAP_SCAN_DONE_EVENT };
    unsigned i;
    for (i = 0; i < PONG_WIFI_CAPS_BYTES; ++i) caps[i] = 0;
    for (i = 0; i < sizeof has; ++i) caps[has[i] / 8] |= (uint8_t)(1u << (has[i] % 8));
}

/* Scan request 86: the networks to probe by name. 0x8 the number of entries, 0xc the entries
 * (40 bytes each: version, length, 32 name bytes), 0x200 the scan type (3: answer with the
 * results already held), 0x210/0x214 the channels. airportd sends it for a saved network it
 * counts as hidden; a scan that only names networks cannot find one that does not broadcast. */
#define PONG_SCAN_MULTIPLE_BYTES 0x14e8u
#define PONG_SCAN_REQUEST_MAX 0x14e8u   /* the ioctl path accepts the largest request it may see */
#define PONG_SCAN_SSID_COUNT 0x8u
#define PONG_SCAN_SSIDS 0xcu
#define PONG_SCAN_SSID_ENTRY 40u
#define PONG_SCAN_SSID_MAX 10u    /* nine names and the wildcard */
#define PONG_SCAN_TYPE 0x200u
#define PONG_SCAN_TYPE_CACHED 3u

/* Channels a scan asks for, in both request shapes: 12 bytes each {version, channel, flags}. */
#define PONG_SCAN_ONE_CHANNEL_COUNT 0x44u
#define PONG_SCAN_ONE_CHANNELS 0x48u
#define PONG_SCAN_MULTIPLE_CHANNEL_COUNT 0x210u
#define PONG_SCAN_MULTIPLE_CHANNELS 0x214u
#define PONG_SCAN_CHANNEL_ENTRY 12u
#define PONG_SCAN_CHANNELS_READ 64u
#define PONG_SCAN_FREQUENCIES_MAX 32u
#define PONG_SCAN_CHANNEL_2GHZ 0x8u
#define PONG_SCAN_CHANNEL_5GHZ 0x10u

static inline uint32_t pong_scan_u32(const uint8_t *at)
{
    uint32_t v;
    memcpy(&v, at, 4);
    return v;
}

/* 0 when the request was understood, -1 when it is shorter than its scan type, names more than
 * PONG_SCAN_SSID_MAX networks or a name longer than 32 bytes. On success the radio probes for
 * the one name when exactly one was given and no wildcard, and for every network otherwise. */
static inline int pong_scan_multiple_parse(const uint8_t *req, uint32_t size, uint32_t *scan_type,
                                           const uint8_t **ssid, uint32_t *ssid_length)
{
    uint32_t count, i, named = 0, wildcard = 0;
    const uint8_t *only = 0;
    uint32_t only_length = 0;
    *scan_type = 0; *ssid = 0; *ssid_length = 0;
    if (!req || size < PONG_SCAN_TYPE + 4u) return -1;
    count = pong_scan_u32(req + PONG_SCAN_SSID_COUNT);
    if (count > PONG_SCAN_SSID_MAX) return -1;
    if (size < PONG_SCAN_SSIDS + count * PONG_SCAN_SSID_ENTRY) return -1;
    for (i = 0; i < count; ++i) {
        const uint8_t *entry = req + PONG_SCAN_SSIDS + i * PONG_SCAN_SSID_ENTRY;
        const uint32_t length = pong_scan_u32(entry + 4);
        if (length > 32) return -1;
        if (!length) { wildcard = 1; continue; }
        only = entry + 8; only_length = length; ++named;
    }
    *scan_type = pong_scan_u32(req + PONG_SCAN_TYPE);
    if (named == 1 && !wildcard) { *ssid = only; *ssid_length = only_length; }
    return 0;
}

/* MHz of a channel this driver reports, 0 for another band. */
static inline uint32_t pong_scan_channel_mhz(uint32_t channel, uint32_t flags)
{
    if (flags & PONG_SCAN_CHANNEL_2GHZ)
        return channel == 14 ? 2484 : (channel >= 1 && channel <= 13 ? 2407 + 5 * channel : 0);
    if (flags & PONG_SCAN_CHANNEL_5GHZ)
        return channel >= 1 && channel <= 196 ? 5000 + 5 * channel : 0;
    return 0;
}

/* The distinct frequencies a scan asks for, in order, into mhz; 0 for every band: no list, no
 * channel this driver reports, more entries than PONG_SCAN_CHANNELS_READ, more distinct
 * frequencies than PONG_SCAN_FREQUENCIES_MAX, or a list past the bytes copied. */
static inline uint32_t pong_scan_frequencies(const uint8_t *req, uint32_t size, uint32_t count_at,
                                             uint32_t list_at, uint32_t mhz[PONG_SCAN_FREQUENCIES_MAX])
{
    uint32_t count, i, n = 0;
    if (!req || size < count_at + 4u) return 0;
    count = pong_scan_u32(req + count_at);
    if (!count || count > PONG_SCAN_CHANNELS_READ) return 0;
    if (size < list_at + count * PONG_SCAN_CHANNEL_ENTRY) return 0;
    for (i = 0; i < count; ++i) {
        const uint8_t *entry = req + list_at + i * PONG_SCAN_CHANNEL_ENTRY;
        const uint32_t f = pong_scan_channel_mhz(pong_scan_u32(entry + 4), pong_scan_u32(entry + 8));
        uint32_t k, seen = 0;
        if (!f) continue;
        for (k = 0; k < n; ++k) seen |= mhz[k] == f;
        if (seen) continue;
        if (n == PONG_SCAN_FREQUENCIES_MAX) return 0;
        mhz[n++] = f;
    }
    return n;
}

#if defined(__cplusplus)
static_assert(sizeof(struct pong_assoc_event27) == 540 &&
              offsetof(struct pong_assoc_event27, result) == 0x214 &&
              offsetof(struct pong_assoc_event27, has_result) == 0x218,
              "24A446 association event");
#else
_Static_assert(sizeof(struct pong_assoc_event27) == 540,
               "24A446 association event size");
_Static_assert(offsetof(struct pong_assoc_event27, result) == 0x214,
               "24A446 association event result offset");
_Static_assert(offsetof(struct pong_assoc_event27, has_result) == 0x218,
               "24A446 association event validity offset");
#endif
#endif
