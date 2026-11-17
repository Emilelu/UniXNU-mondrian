/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Pins the measured opcode-4 subscription ACK pair for the K60 battery codec.
 *
 * The ADSP firmware's own opcode-4 handler answers with a 16-byte frame
 * {owner=0x800a, type=1, opcode=4, result} (docs/research/charger/
 * 06-SUBSCRIPTION-CONSTANT.md). This test proves the repo consumer accepts
 * exactly that pair and rejects every neighbouring shape, so the constant can
 * never silently drift back to "zero until a capture exists". */
#include <stdio.h>
#include <string.h>
#include "../../drivers/PongPower/K60Battmgr.c"

#define ACK_TYPE 1u
#define ACK_BYTES 16u

static int fails, checks;

static void expect(int cond, const char *what)
{
    checks++;
    if (!cond) { printf("FAIL %s\n", what); fails++; }
}

static void put(uint8_t *p, unsigned off, uint32_t v)
{
    p[off] = (uint8_t)v; p[off + 1] = (uint8_t)(v >> 8);
    p[off + 2] = (uint8_t)(v >> 16); p[off + 3] = (uint8_t)(v >> 24);
}

static void ack(uint8_t *p, unsigned bytes, uint32_t type, uint32_t opcode, uint32_t result)
{
    memset(p, 0, bytes);
    put(p, 0, K60_BATTMGR_OWNER);
    put(p, 4, type);
    put(p, 8, opcode);
    if (bytes >= 16) put(p, 12, result);
}

