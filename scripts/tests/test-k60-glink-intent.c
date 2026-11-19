/*
 * Host test for the GLINK receive-intent list and the D9 divergence.
 *
 * 0622-k60-modem-qrtr.patch (the cellular line's copy of bsd/dev/qcom_glink.c)
 * rejects the whole intent message when one entry has size 0:
 *
 *     if (!size) return QcomGlinkCorrupt;  /\* id 0 is a legal buffer number *\/
 *
 * This tree keeps the per-entry drop instead (drivers/PongPower/QcomGlink.c):
 * id 0 is a valid intent id, so a zero-size entry is a placeholder the sender
 * never filled, not corruption of its neighbours.  The lead accepted the
 * divergence on 2026-11-19 and asked for two things, both pinned here:
 *
 *   1. a test where a zero-length intent is followed by a normal intent, and
 *      the normal one is still processed (usable end to end, not merely stored);
 *   2. the divergence written down, so a future cellular merge does not
 *      "fix" it back to a whole-list rejection.
 *
 *   cc -std=c11 -O1 -Wall -Wextra -Werror -I drivers/PongPower \
 *      -o build/glinkintent scripts/tests/test-k60-glink-intent.c \
 *      drivers/PongPower/QcomGlink.c
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stddef.h>

#include "QcomGlink.h"

static int failures;
static int checks;

#define CHECK(cond) do { \
    checks++; \
    if (!(cond)) { \
        printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #cond); \
        failures++; \
    } \
} while (0)

#define RX_LEN 1024u
#define TX_LEN 1024u
#define INTENT_SIZE 256u

static uint32_t rx_head, rx_tail, tx_head, tx_tail;
static uint8_t rx_bytes[RX_LEN], tx_bytes[TX_LEN];
static QcomGlink g;
static uint8_t storage[INTENT_SIZE];
static int kicks, state_calls, receive_calls;
static uint32_t received_len;
static uint8_t received[INTENT_SIZE];

static void
client_state(void *context, QcomGlinkChannel *channel, int up)
{
	(void)context;
	(void)channel;
	(void)up;
	state_calls++;
}

static void
client_receive(void *context, QcomGlinkChannel *channel, const uint8_t *data, uint32_t length)
{
	(void)context;
	(void)channel;
	receive_calls++;
	received_len = length;
	if (length > sizeof received)
		length = sizeof received;
	memcpy(received, data, length);
}

static void
kick(void *context)
{
	(void)context;
	kicks++;
}

static const QcomGlinkClient client = {client_state, client_receive};

static void
put32(uint8_t *p, uint32_t v)
{
	p[0] = (uint8_t)(v & 0xff);
	p[1] = (uint8_t)((v >> 8) & 0xff);
	p[2] = (uint8_t)((v >> 16) & 0xff);
	p[3] = (uint8_t)((v >> 24) & 0xff);
}

static uint32_t
le32(const uint8_t *p)
{
	return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

/* The remote writes at head and advances it, exactly as the DSP does. */
static void
rx_put(const void *bytes, uint32_t count)
{
	const uint8_t *p = (const uint8_t *)bytes;

	for (uint32_t i = 0; i < count; ++i) {
		rx_bytes[rx_head] = p[i];
		if (++rx_head == RX_LEN)
			rx_head = 0;
	}
}

static void
rx_pad(uint32_t count)
{
	static const uint8_t zero[8] = {0};

	while (count >= 8) {
		rx_put(zero, 8);
		count -= 8;
	}
	if (count)
		rx_put(zero, count);
}

static void
rx_cmd(uint16_t cmd, uint16_t param1, uint32_t param2)
{
	uint8_t m[8];

	m[0] = (uint8_t)(cmd & 0xff);
	m[1] = (uint8_t)(cmd >> 8);
	m[2] = (uint8_t)(param1 & 0xff);
	m[3] = (uint8_t)(param1 >> 8);
	put32(m + 4, param2);
	rx_put(m, 8);
}

