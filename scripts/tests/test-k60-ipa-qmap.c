/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Host test for the K60 IPA QMAP codec: frame sizes, encode, decode,
 * aggregation, command frames and every refused header shape. */

#include <stdio.h>
#include <string.h>

#include "K60IpaQmap.h"

static int failures;

static void
check(int condition, const char *name)
{
    if (!condition) {
        printf("FAIL %s\n", name);
        failures++;
    }
}

typedef struct {
    unsigned count;
    uint8_t mux[16];
    size_t bytes[16];
    uint8_t payload[16][1600];
} Recorded;

static void
record(void *context, uint8_t mux, const uint8_t *payload, size_t bytes)
{
    Recorded *r = context;
    unsigned index = r->count;

    if (index >= 16 || bytes > sizeof(r->payload[0])) {
        failures++;
        return;
    }
    r->mux[index] = mux;
    r->bytes[index] = bytes;
    memcpy(r->payload[index], payload, bytes);
    r->count++;
}

static size_t
expected_frame(size_t payload)
{
    return K60_IPA_QMAP_HEADER_BYTES + payload +
        (K60_IPA_QMAP_ALIGN - payload % K60_IPA_QMAP_ALIGN) %
        K60_IPA_QMAP_ALIGN;
}

static void
test_frame_bytes(void)
{
    static const size_t sizes[] = {0, 1, 3, 4, 5, 6, 7, 8, 1492};
    size_t i;

    for (i = 0; i < sizeof(sizes) / sizeof(sizes[0]); i++) {
        check(k60_ipa_qmap_frame_bytes(sizes[i]) == expected_frame(sizes[i]),
            "frame_bytes matches the padding rule");
    }
    check(k60_ipa_qmap_frame_bytes(1) == 8, "one byte pads to eight");
    check(k60_ipa_qmap_frame_bytes(4) == 8, "four bytes need no padding");
    check(k60_ipa_qmap_frame_bytes(5) == 12, "five bytes pad to twelve");
}

static void
test_encode(void)
{
    uint8_t payload[64];
    uint8_t frame[96];
    size_t bytes = 0;
    size_t total = 0;
    size_t i;

    for (i = 0; i < sizeof(payload); i++) {
        payload[i] = (uint8_t)(0x30 + i);
    }

    check(k60_ipa_qmap_encode(3, payload, 20, frame, sizeof(frame), &total) ==
        K60IpaQmapOk, "encode accepts a four-byte aligned payload");
    check(total == 24 && frame[0] == 0 && frame[1] == 3 &&
        frame[2] == 0 && frame[3] == 20, "header carries pad, mux and length");
    check(memcmp(frame + 4, payload, 20) == 0, "payload copied verbatim");

    memset(frame, 0xa5, sizeof(frame));
    check(k60_ipa_qmap_encode(4, payload, 21, frame, sizeof(frame), &total) ==
        K60IpaQmapOk, "encode accepts an unaligned payload");
    check(total == 28 && frame[0] == 3 && frame[1] == 4 && frame[2] == 0 &&
        frame[3] == 24, "unaligned header counts payload plus padding");
    check(memcmp(frame + 4, payload, 21) == 0, "unaligned payload copied");
    check(frame[25] == 0 && frame[26] == 0 && frame[27] == 0,
        "padding is zeroed");
    check(frame[28] == 0xa5, "encode does not write past the frame");

    check(k60_ipa_qmap_encode(0, payload, 20, frame, sizeof(frame), &total) ==
        K60IpaQmapBadArgument, "mux zero is refused");
    check(k60_ipa_qmap_encode(255, payload, 20, frame, sizeof(frame), &total) ==
        K60IpaQmapBadArgument, "mux 255 is refused");
    check(k60_ipa_qmap_encode(1, payload, 0, frame, sizeof(frame), &total) ==
        K60IpaQmapBadArgument, "empty payload is refused");
    check(k60_ipa_qmap_encode(1, NULL, 20, frame, sizeof(frame), &total) ==
        K60IpaQmapBadArgument, "null payload is refused");
    check(k60_ipa_qmap_encode(1, payload, 20, NULL, sizeof(frame), &total) ==
        K60IpaQmapBadArgument, "null output is refused");
    check(k60_ipa_qmap_encode(1, payload, 20, frame, sizeof(frame), NULL) ==
        K60IpaQmapBadArgument, "null frame_bytes is refused");
    check(k60_ipa_qmap_encode(1, payload, 21, frame, 27, &total) ==
        K60IpaQmapTooLong, "short capacity is refused");
    bytes = 21;
    check(k60_ipa_qmap_encode(1, payload, bytes, frame, sizeof(frame), &total) ==
        K60IpaQmapOk, "boundary payload encodes");
}

