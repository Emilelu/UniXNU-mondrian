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