static void
rx_open(uint16_t rcid, const char *name)
{
	const uint32_t n = (uint32_t)strlen(name) + 1;

	rx_cmd(QCOM_GLINK_OPEN, rcid, n);
	rx_put(name, n);
	rx_pad((8u - (n & 7u)) & 7u);
}

static void
rx_intent(uint16_t rcid, const uint32_t *sizes, const uint32_t *ids, uint32_t count)
{
	rx_cmd(QCOM_GLINK_INTENT, rcid, count);
	for (uint32_t i = 0; i < count; ++i) {
		uint8_t entry[8];

		put32(entry, sizes[i]);
		put32(entry + 4, ids[i]);
		rx_put(entry, 8);
	}
}

static void
rx_data(uint16_t rcid, uint32_t liid, const void *payload, uint32_t count)
{
	uint8_t h[16];

	h[0] = (uint8_t)QCOM_GLINK_TX_DATA;
	h[1] = 0;
	h[2] = (uint8_t)(rcid & 0xff);
	h[3] = (uint8_t)(rcid >> 8);
	put32(h + 4, liid);
	put32(h + 8, count);
	put32(h + 12, 0);
	rx_put(h, 16);
	rx_put(payload, count);
	rx_pad((8u - (count & 7u)) & 7u);
}

static QcomGlinkChannel *
setup(void)
{
	QcomGlinkFifo tx = {&tx_head, &tx_tail, tx_bytes, TX_LEN};
	QcomGlinkFifo rx = {&rx_head, &rx_tail, rx_bytes, RX_LEN};

	rx_head = rx_tail = tx_head = tx_tail = 0;
	memset(rx_bytes, 0, sizeof rx_bytes);
	memset(tx_bytes, 0, sizeof tx_bytes);
	memset(&g, 0, sizeof g);
	memset(storage, 0, sizeof storage);
	kicks = state_calls = receive_calls = 0;
	received_len = 0;

	CHECK(qcom_glink_adopt(&g, tx, rx, kick, 0) == QcomGlinkOk);
	QcomGlinkChannel *c = qcom_glink_channel(&g, "k60-pmic", INTENT_SIZE, 1, storage, &client, 0, 1);
	CHECK(c != 0);
	return c;
}

/* Version handshake, the remote's OPEN and its OPEN_ACK: the channel is up. */
static void
bring_up(QcomGlinkChannel *c, uint16_t rcid)
{
	rx_cmd(QCOM_GLINK_VERSION, 1, QCOM_GLINK_FEATURE_INTENT_REUSE);
	rx_open(rcid, "k60-pmic");
	CHECK(qcom_glink_poll(&g) >= 0);
	rx_cmd(QCOM_GLINK_OPEN_ACK, c->lcid, 0);
	CHECK(qcom_glink_poll(&g) >= 0);
	CHECK(c->up == 1);
}

/* A send that went out must name the surviving intent id, not the dropped one. */
static void
check_send_used_intent(QcomGlinkChannel *c, uint32_t want_id, const char *want)
{
	const uint32_t want_len = (uint32_t)strlen(want);
	/* The message we are about to send is appended at the current head. */
	const uint32_t at = tx_head;

	CHECK(qcom_glink_send(&g, c, want, want_len) == QcomGlinkOk);
	CHECK(at + 16 + want_len <= tx_head);
	CHECK(tx_bytes[at] == QCOM_GLINK_TX_DATA);
	CHECK(le32(tx_bytes + at + 4) == want_id);
	CHECK(le32(tx_bytes + at + 8) == want_len);
	CHECK(le32(tx_bytes + at + 12) == 0);
	CHECK(memcmp(tx_bytes + at + 16, want, want_len) == 0);
}