static void
test_encode_too_long(void)
{
    static uint8_t payload[65536];
    static uint8_t frame[65536 + 8];
    size_t total = 0;

    memset(payload, 0x11, sizeof(payload));
    check(k60_ipa_qmap_encode(1, payload, 0xffff, frame, sizeof(frame), &total) ==
        K60IpaQmapTooLong, "padded length above 16 bits is refused");
    check(k60_ipa_qmap_encode(1, payload, 0xffff - 3, frame, sizeof(frame),
        &total) == K60IpaQmapOk, "largest representable payload encodes");
}

static void
test_decode_single(void)
{
    uint8_t payload[21];
    uint8_t frame[32];
    K60IpaQmapStats stats;
    Recorded r;
    size_t total = 0;
    size_t i;

    for (i = 0; i < sizeof(payload); i++) {
        payload[i] = (uint8_t)(i * 3 + 1);
    }
    memset(&r, 0, sizeof(r));
    check(k60_ipa_qmap_encode(2, payload, sizeof(payload), frame, sizeof(frame),
        &total) == K60IpaQmapOk, "decode fixture encodes");
    check(k60_ipa_qmap_decode(frame, total, record, &r, &stats) == 1,
        "single frame delivered");
    check(stats.packets == 1 && stats.commands == 0 && stats.dropped == 0 &&
        stats.bytes == sizeof(payload), "single frame statistics");
    check(r.count == 1 && r.mux[0] == 2 && r.bytes[0] == sizeof(payload),
        "single frame mux and length");
    check(memcmp(r.payload[0], payload, sizeof(payload)) == 0,
        "single frame payload");
    check(k60_ipa_qmap_decode(frame, total - 1, record, &r, &stats) == 0 &&
        stats.dropped == 1, "truncated payload is dropped");
    check(k60_ipa_qmap_decode(frame, 2, record, &r, &stats) == 0 &&
        stats.dropped == 1, "truncated header is dropped");
    check(k60_ipa_qmap_decode(NULL, 0, record, &r, &stats) == 0 &&
        stats.dropped == 0, "null buffer decodes nothing");
    check(k60_ipa_qmap_decode(frame, total, NULL, NULL, NULL) == 1,
        "decode works without a receiver or stats");
}

static void
test_decode_aggregate(void)
{
    uint8_t frame[160];
    uint8_t first[5] = {0x45, 0, 0, 0, 0};
    uint8_t second[17];
    uint8_t third[16];
    size_t total = 0;
    size_t part = 0;
    Recorded r;
    K60IpaQmapStats stats;
    unsigned i;

    for (i = 0; i < sizeof(second); i++) {
        second[i] = (uint8_t)(0x60 + i);
    }
    memset(third, 0x7e, sizeof(third));
    memset(&r, 0, sizeof(r));

    check(k60_ipa_qmap_encode(1, first, sizeof(first), frame + total,
        sizeof(frame) - total, &part) == K60IpaQmapOk, "aggregate first");
    total += part;
    frame[total + 0] = K60_IPA_QMAP_COMMAND_BIT;
    frame[total + 1] = 0;
    frame[total + 2] = 0;
    frame[total + 3] = 8;
    memset(frame + total + 4, 0, 8);
    total += 12;
    check(k60_ipa_qmap_encode(4, third, sizeof(third), frame + total,
        sizeof(frame) - total, &part) == K60IpaQmapOk, "aggregate second");
    total += part;
    check(k60_ipa_qmap_encode(3, second, sizeof(second), frame + total,
        sizeof(frame) - total, &part) == K60IpaQmapOk, "aggregate third");
    total += part;

    check(k60_ipa_qmap_decode(frame, total, record, &r, &stats) == 3,
        "three data frames delivered");
    check(stats.packets == 3 && stats.commands == 1 && stats.dropped == 0,
        "aggregate counts commands and drops nothing");
    check(stats.bytes == 5 + 16 + 17, "aggregate payload bytes exclude padding");
    check(r.mux[0] == 1 && r.mux[1] == 4 && r.mux[2] == 3,
        "aggregate preserves mux order");
    check(r.bytes[2] == 17 && memcmp(r.payload[2], second, 17) == 0,
        "padded payload is trimmed to the IP length");
    check(memcmp(r.payload[1], third, 16) == 0, "middle payload intact");

    check(k60_ipa_qmap_decode(frame, total - 1, record, &r, &stats) == 2 &&
        stats.dropped == 1, "trailing truncation drops only the last frame");
}

