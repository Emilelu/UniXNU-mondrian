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

    /* 10. A rejected value marks its field failed, never valid. */
    {
        K60Battmgr v;
        uint8_t req[K60_BATTMGR_NOTIFY_BYTES];
        k60_battmgr_init(&v, 0, 0, 0);
        k60_battmgr_channel_up(&v);
        v.cursor = K60BmVoltage;
        expect(k60_battmgr_next(&v, req) == K60_BATTMGR_REQUEST_BYTES, "voltage request is 24 B");
        k60_battmgr_sent(&v);
        ack(in, 24, 1u, 0x30u, 0u);
        put(in, 12, 7u);
        put(in, 16, 100u);
        expect(k60_battmgr_receive(&v, in, 24) == K60BmAnswer, "invalid voltage is answered");
        expect((v.failed & BIT(K60BmVoltage)) != 0, "invalid voltage sets its failed bit");
        expect((v.valid & BIT(K60BmVoltage)) == 0, "invalid voltage is not valid");
        expect(v.errors == 1, "invalid voltage counts one error");
    }

    /* 11. The sample carries raw wire values and the cycle failed mask. */
    {
        K60Battmgr raw;
        K60BatterySample sm;
        k60_battmgr_init(&raw, 0, 0, 0);
        raw.last_fresh = BIT(K60BmStatus) | BIT(K60BmPresent) | BIT(K60BmCapacity) |
            BIT(K60BmVoltage) | BIT(K60BmTemperature) | BIT(K60BmFull) |
            BIT(K60BmDesign) | BIT(K60BmCycles) | BIT(K60BmUsbOnline) |
            BIT(K60BmUsbVoltage) | BIT(K60BmWirelessOnline);
        raw.failed = BIT(K60BmUsbCurrent);
        raw.value[K60BmStatus] = 2;
        raw.value[K60BmPresent] = 1;
        raw.value[K60BmCapacity] = 8900;
        raw.value[K60BmVoltage] = 4277000;
        raw.value[K60BmTemperature] = 2830;
        raw.value[K60BmFull] = 5000000;
        raw.value[K60BmDesign] = 5500000;
        raw.value[K60BmCycles] = 100;
        raw.value[K60BmUsbOnline] = 1;
        raw.value[K60BmUsbVoltage] = 5000000;
        raw.value[K60BmUsbCurrent] = 0;
        expect(k60_battmgr_sample(&raw, &sm) == 1, "raw sample passes validation");
        expect(sm.raw[K60BmVoltage] == 4277000, "raw voltage keeps microvolts");
        expect(sm.raw[K60BmTemperature] == 2830, "raw temperature keeps hundredths");
        expect(sm.raw[K60BmCapacity] == 8900, "raw capacity keeps hundredths of a percent");
        expect(sm.failed == BIT(K60BmUsbCurrent), "sample carries the failed mask");
        expect(sm.voltage_mv == 4277, "published voltage is millivolts");
        expect(sm.capacity_hundredths == 8900, "published capacity is hundredths");
    }

    /* 12. An absent pack still reports raw USB values and the failed mask. */
    {
        K60Battmgr raw;
        K60BatterySample sm;
        k60_battmgr_init(&raw, 0, 0, 0);
        raw.last_fresh = BIT(K60BmPresent) | BIT(K60BmUsbOnline) |
            BIT(K60BmUsbVoltage) | BIT(K60BmWirelessOnline);
        raw.failed = BIT(K60BmCapacity);
        raw.value[K60BmPresent] = 0;
        raw.value[K60BmUsbOnline] = 1;
        raw.value[K60BmUsbVoltage] = 5000000;
        expect(k60_battmgr_sample(&raw, &sm) == 1, "absent pack returns a sample");
        expect(sm.present == 0, "absent pack is not present");
        expect(sm.raw[K60BmUsbVoltage] == 5000000, "absent pack keeps raw USB voltage");
        expect(sm.failed == BIT(K60BmCapacity), "absent pack keeps the failed mask");
    }

    /* 13. A timeout marks only the fields that never completed. */
    {
        K60Battmgr t;
        k60_battmgr_init(&t, 0, 0, 0);
        k60_battmgr_channel_up(&t);
        t.cursor = K60BmCapacity;
        t.flight = FLIGHT_PROPERTY;
        t.completed = BIT(K60BmStatus) | BIT(K60BmPresent);
        k60_battmgr_timeout(&t);
        expect((t.failed & BIT(K60BmCapacity)) != 0, "timeout marks the outstanding field failed");
        expect((t.failed & BIT(K60BmStatus)) == 0, "timeout leaves completed fields alone");
        expect((t.failed & BIT(K60BmPresent)) == 0, "timeout leaves every completed field alone");
    }

    /* 14. A transport restart clears the sample and a fresh cycle publishes again. */
    {
        K60Battmgr rst;
        K60BatterySample smp;
        k60_battmgr_init(&rst, 0, 0, 0);
        k60_battmgr_channel_up(&rst);
        rst.last_fresh = BIT(K60BmStatus) | BIT(K60BmPresent) | BIT(K60BmCapacity) |
            BIT(K60BmVoltage) | BIT(K60BmTemperature) | BIT(K60BmFull) |
            BIT(K60BmDesign) | BIT(K60BmCycles) | BIT(K60BmUsbOnline) |
            BIT(K60BmUsbVoltage) | BIT(K60BmWirelessOnline);
        rst.value[K60BmStatus] = 1;
        rst.value[K60BmPresent] = 1;
        rst.value[K60BmCapacity] = 5000;
        rst.value[K60BmVoltage] = 4300000;
        rst.value[K60BmTemperature] = 3000;
        rst.value[K60BmFull] = 5000000;
        rst.value[K60BmDesign] = 5500000;
        rst.value[K60BmUsbOnline] = 1;
        rst.value[K60BmUsbVoltage] = 5000000;
        expect(k60_battmgr_sample(&rst, &smp) == 1, "sample available before restart");
        k60_battmgr_channel_down(&rst);
        expect(k60_battmgr_sample(&rst, &smp) == 0, "channel down drops the sample");
        k60_battmgr_channel_up(&rst);
        rst.last_fresh = BIT(K60BmStatus) | BIT(K60BmPresent) | BIT(K60BmCapacity) |
            BIT(K60BmVoltage) | BIT(K60BmTemperature) | BIT(K60BmFull) |
            BIT(K60BmDesign) | BIT(K60BmCycles) | BIT(K60BmUsbOnline) |
            BIT(K60BmUsbVoltage) | BIT(K60BmWirelessOnline);
        expect(k60_battmgr_sample(&rst, &smp) == 1, "a fresh cycle publishes after restart");
    }

    /* 15. Plug, unplug and the charging/full states come from status plus
     * external power, not from a fabricated conclusion. */
    {
        K60Battmgr p;
        K60BatterySample sm;
        const uint32_t all = BIT(K60BmStatus) | BIT(K60BmPresent) | BIT(K60BmCapacity) |
            BIT(K60BmVoltage) | BIT(K60BmTemperature) | BIT(K60BmFull) |
            BIT(K60BmDesign) | BIT(K60BmCycles) | BIT(K60BmUsbOnline) |
            BIT(K60BmUsbVoltage) | BIT(K60BmWirelessOnline) | BIT(K60BmUsbCurrent) |
            BIT(K60BmTimeToFull) | BIT(K60BmTimeToEmpty);
        k60_battmgr_init(&p, 1, 0, 0);
        p.last_fresh = all;
        p.value[K60BmStatus] = 1;
        p.value[K60BmPresent] = 1;
        p.value[K60BmCapacity] = 5000;
        p.value[K60BmVoltage] = 4300000;
        p.value[K60BmTemperature] = 3000;
        p.value[K60BmFull] = 5000000;
        p.value[K60BmDesign] = 5500000;
        p.value[K60BmCycles] = 100;
        p.value[K60BmUsbOnline] = 1;
        p.value[K60BmUsbVoltage] = 5000000;
        p.value[K60BmUsbCurrent] = 397000;
        p.value[K60BmTimeToFull] = 3600;
        p.value[K60BmTimeToEmpty] = 7200;
        expect(k60_battmgr_sample(&p, &sm) == 1, "plugged pack returns a sample");
        expect(sm.external == 1 && sm.charging == 1 && sm.full == 0,
               "status 1 with USB is charging");
        expect(sm.current_ma == 397 && sm.current_source == K60BatteryCurrentUsb,
               "USB input current feeds the charging sample");
        expect(sm.time_remaining_min == 60,
               "charging uses time-to-full");

        p.value[K60BmStatus] = 2;
        p.value[K60BmUsbOnline] = 0;
        p.value[K60BmUsbVoltage] = 0;
        p.value[K60BmUsbCurrent] = 0;
        expect(k60_battmgr_sample(&p, &sm) == 1, "unplugged pack returns a sample");
        expect(sm.external == 0 && sm.charging == 0 && sm.usb_connected == 0,
               "unplugged status 2 is discharging");
        expect(sm.current_ma == 0 && sm.current_source == K60BatteryCurrentNone,
               "unplugged sample has no charging current");
        expect(sm.time_remaining_min == 120,
               "discharging uses time-to-empty");

        p.value[K60BmStatus] = 4;
        p.value[K60BmUsbOnline] = 1;
        p.value[K60BmUsbVoltage] = 5000000;
        expect(k60_battmgr_sample(&p, &sm) == 1, "full pack returns a sample");
        expect(sm.external == 1 && sm.charging == 0 && sm.full == 1,
               "status 4 with USB is full");
        expect(sm.time_remaining_min == 0, "full pack has zero time remaining");

        p.value[K60BmStatus] = 2;
        p.value[K60BmUsbOnline] = 1;
        p.value[K60BmUsbVoltage] = 5000000;
        p.value[K60BmUsbCurrent] = 0;
        p.value[K60BmCurrent] = 0;
        expect(k60_battmgr_sample(&p, &sm) == 1, "plugged but not charging returns a sample");
        expect(sm.external == 1 && sm.charging == 0, "status 2 with USB is not charging");
        expect(sm.time_remaining_min == 120,
               "plugged but not charging uses time-to-empty");

        p.value[K60BmStatus] = 1;
        p.value[K60BmUsbOnline] = 0;
        p.value[K60BmUsbVoltage] = 0;
        expect(k60_battmgr_sample(&p, &sm) == 0,
               "status 1 without external power is rejected");

        p.value[K60BmStatus] = 2;
        p.value[K60BmUsbOnline] = 1;
        p.value[K60BmUsbVoltage] = 5000000;
        p.value[K60BmCurrent] = 500000;
        p.last_fresh |= BIT(K60BmCurrent);
        expect(k60_battmgr_sample(&p, &sm) == 0,
               "status 2 with positive current is rejected");
    }

    if (fails) { printf("FAILURES %d\n", fails); return 1; }
    printf("TESTS OK %d\n", checks);
    return 0;
}