/* 1. The lead's case: a zero-length intent, then a normal one, still usable. */
static void
zero_then_valid(void)
{
	const uint32_t sizes[] = {0, 1024}, ids[] = {5, 7};
	QcomGlinkChannel *c = setup();

	bring_up(c, 0x40);
	rx_intent(0x40, sizes, ids, 2);
	CHECK(qcom_glink_poll(&g) >= 0);
	CHECK(g.broken == 0);
	CHECK(g.dropped == 1);
	CHECK(c->remote[0].valid == 1);
	CHECK(c->remote[0].id == 7);
	CHECK(c->remote[0].size == 1024);
	CHECK(c->remote[1].valid == 0);
	check_send_used_intent(c, 7, "hi");
}

/* 2. The drop is not sticky: a later intent message is accepted normally. */
static void
zero_only_then_later_valid(void)
{
	const uint32_t zero_size[] = {0}, zero_id[] = {9};
	const uint32_t later_size[] = {512}, later_id[] = {11};
	QcomGlinkChannel *c = setup();

	bring_up(c, 0x40);
	rx_intent(0x40, zero_size, zero_id, 1);
	CHECK(qcom_glink_poll(&g) >= 0);
	CHECK(g.broken == 0);
	CHECK(g.dropped == 1);
	CHECK(c->remote[0].valid == 0);

	rx_intent(0x40, later_size, later_id, 1);
	CHECK(qcom_glink_poll(&g) >= 0);
	CHECK(g.broken == 0);
	CHECK(g.dropped == 1);
	CHECK(c->remote[0].valid == 1);
	CHECK(c->remote[0].id == 11);
	CHECK(c->remote[0].size == 512);
}

/* 3. Neighbours on both sides survive: ids 1 and 3 land, id 2 is dropped. */
static void
valid_zero_valid(void)
{
	const uint32_t sizes[] = {256, 0, 256}, ids[] = {1, 2, 3};
	QcomGlinkChannel *c = setup();

	bring_up(c, 0x40);
	rx_intent(0x40, sizes, ids, 3);
	CHECK(qcom_glink_poll(&g) >= 0);
	CHECK(g.broken == 0);
	CHECK(g.dropped == 1);
	CHECK(c->remote[0].valid == 1);
	CHECK(c->remote[0].id == 1);
	CHECK(c->remote[1].valid == 1);
	CHECK(c->remote[1].id == 3);
	CHECK(c->remote[2].valid == 0);
}

/* 4. Every placeholder is counted, and a list of nothing but placeholders is
 *    still a valid message rather than a corrupt one. */
static void
all_zero_entries(void)
{
	const uint32_t sizes[] = {0, 0}, ids[] = {1, 2};
	QcomGlinkChannel *c = setup();

	bring_up(c, 0x40);
	rx_intent(0x40, sizes, ids, 2);
	CHECK(qcom_glink_poll(&g) >= 0);
	CHECK(g.broken == 0);
	CHECK(g.dropped == 2);
	CHECK(c->remote[0].valid == 0);
	CHECK(c->remote[1].valid == 0);
}

/* 5. The stream keeps flowing: data arrives after the dropped placeholder. */
static void
stream_continues(void)
{
	const uint32_t sizes[] = {0, 1024}, ids[] = {5, 7};
	QcomGlinkChannel *c = setup();

	bring_up(c, 0x40);
	rx_intent(0x40, sizes, ids, 2);
	CHECK(qcom_glink_poll(&g) >= 0);
	CHECK(g.dropped == 1);

	rx_data(0x40, 1, "abc", 3);
	CHECK(qcom_glink_poll(&g) >= 0);
	CHECK(g.broken == 0);
	CHECK(receive_calls == 1);
	CHECK(received_len == 3);
	CHECK(memcmp(received, "abc", 3) == 0);
	CHECK(g.rx_data == 1);
}

int
main(void)
{
	zero_then_valid();
	zero_only_then_later_valid();
	valid_zero_valid();
	all_zero_entries();
	stream_continues();

	printf("glink: %d checks, %d failures\n", checks, failures);
	if (failures) {
		printf("FAILURES: %d\n", failures);
		return 1;
	}
	printf("TESTS OK %d checks\n", checks);
	return 0;
}
