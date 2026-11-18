/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* K60 IPA QMAP framing (M5 prerequisite, host-testable).
 *
 * The modem WAN path carries raw IP inside QMAP frames: a four-byte header
 * (pad length:6, reserved:1, command:1 | mux id | length:16 big-endian)
 * followed by the padded payload. The length field counts the payload and its
 * padding, NOT the header, and the padding sits at the end of the payload, so
 * the IP length is length - pad. Pong encodes it this way
 * (references/pong-baseband/PongModemWan.h:313-342) and parses it the same way
 * on receive; the PHK110 fork agrees (references/phk110-port/drivers/modem/
 * hakios.ipa.c:671-689, :710-733).
 *
 * WDA Set Data Format negotiates a DAP value (CBD_DAP_QMAP in
 * references/pong-baseband/PongModemData.h:67, CBD_DAP_QMAPV4=8 and
 * CBD_DAP_QMAP=5 in coachz_bb_data.h). That value selects aggregation and
 * checksum capabilities, not the data header: the four-byte header is the same
 * for QMAP and QMAPv4/v5 data packets. The checksum-offload variant is out of
 * scope here because the Pong data path advertises no AP checksum/NAT offload
 * (references/pong-baseband/PongModemRules.h:6); if the modem ever reports one,
 * the trailer belongs to the negotiation layer, and this codec must be revisited
 * rather than guessed at.
 *
 * Command frames (bit 7) carry MAP control information and are counted and
 * skipped; they are not IP payloads. A reserved bit, a zero length, a pad larger
 * than the length or a frame that runs past the buffer are framing errors: the
 * decoder drops that frame and stops, because resynchronising inside a corrupt
 * aggregate would deliver garbage to the network stack.
 */

#ifndef K60_IPA_QMAP_H
#define K60_IPA_QMAP_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define K60_IPA_QMAP_HEADER_BYTES   4u
#define K60_IPA_QMAP_ALIGN          4u
#define K60_IPA_QMAP_PAD_MASK       0x3fu
#define K60_IPA_QMAP_RESERVED_BIT   0x40u
#define K60_IPA_QMAP_COMMAND_BIT    0x80u
#define K60_IPA_QMAP_MUX_MIN        1u
#define K60_IPA_QMAP_MUX_MAX        254u
/* The length field is 16 bits and counts the padded payload. */
#define K60_IPA_QMAP_MAX_LENGTH     0xffffu

enum {
    K60IpaQmapOk = 0,
    K60IpaQmapBadArgument = -1,
    K60IpaQmapTooLong = -2,
};

typedef struct {
    uint32_t packets;   /* data frames delivered */
    uint32_t commands;  /* command frames skipped */
    uint32_t dropped;   /* frames refused: bad header, truncation or mux */
    uint64_t bytes;     /* payload bytes delivered, without padding */
} K60IpaQmapStats;

/* Called once per data frame with the mux id and the IP bytes. The payload
 * points into the caller's buffer and is valid only during the call. */
typedef void (*k60_ipa_qmap_receive)(void *context, uint8_t mux,
    const uint8_t *payload, size_t bytes);

/* Header, payload and trailing padding for a payload of this size. */
size_t k60_ipa_qmap_frame_bytes(size_t payload_bytes);

/* Build one frame at out. The payload is copied; out must not overlap it.
 * Rejects mux 0/255, an empty payload, a padded length above 0xffff and a
 * capacity too small for header + payload + padding. frame_bytes receives the
 * full frame length on success. */
int k60_ipa_qmap_encode(uint8_t mux, const void *payload, size_t bytes,
    void *out, size_t capacity, size_t *frame_bytes);

/* Decode a buffer holding one or more frames. Every data frame is passed to
 * receive (when non-NULL); stats may be NULL. Returns the number of data frames
 * delivered and records commands and dropped frames in stats. */
unsigned k60_ipa_qmap_decode(const void *frames, size_t bytes,
    k60_ipa_qmap_receive receive, void *context, K60IpaQmapStats *stats);

#ifdef __cplusplus
}
#endif

#endif /* K60_IPA_QMAP_H */
