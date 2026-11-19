/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Memshare, service 0x34 instance 1 on port 0x101.

 * Pong registers three services to the modem before pas4: the servloc
 * locator (0x40/0x101), heap memory share (0x34/0x101) and storage (14/1).
 * The memory share is how the modem asks the AP for a contiguous region and
 * how it hands it back; the transfer itself is the SCM 0x0c/0x16 ownership
 * call this branch already carries in K60ModemPas.h.

 * The wire shapes follow references/pong-baseband/PongModemMemshare.h: a QMI
 * v1 request (type 0), seven byte header, little endian TLVs.  A query (0x24)
 * reports the client limit, an allocate (0x22) asks for bytes and answers with
 * a sequence number plus a 13 byte extent, and a free (0x23) hands back an
 * extent that must match the one still held.  Rejections use QMI error 48
 * (invalid argument), 2 (no memory), 3 (ownership transfer failed) or 71
 * (message not supported), exactly as the reference does.
 */
#ifndef K60_MODEM_MEMSHARE_H
#define K60_MODEM_MEMSHARE_H

#include <stddef.h>
#include <stdint.h>

#define K60_MEMSHARE_SERVICE            0x34u
#define K60_MEMSHARE_INSTANCE           1u
#define K60_MEMSHARE_PORT               0x101u

#define K60_MEMSHARE_QUERY              0x24u
#define K60_MEMSHARE_ALLOCATE           0x22u
#define K60_MEMSHARE_FREE               0x23u

#define K60_MEMSHARE_MAXIMUM            0x500000u   /* five megabytes */
#define K60_MEMSHARE_ALIGNMENT_LIMIT    11u
#define K60_MEMSHARE_CLIENT             1u
#define K60_MEMSHARE_CLIENT_LIMIT       2u
#define K60_MEMSHARE_EXTENT_BYTES       13u
#define K60_MEMSHARE_EXTENT_VERSION     1u

#define K60_MEMSHARE_ERROR_NONE         0u
#define K60_MEMSHARE_ERROR_NO_MEMORY    2u
#define K60_MEMSHARE_ERROR_TRANSFER     3u
#define K60_MEMSHARE_ERROR_ARGUMENT     48u
#define K60_MEMSHARE_ERROR_UNSUPPORTED  71u

enum {
	K60MemshareOk = 0,
	K60MemshareBadArgument = -1,
	K60MemshareMalformed = -2,
};

typedef struct {
	uint16_t message;
	uint16_t transaction;
	uint32_t client;
	uint32_t processor;
	uint32_t sequence;
	uint32_t bytes;             /* allocate: the size asked for */
	uint32_t alignment;
	uint64_t physical;          /* free: the extent handed back */
	uint32_t extent_bytes;
	uint32_t error;             /* non zero: answer with this code, not memory */
} K60MemshareRequest;

/* Parses one request.  The protocol rejections the reference decides while
 * parsing (wrong client, a processor id, a bad alignment, an extent that does
 * not match the shape) are reported in out->error with a zero return, so the
 * caller answers with that code instead of allocating.  A malformed header or
 * a missing required TLV is K60MemshareMalformed. */
int k60_memshare_parse(const void *bytes, size_t length, K60MemshareRequest *out);

/* Builds the response.  error is one of the codes above; a successful query
 * carries the client limit, a successful allocate carries the sequence and the
 * extent, and nothing else carries a value TLV.  Returns the message length or
 * zero when the buffer is too small. */
size_t k60_memshare_build_reply(uint8_t *out, size_t capacity,
    uint16_t transaction, uint16_t message, uint32_t error, uint32_t maximum,
    const uint32_t *sequence, uint64_t physical, uint32_t bytes);

/* Rounding and bounds the reference applies to a region before it is handed
 * over: 4096 byte pages, no zero length, and every page below the ceiling.
 * Returns 0 when the region is acceptable. */
int k60_memshare_region_ok(uint64_t physical, uint32_t bytes, uint64_t ceiling);

#endif
