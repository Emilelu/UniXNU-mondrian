/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* Host test for the two-slot QcomGlink transport.
 *
 * The transport in drivers/PongPower/QcomGlink.c is event driven and
 * allocation free, so the whole protocol can be driven from a host: this file
 * plays the DSP on the receive FIFO and reads back what the AP wrote into the
 * transmit FIFO. Nothing here touches MMIO, SMEM or a device.
 *
 * Two consumers register different channel names on one instance; the test
 * asserts each one receives only its own messages, including when the two
 * channels' traffic is interleaved, replayed or addressed to nobody.
 *
 * QCOM_GLINK_MAX_CHANNELS is 2 in drivers/PongPower/QcomGlink.h; this file
 * compiles the real transport and pins the per-slot protocol behavior. */

#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include "QcomGlink.h"
#include "K60AudioGlink.h"

#if QCOM_GLINK_MAX_CHANNELS < 2u
#error "QcomGlink.h still has one channel slot: run run-glink-multislot-tests.sh"
#endif

#define FIFO_BYTES 4096u
#define LOG_BYTES 96u
#define NAME_A "PMIC_RTR_ADSP_APPS"
#define NAME_B "adsp_apps"
#define RCID_A 0x21u
#define RCID_B 0x22u
#define RCID_NOBODY 0x77u
#define NAME_UNKNOWN "not_a_channel"
#define RCID_UNKNOWN 0x99u

static unsigned cases, fails;

static void expect(int cond, const char *what)
{
    ++cases;
    if (!cond) {++fails; printf("FAIL %s\n", what);}
}
static void expect_eq(unsigned long got, unsigned long want, const char *what)
{
    ++cases;
    if (got != want) {++fails; printf("FAIL %s: got %lu want %lu\n", what, got, want);}
}
static void expect_name(const char *got, const char *want, const char *what)
{
    ++cases;
    if (strcmp(got, want)) {++fails; printf("FAIL %s: got \"%s\" want \"%s\"\n", what, got, want);}
}