int main(void)
{
    K60Battmgr b;
    uint8_t frame[K60_BATTMGR_NOTIFY_BYTES], in[64];

    /* 1. The measured pair is accepted by the init whitelist. */
    k60_battmgr_init(&b, 0, ACK_TYPE, ACK_BYTES);
    expect(b.notify_reply_type == ACK_TYPE, "init keeps reply type 1");
    expect(b.notify_reply_bytes == ACK_BYTES, "init keeps reply length 16");

    /* 2. A zero length (unqualified) still disables subscription. */
    {
        K60Battmgr z;
        k60_battmgr_init(&z, 0, 0, 0);
        k60_battmgr_channel_up(&z);
        expect(z.subscribe_due == 0, "unqualified pair keeps subscription off");
        expect(k60_battmgr_next(&z, frame) == K60_BATTMGR_REQUEST_BYTES,
               "unqualified pair goes straight to properties");
    }

    /* 3. Channel up arms the subscription and the request is the 28 B NOTIFY frame. */
    k60_battmgr_channel_up(&b);
    expect(b.subscribe_due == 1, "channel up arms subscription");
    expect(k60_battmgr_next(&b, frame) == K60_BATTMGR_NOTIFY_BYTES, "subscribe frame is 28 B");
    expect(le32(frame) == K60_BATTMGR_OWNER, "subscribe owner 0x800a");
    expect(le32(frame + 4) == 2u, "subscribe type 2");
    expect(le32(frame + 8) == 4u, "subscribe opcode 4");
    {
        int zero = 1;
        for (unsigned i = 12; i < K60_BATTMGR_NOTIFY_BYTES; ++i) zero &= frame[i] == 0;
        expect(zero, "subscribe payload is four zero words");
    }
    k60_battmgr_sent(&b);
    expect(b.flight == 2u, "flight is FLIGHT_SUBSCRIBE");
    expect(k60_battmgr_opcode(&b) == 4u, "pending opcode is 4");

    /* 4. Every shape but (type 1, 16 B, zero result) must be ignored. */
    ack(in, 28, 2u, 4u, 0u);
    expect(k60_battmgr_receive(&b, in, 28) == K60BmIgnored, "28 B ACK ignored");
    ack(in, 16, 2u, 4u, 0u);
    expect(k60_battmgr_receive(&b, in, 16) == K60BmIgnored, "type 2 ACK ignored");
    ack(in, 24, 1u, 4u, 0u);
    expect(k60_battmgr_receive(&b, in, 24) == K60BmIgnored, "24 B ACK ignored");
    ack(in, 12, 1u, 4u, 0u);
    expect(k60_battmgr_receive(&b, in, 12) == K60BmIgnored, "12 B ACK ignored");
    expect(b.subscribed == 0, "no ignored shape marks subscription complete");

    /* 5. A non-zero result word is a remote failure, not success. */
    ack(in, 16, 1u, 4u, 0x206u);
    expect(k60_battmgr_receive(&b, in, 16) == K60BmAnswer, "non-zero result answers, not subscribes");
    expect(b.subscribed == 0, "non-zero result leaves subscription off");
    expect(b.errors == 1, "non-zero result counts one error");
    expect(b.flight == 0, "non-zero result releases the flight");

    /* 6. The measured frame completes the subscription and polling starts. */
    k60_battmgr_channel_up(&b);
    expect(k60_battmgr_next(&b, frame) == K60_BATTMGR_NOTIFY_BYTES, "re-arm sends subscribe again");
    k60_battmgr_sent(&b);
    ack(in, 16, 1u, 4u, 0u);
    expect(k60_battmgr_receive(&b, in, 16) == K60BmSubscribed, "16 B type 1 zero-result ACK subscribes");
    expect(b.subscribed == 1, "subscribed flag set");
    expect(b.flight == 0, "subscription flight released");
    expect(k60_battmgr_next(&b, frame) == K60_BATTMGR_REQUEST_BYTES, "polling resumes at 24 B");
    expect(le32(frame + 4) == 1u, "property request type 1");
    expect(le32(frame + 8) == 0x30u, "first poll is battery GET");

    /* 7. A notification only counts when it is the 16 B type 2 opcode 7 frame. */
    ack(in, 16, 2u, 7u, 0u);
    put(in, 12, 0x30u);
    expect(k60_battmgr_receive(&b, in, 16) == K60BmNotified, "type 2 opcode 7 notification accepted");
    expect(b.notifications == 1, "notification counted");

    /* 8. CURRENT_NOW (field 4 / property 9) is optional and never requested. */
    {
        K60Battmgr s;
        const uint32_t props[4] = {0u, 2u, 4u, 7u};
        const int32_t values[4] = {1, 1, 5000, 4300000};
        k60_battmgr_init(&s, 0, 0, 0);
        k60_battmgr_channel_up(&s);
        for (unsigned i = 0; i < 4; ++i) {
            expect(k60_battmgr_next(&s, frame) == K60_BATTMGR_REQUEST_BYTES, "property request is 24 B");
            expect(le32(frame + 16) == props[i], "property order before the current field");
            k60_battmgr_sent(&s);
            ack(in, 24, 1u, 0x30u, 0u);
            put(in, 12, props[i]);
            put(in, 16, (uint32_t)values[i]);
            expect(k60_battmgr_receive(&s, in, 24) == K60BmAnswer, "battery property answered");
        }
        expect(k60_battmgr_next(&s, frame) == K60_BATTMGR_REQUEST_BYTES, "next request after voltage is 24 B");
        expect(le32(frame + 16) == 13u, "CURRENT_NOW property 9 is skipped");
    }

    /* 9. A notification during a cycle must not discard the completed sample. */
    {
        K60Battmgr d;
        K60BatterySample sample;
        k60_battmgr_init(&d, 0, 0, 0);
        d.cycle_active = 1;
        d.cursor = K60BmFields - 1;
        d.sample_dirty = 1;
        d.notifications = 1;
        d.fresh = BIT(K60BmStatus) | BIT(K60BmPresent) | BIT(K60BmCapacity) |
            BIT(K60BmVoltage) | BIT(K60BmTemperature) | BIT(K60BmFull) |
            BIT(K60BmDesign) | BIT(K60BmCycles) | BIT(K60BmUsbOnline) |
            BIT(K60BmUsbVoltage) | BIT(K60BmWirelessOnline) | BIT(K60BmUsbCurrent);
        d.value[K60BmStatus] = 1;
        d.value[K60BmPresent] = 1;
        d.value[K60BmCapacity] = 5000;
        d.value[K60BmVoltage] = 4300000;
        d.value[K60BmTemperature] = 3000;
        d.value[K60BmFull] = 5000000;
        d.value[K60BmDesign] = 5500000;
        d.value[K60BmCycles] = 100;
        d.value[K60BmUsbOnline] = 1;
        d.value[K60BmUsbVoltage] = 5000000;
        d.value[K60BmUsbCurrent] = 397000;
        d.valid = BIT(K60BmUsbCurrent);
        expect(finish_field(&d) == K60BmCycleDone, "notification-dirty cycle finishes");
        expect(d.sample_dirty == 0, "finish_field clears the notification flag");
        expect(d.refresh_due == 1, "finish_field keeps the extra refresh request");
        expect(k60_battmgr_sample(&d, &sample) == 1, "completed sample survives the notification");
        expect(sample.current_source == K60BatteryCurrentUsb && sample.current_ma == 397,
               "USB input current is tagged as the source");
    }

    if (fails) { printf("FAILURES %d\n", fails); return 1; }
    printf("TESTS OK %d\n", checks);
    return 0;
}