static void
test_decode_header_errors(void)
{
    uint8_t frame[32];
    K60IpaQmapStats stats;
    Recorded r;

    memset(&r, 0, sizeof(r));

    memset(frame, 0, sizeof(frame));
    frame[2] = 0;
    frame[3] = 0;
    check(k60_ipa_qmap_decode(frame, 8, record, &r, &stats) == 0 &&
        stats.dropped == 1, "zero length is dropped");

    frame[0] = 5;
    frame[2] = 0;
    frame[3] = 4;
    check(k60_ipa_qmap_decode(frame, 8, record, &r, &stats) == 0 &&
        stats.dropped == 1, "pad larger than length is dropped");

    frame[0] = K60_IPA_QMAP_RESERVED_BIT;
    frame[2] = 0;
    frame[3] = 4;
    check(k60_ipa_qmap_decode(frame, 8, record, &r, &stats) == 0 &&
        stats.dropped == 1, "reserved bit is dropped");

    frame[0] = 0;
    frame[1] = 0;
    frame[2] = 0;
    frame[3] = 4;
    check(k60_ipa_qmap_decode(frame, 8, record, &r, &stats) == 0 &&
        stats.dropped == 1, "mux zero data frame is dropped");
    check(stats.packets == 0 && stats.commands == 0,
        "refused frames deliver nothing");

    memset(frame, 0, sizeof(frame));
    frame[1] = 1;
    frame[3] = 4;
    check(k60_ipa_qmap_decode(frame, 10, record, &r, &stats) == 1 &&
        stats.dropped == 1, "trailing partial header is dropped");
}

static void
test_round_trip(void)
{
    uint8_t payload[1600];
    uint8_t frame[1640];
    Recorded r;
    K60IpaQmapStats stats;
    size_t bytes;
    size_t total;
    uint8_t mux;
    unsigned i;

    for (i = 0; i < sizeof(payload); i++) {
        payload[i] = (uint8_t)(i ^ 0x5a);
    }
    for (bytes = 1; bytes <= 64; bytes++) {
        for (mux = 1; mux <= 4; mux++) {
            memset(&r, 0, sizeof(r));
            check(k60_ipa_qmap_encode(mux, payload, bytes, frame, sizeof(frame),
                &total) == K60IpaQmapOk, "round-trip encode");
            check(total == expected_frame(bytes), "round-trip frame size");
            check(k60_ipa_qmap_decode(frame, total, record, &r, &stats) == 1,
                "round-trip decode");
            check(r.mux[0] == mux && r.bytes[0] == bytes &&
                memcmp(r.payload[0], payload, bytes) == 0,
                "round-trip payload identity");
        }
    }
    memset(&r, 0, sizeof(r));
    check(k60_ipa_qmap_encode(4, payload, 1492, frame, sizeof(frame), &total) ==
        K60IpaQmapOk, "MTU payload encodes");
    check(total == 1496, "MTU frame is header plus MTU");
    check(k60_ipa_qmap_decode(frame, total, record, &r, &stats) == 1 &&
        r.bytes[0] == 1492, "MTU payload decodes");
}

int
main(void)
{
    test_frame_bytes();
    test_encode();
    test_encode_too_long();
    test_decode_single();
    test_decode_aggregate();
    test_decode_header_errors();
    test_round_trip();
    if (failures != 0) {
        printf("K60 IPA QMAP FAIL %d check(s)\n", failures);
        return 1;
    }
    printf("K60 IPA QMAP PASS frame_bytes encode decode aggregate header-errors round-trip\n");
    return 0;
}