static uint32_t align8(uint32_t v) {return (v + 7u) & ~7u;}
static uint32_t le32(const uint8_t *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static void put32le(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}
static unsigned rd16(const uint8_t *p) {return (unsigned)p[0] | (unsigned)p[1] << 8;}

typedef struct {
    volatile uint32_t txhead, txtail, rxhead, rxtail;
    uint8_t txdata[FIFO_BYTES], rxdata[FIFO_BYTES];
    uint8_t storage_a[4u * 256u], storage_b[2u * 512u];
    QcomGlink g;
    QcomGlinkClient client;
    QcomGlinkChannel *a, *b;
    unsigned kicks, a_states, b_states;
    int a_up, b_up;
    char a_log[LOG_BYTES], b_log[LOG_BYTES];
} Link;

static Link link, replay, bridge_link;

static void log_add(char *log, const uint8_t *data, uint32_t length)
{
    size_t at = strlen(log), i;
    for (i = 0; i < length && at + 2u < LOG_BYTES; ++i) log[at++] = (char)data[i];
    log[at++] = ';';
    log[at] = 0;
}

static void on_kick(void *context) {++((Link *)context)->kicks;}

static void on_state(void *context, QcomGlinkChannel *channel, int up)
{
    Link *l = (Link *)context;
    if (channel == l->a) {++l->a_states; l->a_up = up;}
    else {++l->b_states; l->b_up = up;}
}
static void on_receive(void *context, QcomGlinkChannel *channel, const uint8_t *data, uint32_t length)
{
    Link *l = (Link *)context;
    if (channel == l->a) log_add(l->a_log, data, length);
    else log_add(l->b_log, data, length);
}

typedef struct {
    unsigned states;
    int up;
    char log[LOG_BYTES];
} BridgeSink;

static void bridge_state(void *context, bool up)
{
    BridgeSink *s = (BridgeSink *)context;
    ++s->states;
    s->up = up;
}
static void bridge_receive(void *context, const uint8_t *data, unsigned bytes)
{
    BridgeSink *s = (BridgeSink *)context;
    log_add(s->log, data, bytes);
}

/* ------------------------------------------------------------------ the DSP */

static uint32_t peer_room(const Link *l)
{
    const uint32_t head = l->rxhead, tail = l->rxtail;
    return head >= tail ? FIFO_BYTES - head + tail : tail - head;
}
static void peer_raw(Link *l, const uint8_t *bytes, uint32_t count, uint32_t padded)
{
    uint32_t at = l->rxhead, i;
    expect(peer_room(l) > padded + 32u, "the peer FIFO has room");
    for (i = 0; i < count; ++i) {l->rxdata[at] = bytes[i]; if (++at == FIFO_BYTES) at = 0;}
    for (; i < padded; ++i) {l->rxdata[at] = 0; if (++at == FIFO_BYTES) at = 0;}
    l->rxhead = at;
}
static void peer_cmd(Link *l, uint16_t cmd, uint16_t param1, uint32_t param2)
{
    uint8_t m[8];
    m[0] = (uint8_t)cmd; m[1] = (uint8_t)(cmd >> 8); m[2] = (uint8_t)param1; m[3] = (uint8_t)(param1 >> 8);
    put32le(m + 4, param2);
    peer_raw(l, m, 8, 8);
}
static void peer_open(Link *l, uint16_t rcid, const char *name)
{
    const uint32_t n = (uint32_t)strlen(name) + 1u;
    uint8_t m[8];
    m[0] = QCOM_GLINK_OPEN; m[1] = 0; m[2] = (uint8_t)rcid; m[3] = (uint8_t)(rcid >> 8);
    put32le(m + 4, n);
    peer_raw(l, m, 8, 8);
    peer_raw(l, (const uint8_t *)name, n, align8(n));
}
static void peer_intent(Link *l, uint16_t rcid, uint32_t size, uint32_t id)
{
    uint8_t m[16];
    m[0] = QCOM_GLINK_INTENT; m[1] = 0; m[2] = (uint8_t)rcid; m[3] = (uint8_t)(rcid >> 8);
    put32le(m + 4, 1);
    put32le(m + 8, size);
    put32le(m + 12, id);
    peer_raw(l, m, 16, 16);
}
static void peer_data(Link *l, uint16_t rcid, uint32_t liid, const char *payload, uint32_t length)
{
    uint8_t h[16];
    h[0] = QCOM_GLINK_TX_DATA; h[1] = 0; h[2] = (uint8_t)rcid; h[3] = (uint8_t)(rcid >> 8);
    put32le(h + 4, liid);
    put32le(h + 8, length);
    put32le(h + 12, 0);
    peer_raw(l, h, 16, 16);
    peer_raw(l, (const uint8_t *)payload, length, align8(length));
}

/* -------------------------------------------------------------- the AP side */

static uint32_t ap_avail(const Link *l)
{
    const uint32_t head = l->txhead, tail = l->txtail;
    return head >= tail ? head - tail : FIFO_BYTES - tail + head;
}
static void ap_peek(const Link *l, uint32_t offset, uint8_t *to, uint32_t count)
{
    uint32_t at = l->txtail + offset, i;
    if (at >= FIFO_BYTES) at -= FIFO_BYTES;
    for (i = 0; i < count; ++i) {to[i] = l->txdata[at]; if (++at == FIFO_BYTES) at = 0;}
}
static void ap_advance(Link *l, uint32_t count)
{
    uint32_t tail = l->txtail + count;
    if (tail >= FIFO_BYTES) tail -= FIFO_BYTES;
    l->txtail = tail;
}
/* 8-byte control messages only: OPEN, INTENT and TX_DATA have their own readers. */
static int ap_read_cmd(Link *l, unsigned *cmd, unsigned *param1, uint32_t *param2)
{
    uint8_t m[8];
    if (ap_avail(l) < 8) return 0;
    ap_peek(l, 0, m, 8);
    *cmd = rd16(m); *param1 = rd16(m + 2); *param2 = le32(m + 4);
    ap_advance(l, 8);
    return 1;
}
static int ap_read_open(Link *l, unsigned *lcid, char *name, uint32_t capacity)
{
    uint8_t m[8];
    if (ap_avail(l) < 8) return 0;
    ap_peek(l, 0, m, 8);
    if (rd16(m) != QCOM_GLINK_OPEN) return 0;
    const uint32_t n = le32(m + 4) & 0xffffu;
    if (!n || n > capacity || ap_avail(l) < align8(8u + n)) return 0;
    *lcid = rd16(m + 2);
    ap_peek(l, 8, (uint8_t *)name, n);
    name[n - 1u] = 0;
    ap_advance(l, align8(8u + n));
    return 1;
}
static int ap_read_intent(Link *l, unsigned *lcid, uint32_t *size, uint32_t *index)
{
    uint8_t m[16];
    if (ap_avail(l) < 16) return 0;
    ap_peek(l, 0, m, 16);
    if (rd16(m) != QCOM_GLINK_INTENT) return 0;
    *lcid = rd16(m + 2);
    *size = le32(m + 8);
    *index = le32(m + 12) - 1u;
    ap_advance(l, 16);
    return 1;
}
static int ap_read_data(Link *l, unsigned *lcid, uint32_t *id, char *payload, uint32_t capacity)
{
    uint8_t h[16];
    if (ap_avail(l) < 16) return 0;
    ap_peek(l, 0, h, 16);
    if (rd16(h) != QCOM_GLINK_TX_DATA) return 0;
    const uint32_t length = le32(h + 8);
    if (length >= capacity || ap_avail(l) < align8(16u + length)) return 0;
    *lcid = rd16(h + 2);
    *id = le32(h + 4);
    ap_peek(l, 16, (uint8_t *)payload, length);
    payload[length] = 0;
    ap_advance(l, align8(16u + length));
    return 1;
}

typedef struct {
    unsigned version, version_ack, open, open_ack, intent, rx_done, rx_done_reuse, data, intent_req, other;
    unsigned unknown_open_ack;   /* OPEN_ACK addressed to RCID_UNKNOWN */
} Scan;

static void ap_scan(Link *l, Scan *s)
{
    memset(s, 0, sizeof *s);
    for (;;) {
        uint8_t m[16];
        const uint32_t have = ap_avail(l);
        if (have < 8) return;
        ap_peek(l, 0, m, have >= 16 ? 16 : 8);
        const unsigned cmd = rd16(m), param1 = rd16(m + 2);
        switch (cmd) {
        case QCOM_GLINK_OPEN: {
            const uint32_t n = le32(m + 4) & 0xffffu;
            if (!n || have < align8(8u + n)) {++s->other; return;}
            ap_advance(l, align8(8u + n));
            ++s->open;
            break;
        }
        case QCOM_GLINK_INTENT:
            if (have < 16) {++s->other; return;}
            ap_advance(l, 16);
            ++s->intent;
            break;
        case QCOM_GLINK_TX_DATA: {
            if (have < 16) {++s->other; return;}
            const uint32_t length = le32(m + 8);
            if (have < align8(16u + length)) {++s->other; return;}
            ap_advance(l, align8(16u + length));
            ++s->data;
            break;
        }
        case QCOM_GLINK_OPEN_ACK:
            if (param1 == RCID_UNKNOWN) ++s->unknown_open_ack;
            ap_advance(l, 8);
            ++s->open_ack;
            break;
        case QCOM_GLINK_VERSION: ap_advance(l, 8); ++s->version; break;
        case QCOM_GLINK_VERSION_ACK: ap_advance(l, 8); ++s->version_ack; break;
        case QCOM_GLINK_RX_DONE: ap_advance(l, 8); ++s->rx_done; break;
        case QCOM_GLINK_RX_DONE_W_REUSE: ap_advance(l, 8); ++s->rx_done_reuse; break;
        case QCOM_GLINK_RX_INTENT_REQ: ap_advance(l, 8); ++s->intent_req; break;
        case QCOM_GLINK_RX_INTENT_REQ_ACK: ap_advance(l, 8); break;
        default: ap_advance(l, 8); ++s->other; break;
        }
    }
}

/* ------------------------------------------------------------------ fixtures */

static void link_reset(Link *l)
{
    memset(l, 0, sizeof *l);
    l->client.state = on_state;
    l->client.receive = on_receive;
    const QcomGlinkFifo tx = {&l->txhead, &l->txtail, l->txdata, FIFO_BYTES};
    const QcomGlinkFifo rx = {&l->rxhead, &l->rxtail, l->rxdata, FIFO_BYTES};
    expect_eq((unsigned long)qcom_glink_adopt(&l->g, tx, rx, on_kick, l), (unsigned long)QcomGlinkOk, "adopt");
}

/* Registers both channels and brings them up, checking every step. */
static void bring_up(Link *l)
{
    unsigned lcid, other_lcid = 0;
    uint32_t size, index;
    char name[QCOM_GLINK_NAME], payload[32];
    Scan s;

    link_reset(l);

    l->a = qcom_glink_channel(&l->g, NAME_A, 256, 4, l->storage_a, &l->client, l, 1);
    l->b = qcom_glink_channel(&l->g, NAME_B, 512, 2, l->storage_b, &l->client, l, 1);
    expect(l->a != 0, "the battery channel registers");
    expect(l->b != 0, "the audio channel registers on the same instance");
    if (!l->a || !l->b) return;
    expect(l->a != l->b, "the two consumers hold distinct slots");
    expect_eq(l->a->lcid, 1, "first slot gets lcid 1");
    expect_eq(l->b->lcid, 2, "second slot gets lcid 2");
    expect_name(l->a->name, NAME_A, "first slot keeps its name");
    expect_name(l->b->name, NAME_B, "second slot keeps its name");
    expect_eq(l->a->intent_size, 256, "first slot keeps its intent size");
    expect_eq(l->b->intent_size, 512, "second slot keeps its intent size");
    expect_eq(l->b->intent_count, 2, "second slot keeps its intent count");

    /* VERSION, then one OPEN per slot, each carrying its own name. */
    expect(qcom_glink_poll(&l->g) >= 0, "poll writes VERSION");
    expect(ap_read_cmd(l, &lcid, &size, &index) != 0, "VERSION is on the wire");
    expect_eq(lcid, QCOM_GLINK_VERSION, "the first message is VERSION");
    expect_eq(index, QCOM_GLINK_FEATURE_INTENT_REUSE, "we offer intent reuse");
    peer_cmd(l, QCOM_GLINK_VERSION_ACK, 1, QCOM_GLINK_FEATURE_INTENT_REUSE);
    expect(qcom_glink_poll(&l->g) >= 0, "poll after VERSION_ACK");

    expect(ap_read_open(l, &lcid, name, sizeof name) != 0, "first OPEN");
    expect_eq(lcid, 1, "first OPEN carries lcid 1");
    expect_name(name, NAME_A, "first OPEN names the battery channel");
    expect(ap_read_open(l, &lcid, name, sizeof name) != 0, "second OPEN");
    expect_eq(lcid, 2, "second OPEN carries lcid 2");
    expect_name(name, NAME_B, "second OPEN names the audio channel");
    expect_eq(ap_avail(l), 0, "nothing else was written for the opens");

    /* The DSP opens both, audio first: slot order must not matter. */
    peer_open(l, RCID_B, NAME_B);
    peer_open(l, RCID_A, NAME_A);
    expect_eq((unsigned long)qcom_glink_poll(&l->g), 2, "both remote opens are handled");
    expect(ap_read_cmd(l, &lcid, &size, &index) != 0, "OPEN_ACK for the audio open");
    expect_eq(lcid, QCOM_GLINK_OPEN_ACK, "it is an OPEN_ACK");
    expect_eq(size, RCID_B, "it acknowledges the audio rcid");
    expect(ap_read_cmd(l, &lcid, &size, &index) != 0, "OPEN_ACK for the battery open");
    expect_eq(size, RCID_A, "it acknowledges the battery rcid");
    expect_eq(l->a->rcid, RCID_A, "the battery slot took its own rcid");
    expect_eq(l->b->rcid, RCID_B, "the audio slot took its own rcid");

    /* The DSP acknowledges our opens, battery first this time. */
    peer_cmd(l, QCOM_GLINK_OPEN_ACK, 1, 0);
    peer_cmd(l, QCOM_GLINK_OPEN_ACK, 2, 0);
    expect(qcom_glink_poll(&l->g) >= 0, "poll after OPEN_ACK");
    for (unsigned k = 0; k < 4; ++k) {
        expect(ap_read_intent(l, &lcid, &size, &index) != 0, "battery intent advertised");
        expect_eq(lcid, 1, "battery intents carry lcid 1");
        expect_eq(size, 256, "battery intent size");
        expect_eq(index, k, "battery intent index");
    }
    for (unsigned k = 0; k < 2; ++k) {
        expect(ap_read_intent(l, &lcid, &size, &index) != 0, "audio intent advertised");
        expect_eq(lcid, 2, "audio intents carry lcid 2");
        expect_eq(size, 512, "audio intent size");
        expect_eq(index, k, "audio intent index");
    }
    expect_eq(ap_avail(l), 0, "both channels are fully advertised");
    expect_eq(l->a_up, 1, "the battery channel is up");
    expect_eq(l->b_up, 1, "the audio channel is up");
    expect_eq(l->a_states, 1, "one state callback per channel");
    expect_eq(l->b_states, 1, "one state callback per channel");
    expect(l->kicks >= 1, "the doorbell rang");

    /* Both slots are up and neither has seen a message yet. */
    ap_scan(l, &s);
    expect_eq(s.open_ack, 0, "no further OPEN_ACK once both are up");
    (void)other_lcid;
    (void)payload;
}

static void delivery_cases(void)
{
    Link *l = &link;
    Scan s;

    bring_up(l);

    /* The transport carries a second channel: a third registration is refused. */
    expect(qcom_glink_channel(&l->g, "third", 128, 1, l->storage_a, &l->client, l, 1) == 0,
           "a third registration finds no slot");
    expect_name(l->a->name, NAME_A, "the refused registration did not touch slot 1");
    expect_name(l->b->name, NAME_B, "the refused registration did not touch slot 2");

    /* A message for the audio slot reaches the audio consumer only. */
    peer_data(l, RCID_B, 1, "B-only", 6);
    expect(qcom_glink_poll(&l->g) >= 0, "poll delivers");
    expect_name(l->b_log, "B-only;", "the audio consumer got its message");
    expect_name(l->a_log, "", "the battery consumer got nothing");

    /* And the other way round. */
    peer_data(l, RCID_A, 1, "A1", 2);
    expect(qcom_glink_poll(&l->g) >= 0, "poll delivers to the other slot");
    expect_name(l->a_log, "A1;", "the battery consumer got its message");
    expect_name(l->b_log, "B-only;", "the audio consumer got nothing more");

    /* Interleaved traffic, one poll: each slot keeps its own order. */
    peer_data(l, RCID_A, 2, "A2", 2);
    peer_data(l, RCID_B, 2, "B2", 2);
    peer_data(l, RCID_A, 3, "A3", 2);
    expect(qcom_glink_poll(&l->g) >= 0, "poll delivers three interleaved messages");
    expect_name(l->a_log, "A1;A2;A3;", "the battery slot kept its own order");
    expect_name(l->b_log, "B-only;B2;", "the audio slot kept its own order");

    /* Each filled buffer is returned with its own lcid and index. */
    ap_scan(l, &s);
    expect_eq(s.rx_done_reuse, 5, "every delivered message frees one buffer");
    expect_eq(s.rx_done + s.rx_done_reuse, 5, "no other completion was written");

    /* An open for a name nobody registered answers nothing and touches no slot. */
    peer_open(l, RCID_UNKNOWN, NAME_UNKNOWN);
    expect_eq((unsigned long)qcom_glink_poll(&l->g), 1, "the unknown open was consumed");
    expect_eq(l->g.unknown_opens, 1, "it is counted as unknown");
    expect_name(l->g.last_unknown, NAME_UNKNOWN, "its name is kept for the log");
    expect_name(l->g.unknown_names, NAME_UNKNOWN, "its name is listed once");
    ap_scan(l, &s);
    expect_eq(s.unknown_open_ack, 0, "an unknown open is never acknowledged");
    expect_eq(l->a_up, 1, "the battery channel stayed up");
    expect_eq(l->b_up, 1, "the audio channel stayed up");
    expect_eq(l->a_states, 1, "the battery channel was not reset");
    expect_eq(l->b_states, 1, "the audio channel was not reset");

    /* A message for an rcid nobody owns is dropped, not delivered anywhere. */
    peer_data(l, RCID_NOBODY, 1, "ghost", 5);
    expect(qcom_glink_poll(&l->g) >= 0, "the stray message does not stop the link");
    expect_eq(l->g.dropped, 1, "it is counted as dropped");
    expect_name(l->a_log, "A1;A2;A3;", "the battery slot saw no stray");
    expect_name(l->b_log, "B-only;B2;", "the audio slot saw no stray");
}

static void intent_cases(void)
{
    Link *l = &link;
    char payload[32];
    unsigned lcid;
    uint32_t id;
    Scan s;

    /* The remote advertises a send buffer for the battery slot only. */
    peer_intent(l, RCID_A, 64, 0x1001);
    expect(qcom_glink_poll(&l->g) >= 0, "poll takes the remote intent");
    expect_eq(l->a->remote[0].valid, 1, "the battery slot got the intent");
    expect_eq(l->a->remote[0].size, 64, "with its size");
    expect_eq(l->b->remote[0].valid, 0, "the audio slot got nothing");

    /* So a send from the audio slot cannot go out yet. */
    expect_eq((unsigned long)qcom_glink_send(&l->g, l->b, "x", 1), (unsigned long)QcomGlinkAgain,
              "the audio slot has no remote intent");
    ap_scan(l, &s);
    expect_eq(s.intent_req, 1, "the audio slot asked the DSP for one intent");
    expect_eq(s.data, 0, "and sent no data");

    /* The battery slot sends inside its own intent. */
    expect_eq((unsigned long)qcom_glink_send(&l->g, l->a, "hi", 2), (unsigned long)QcomGlinkOk,
              "the battery slot sends");
    expect(ap_read_data(l, &lcid, &id, payload, sizeof payload) != 0, "the data is on the wire");
    expect_eq(lcid, 1, "it carries the battery lcid");
    expect_eq(id, 0x1001, "it uses the battery slot's remote intent");
    expect_name(payload, "hi", "the payload survived");
    expect_eq(l->a->remote[0].busy, 1, "the intent is busy until the DSP reads it");
    expect_eq(l->b->remote[0].valid, 0, "the audio slot's table is still empty");

    /* The DSP reads it and reuses the intent. */
    peer_cmd(l, QCOM_GLINK_RX_DONE_W_REUSE, RCID_A, 0x1001);
    expect(qcom_glink_poll(&l->g) >= 0, "poll takes the completion");
    expect_eq(l->a->remote[0].busy, 0, "the intent is free again");
    expect_eq(l->a->remote[0].valid, 1, "and still advertised");
}

static void teardown_cases(void)
{
    Link *l = &link;

    qcom_glink_stop(&l->g);
    expect_eq(l->g.broken, 1, "stop marks the link broken");
    expect_eq(l->a_up, 0, "the battery channel is told it is down");
    expect_eq(l->b_up, 0, "the audio channel is told it is down");
    expect_eq(l->a_states, 2, "the battery channel saw exactly one more transition");
    expect_eq(l->b_states, 2, "the audio channel saw exactly one more transition");
    qcom_glink_stop(&l->g);
    expect_eq(l->a_states, 2, "a second stop is a no-op");
    expect_eq(l->b_states, 2, "a second stop is a no-op");
    expect(qcom_glink_poll(&l->g) < 0, "a broken link refuses to poll");
    expect_eq((unsigned long)qcom_glink_send(&l->g, l->a, "x", 1), (unsigned long)QcomGlinkNotOpen,
              "a broken link refuses to send");
}

static void replay_cases(void)
{
    Link *l = &replay;
    Scan s;

    bring_up(l);

    /* A promised buffer is filled once and handed over. */
    peer_data(l, RCID_B, 1, "once", 4);
    expect(qcom_glink_poll(&l->g) >= 0, "poll delivers");
    expect_name(l->b_log, "once;", "the audio consumer got it");

    /* The same chunk again: no dedupe exists, so it is delivered again -- to
     * the same consumer, never to the other one. */
    peer_data(l, RCID_B, 1, "again", 5);
    expect(qcom_glink_poll(&l->g) >= 0, "a replayed chunk is handled");
    expect_name(l->b_log, "once;again;", "the replay went to the same consumer");
    expect_name(l->a_log, "", "the replay never reached the other consumer");

    /* Out of order: a liid the audio slot never advertised is a broken stream,
     * not a message for somebody else. */
    peer_data(l, RCID_B, 2, "B2", 2);
    expect(qcom_glink_poll(&l->g) >= 0, "the audio slot's second buffer is used");
    expect_name(l->b_log, "once;again;B2;", "the audio consumer kept the order");
    expect_name(l->a_log, "", "still nothing on the battery slot");

    ap_scan(l, &s);
    expect_eq(s.data, 0, "the AP sent no data of its own");
    expect_eq(s.rx_done_reuse, 3, "three completions for three deliveries");

    /* A chunk whose index is out of range stops the link instead of being
     * delivered to the wrong slot. */
    peer_data(l, RCID_B, 3, "bad", 3);
    expect(qcom_glink_poll(&l->g) < 0, "an out-of-range index is corrupt");
    expect_eq(l->g.broken, 1, "the link is stopped");
    expect_name(l->a_log, "", "the battery slot never saw the audio traffic");
    expect_eq(l->b_log[0] != 0, 1, "the audio log is unchanged by the corrupt message");
    expect(strstr(l->b_log, "bad") == 0, "the corrupt chunk was not delivered");
}

static void geometry_cases(void)
{
    Link *l = &replay;
    QcomGlinkFifo tx, rx;

    memset(l, 0, sizeof *l);
    l->client.state = on_state;
    l->client.receive = on_receive;
    tx = (QcomGlinkFifo){&l->txhead, &l->txtail, l->txdata, FIFO_BYTES};
    rx = (QcomGlinkFifo){&l->rxhead, &l->rxtail, l->rxdata, FIFO_BYTES};
    l->rxtail = 8;
    expect_eq((unsigned long)qcom_glink_adopt(&l->g, tx, rx, on_kick, l), (unsigned long)QcomGlinkArgument,
              "a receive FIFO that is not at zero is refused");
    l->rxtail = 0;
    l->txhead = 8;
    expect_eq((unsigned long)qcom_glink_adopt(&l->g, tx, rx, on_kick, l), (unsigned long)QcomGlinkArgument,
              "a transmit FIFO that is not at zero is refused");
    l->txhead = 0;
    l->txdata[0] = 0;
    tx.length = 4004;   /* 4000 is a multiple of eight: the check is on the low bits. */
    expect_eq((unsigned long)qcom_glink_adopt(&l->g, tx, rx, on_kick, l), (unsigned long)QcomGlinkArgument,
              "a FIFO that is not a multiple of eight is refused");
    tx.length = FIFO_BYTES;
    expect_eq((unsigned long)qcom_glink_adopt(&l->g, tx, rx, 0, l), (unsigned long)QcomGlinkArgument,
              "a link without a doorbell is refused");
    expect_eq((unsigned long)qcom_glink_adopt(&l->g, tx, rx, on_kick, l), (unsigned long)QcomGlinkOk,
              "the same geometry is accepted once it is well formed");
    expect_eq(qcom_glink_channel(&l->g, NAME_A, 256, 0, l->storage_a, &l->client, l, 1) == 0, 1,
              "zero receive intents is refused");
    expect_eq(qcom_glink_channel(&l->g, NAME_A, 256, QCOM_GLINK_MAX_LOCAL_INTENTS + 1u, l->storage_a, &l->client, l, 1) == 0, 1,
              "more receive intents than the table holds is refused");
    expect_eq(qcom_glink_channel(&l->g, "", 256, 1, l->storage_a, &l->client, l, 1) == 0, 1,
              "a nameless channel is refused");
    expect_eq(qcom_glink_channel(&l->g, "no_storage", 256, 1, 0, &l->client, l, 1) == 0, 1,
              "a channel without storage is refused");
}

static void bridge_cases(void)
{
    Link *l = &bridge_link;
    K60AudioGlink bridge, empty;
    K60PmicGlinkAudioClient client;
    BridgeSink sink;
    unsigned lcid;
    char name[QCOM_GLINK_NAME];
    uint32_t size, index;

    memset(l, 0, sizeof *l);
    memset(&sink, 0, sizeof sink);
    l->client.state = on_state;
    l->client.receive = on_receive;
    const QcomGlinkFifo tx = {&l->txhead, &l->txtail, l->txdata, FIFO_BYTES};
    const QcomGlinkFifo rx = {&l->rxhead, &l->rxtail, l->rxdata, FIFO_BYTES};
    expect_eq((unsigned long)qcom_glink_adopt(&l->g, tx, rx, on_kick, l), (unsigned long)QcomGlinkOk,
              "bridge: the transport adopts");

    k60_audio_glink_init(&bridge, &l->g);
    client.state = bridge_state;
    client.receive = bridge_receive;
    expect_eq((unsigned long)(long)k60_audio_glink_service(&bridge), 0,
              "bridge: service without a request is a no-op");
    expect_eq((unsigned long)(long)k60_audio_glink_request(&bridge, 0, 0),
              (unsigned long)(long)K60_PMIC_GLINK_AUDIO_REFUSED,
              "bridge: a null client is refused");
    expect_eq((unsigned long)(long)k60_audio_glink_request(&bridge, &client, &sink), 0,
              "bridge: the audio client is queued");
    expect_eq(k60_audio_glink_ready(&bridge), 0, "bridge: queued is not ready");
    expect_eq((unsigned long)(long)k60_audio_glink_service(&bridge), 0,
              "bridge: the workloop registers the queued slot");
    expect(bridge.channel != 0, "bridge: the adsp_apps slot exists");
    if (!bridge.channel) return;
    expect_name(bridge.channel->name, K60_AUDIO_GLINK_NAME, "bridge: the slot carries adsp_apps");
    expect_eq(bridge.channel->intent_count, K60_AUDIO_GLINK_INTENT_COUNT,
              "bridge: twenty receive intents");
    expect_eq(bridge.channel->intent_size, K60_AUDIO_GLINK_INTENT_BYTES,
              "bridge: 512-byte intents");
    expect_eq(k60_audio_glink_ready(&bridge), 0, "bridge: registered is not up");

    expect(qcom_glink_poll(&l->g) >= 0, "bridge: poll writes VERSION");
    expect(ap_read_cmd(l, &lcid, &size, &index) != 0, "bridge: VERSION is on the wire");
    expect_eq(lcid, QCOM_GLINK_VERSION, "bridge: first message is VERSION");
    peer_cmd(l, QCOM_GLINK_VERSION_ACK, 1, QCOM_GLINK_FEATURE_INTENT_REUSE);
    expect(qcom_glink_poll(&l->g) >= 0, "bridge: poll after VERSION_ACK");
    expect(ap_read_open(l, &lcid, name, sizeof name) != 0, "bridge: OPEN is emitted");
    expect_eq(lcid, 1, "bridge: the audio slot is lcid 1");
    expect_name(name, K60_AUDIO_GLINK_NAME, "bridge: OPEN names adsp_apps");

    peer_open(l, 0x31, K60_AUDIO_GLINK_NAME);
    expect(qcom_glink_poll(&l->g) >= 0, "bridge: the DSP opens adsp_apps");
    expect(ap_read_cmd(l, &lcid, &size, &index) != 0, "bridge: OPEN_ACK is emitted");
    expect_eq(lcid, QCOM_GLINK_OPEN_ACK, "bridge: it is an OPEN_ACK");
    expect_eq(size, 0x31, "bridge: the remote rcid is acknowledged");
    peer_cmd(l, QCOM_GLINK_OPEN_ACK, 1, 0);
    expect(qcom_glink_poll(&l->g) >= 0, "bridge: poll after OPEN_ACK");
    for (unsigned k = 0; k < K60_AUDIO_GLINK_INTENT_COUNT; ++k) {
        expect(ap_read_intent(l, &lcid, &size, &index) != 0, "bridge: every audio intent is advertised");
        expect_eq(lcid, 1, "bridge: audio intents carry lcid 1");
        expect_eq(size, K60_AUDIO_GLINK_INTENT_BYTES, "bridge: advertised intent size");
        expect_eq(index, k, "bridge: advertised intent index");
    }
    expect_eq(ap_avail(l), 0, "bridge: all twenty intents are on the wire");
    expect_eq(sink.states, 1, "bridge: one state callback");
    expect_eq((unsigned long)sink.up, 1, "bridge: the audio channel is up");
    expect_eq(k60_audio_glink_ready(&bridge), 1, "bridge: ready follows the channel state");

    peer_data(l, 0x31, 1, "pcm", 3);
    expect(qcom_glink_poll(&l->g) >= 0, "bridge: poll delivers audio data");
    expect_name(sink.log, "pcm;", "bridge: the audio callback received its own payload");

    expect_eq((unsigned long)(long)k60_audio_glink_request(&bridge, &client, &sink), 0,
              "bridge: a repeated request is idempotent");
    k60_audio_glink_stop(&bridge);
    expect_eq(k60_audio_glink_ready(&bridge), 0, "bridge: stop drops readiness");

    k60_audio_glink_init(&empty, 0);
    expect_eq((unsigned long)(long)k60_audio_glink_request(&empty, &client, &sink),
              (unsigned long)(long)K60_PMIC_GLINK_AUDIO_NO_TRANSPORT,
              "bridge: no transport is reported as no handoff");
}

int main(void)
{
    printf("two-slot transport: QCOM_GLINK_MAX_CHANNELS=%u, sizeof(QcomGlinkChannel)=%zu, sizeof(QcomGlink)=%zu\n",
           (unsigned)QCOM_GLINK_MAX_CHANNELS, sizeof(QcomGlinkChannel), sizeof(QcomGlink));
    expect_eq(QCOM_GLINK_MAX_CHANNELS, 2, "the transport under test really has two slots");

    delivery_cases();
    intent_cases();
    teardown_cases();
    replay_cases();
    geometry_cases();
    bridge_cases();

    if (fails) {printf("TESTS FAILED %u of %u cases\n", fails, cases); return 1;}
    printf("TESTS OK %u cases\n", cases);
    return 0;
}
