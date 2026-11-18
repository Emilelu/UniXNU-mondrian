/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* K60 IPA QMAP framing; see K60IpaQmap.h for the wire layout and the sources.
 * Pure buffer movement, so the host test runs the same code as the kernel.
 */

#include "K60IpaQmap.h"

#ifdef K60_HOST_TEST
#include <string.h>
#else
#include <sys/systm.h>
#endif

_Static_assert(K60_IPA_QMAP_ALIGN == 4u, "QMAP padding aligns to four bytes");
_Static_assert(K60_IPA_QMAP_PAD_MASK == 0x3fu, "pad length occupies bits 5:0");

size_t
k60_ipa_qmap_frame_bytes(size_t payload_bytes)
{
    const size_t padding = (K60_IPA_QMAP_ALIGN -
        (payload_bytes % K60_IPA_QMAP_ALIGN)) % K60_IPA_QMAP_ALIGN;

    return K60_IPA_QMAP_HEADER_BYTES + payload_bytes + padding;
}

int
k60_ipa_qmap_encode(uint8_t mux, const void *payload, size_t bytes, void *out,
    size_t capacity, size_t *frame_bytes)
{
    const uint8_t *from = payload;
    uint8_t *to = out;
    size_t padding;
    size_t length;
    size_t total;

    if (from == NULL || to == NULL || frame_bytes == NULL || bytes == 0 ||
        bytes > K60_IPA_QMAP_MAX_LENGTH || mux < K60_IPA_QMAP_MUX_MIN ||
        mux > K60_IPA_QMAP_MUX_MAX) {
        return K60IpaQmapBadArgument;
    }
    padding = (K60_IPA_QMAP_ALIGN - (bytes % K60_IPA_QMAP_ALIGN)) %
        K60_IPA_QMAP_ALIGN;
    length = bytes + padding;
    if (length > K60_IPA_QMAP_MAX_LENGTH) {
        return K60IpaQmapTooLong;
    }
    total = K60_IPA_QMAP_HEADER_BYTES + length;
    if (total > capacity) {
        return K60IpaQmapTooLong;
    }

    to[0] = (uint8_t)padding;
    to[1] = mux;
    to[2] = (uint8_t)(length >> 8);
    to[3] = (uint8_t)length;
    memcpy(to + K60_IPA_QMAP_HEADER_BYTES, from, bytes);
    (void)memset(to + K60_IPA_QMAP_HEADER_BYTES + bytes, 0, padding);
    *frame_bytes = total;
    return K60IpaQmapOk;
}

unsigned
k60_ipa_qmap_decode(const void *frames, size_t bytes, k60_ipa_qmap_receive receive,
    void *context, K60IpaQmapStats *stats)
{
    const uint8_t *frame = frames;
    K60IpaQmapStats local;
    size_t at = 0;
    unsigned delivered = 0;
    int stopped = 0;

    local.packets = 0;
    local.commands = 0;
    local.dropped = 0;
    local.bytes = 0;

    if (frame == NULL) {
        if (stats != NULL) {
            *stats = local;
        }
        return 0;
    }

    while (at + K60_IPA_QMAP_HEADER_BYTES <= bytes) {
        const size_t header = at;
        const uint8_t pad = (uint8_t)(frame[header] & K60_IPA_QMAP_PAD_MASK);
        const uint8_t mux = frame[header + 1];
        const size_t length = ((size_t)frame[header + 2] << 8) |
            (size_t)frame[header + 3];
        const int command = (frame[header] & K60_IPA_QMAP_COMMAND_BIT) != 0;
        const int reserved = (frame[header] & K60_IPA_QMAP_RESERVED_BIT) != 0;

        if (length == 0 || pad > length ||
            at + K60_IPA_QMAP_HEADER_BYTES + length > bytes || reserved) {
            local.dropped++;
            stopped = 1;
            break;
        }
        if (command) {
            local.commands++;
        } else if (mux < K60_IPA_QMAP_MUX_MIN || mux > K60_IPA_QMAP_MUX_MAX) {
            local.dropped++;
        } else {
            const size_t payload = length - pad;

            if (payload != 0 && receive != NULL) {
                receive(context, mux,
                    frame + header + K60_IPA_QMAP_HEADER_BYTES, payload);
            }
            local.packets++;
            local.bytes += payload;
            delivered++;
        }
        at += K60_IPA_QMAP_HEADER_BYTES + length;
    }
    if (!stopped && at != bytes) {
        local.dropped++;
    }
    if (stats != NULL) {
        *stats = local;
    }
    return delivered;
}
