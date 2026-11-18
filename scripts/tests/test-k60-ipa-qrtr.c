/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Host test for K60IpaQrtr: announce/lookup bytes, endpoint discovery,
 * INIT_DRIVER framing, modem requests, the single completion, BYE and the
 * send-failure flush path. No device involved. */

#include <stdio.h>
#include <string.h>

#include "K60IpaQrtr.h"

#define MAX_PACKETS 16

typedef struct {
	uint8_t data[MAX_PACKETS][512];
	size_t length[MAX_PACKETS];
	size_t count;
	int attempts;
	int fail;
} Link;

static int failures;

static void
check(int condition, const char *name)
{
	if (!condition) {
		printf("FAIL %s\n", name);
		failures++;
	}
}

static void
set32(uint8_t *p, uint32_t value)
{
	p[0] = (uint8_t)value;
	p[1] = (uint8_t)(value >> 8);
	p[2] = (uint8_t)(value >> 16);
	p[3] = (uint8_t)(value >> 24);
}

static void
put_header(uint8_t *p, uint32_t type, uint32_t from_node, uint32_t from_port,
    uint32_t size, uint32_t to_node, uint32_t to_port)
{
	set32(p + 0, K60_QRTR_VERSION);
	set32(p + 4, type);
	set32(p + 8, from_node);
	set32(p + 12, from_port);
	set32(p + 16, 0);
	set32(p + 20, size);
	set32(p + 24, to_node);
	set32(p + 28, to_port);
}

static size_t
new_server(uint8_t *out, uint32_t from_node, uint32_t service,
    uint32_t instance, uint32_t node, uint32_t port, uint32_t to_node)
{
	put_header(out, K60QrtrNewServer, from_node, K60_QRTR_CONTROL_PORT,
	    K60_QRTR_CONTROL_BYTES, to_node, K60_QRTR_CONTROL_PORT);
	set32(out + 32, K60QrtrNewServer);
	set32(out + 36, service);
	set32(out + 40, instance);
	set32(out + 44, node);
	set32(out + 48, port);
	return K60_QRTR_LOOKUP_BYTES;
}

static size_t
data_packet(uint8_t *out, uint32_t from_node, uint32_t from_port,
    uint32_t to_port, const uint8_t *qmi, size_t qmi_bytes)
{
	size_t padded = (qmi_bytes + 3u) & ~(size_t)3u;

	put_header(out, K60QrtrData, from_node, from_port, (uint32_t)qmi_bytes,
	    K60_QRTR_AP_NODE, to_port);
	memset(out + 32, 0, padded);
	memcpy(out + 32, qmi, qmi_bytes);
	return K60_QRTR_HEADER_BYTES + padded;
}

static size_t
qmi_request(uint8_t *out, uint16_t transaction, uint16_t message)
{
	memset(out, 0, 7);
	out[0] = K60_QMI_REQUEST;
	out[1] = (uint8_t)transaction;
	out[2] = (uint8_t)(transaction >> 8);
	out[3] = (uint8_t)message;
	out[4] = (uint8_t)(message >> 8);
	out[5] = 0;
	out[6] = 0;
	return 7;
}

static size_t
qmi_status_request(uint8_t *out, uint16_t transaction, uint8_t status)
{
	qmi_request(out, transaction, K60_IPA_QMI_DRIVER_INIT_COMPLETE);
	out[5] = 4;
	out[6] = 0;
	out[7] = K60_IPA_QMI_TLV_DRIVER_STATUS;
	out[8] = 1;
	out[9] = 0;
	out[10] = status;
	return 11;
}

static size_t
qmi_response(uint8_t *out, uint16_t transaction, uint16_t message)
{
	memset(out, 0, 14);
	out[0] = K60_QMI_RESPONSE;
	out[1] = (uint8_t)transaction;
	out[2] = (uint8_t)(transaction >> 8);
	out[3] = (uint8_t)message;
	out[4] = (uint8_t)(message >> 8);
	out[5] = 7;
	out[6] = 0;
	out[7] = K60_IPA_QMI_TLV_RESULT;
	out[8] = 4;
	out[9] = 0;
	out[10] = 0;
	out[11] = 0;
	out[12] = 0;
	out[13] = 0;
	return 14;
}

static int
send_link(void *context, const uint8_t *packet, size_t bytes)
{
	Link *link = (Link *)context;

	link->attempts++;
	if (link->fail != 0) {
		return -1;
	}
	if (link->count >= MAX_PACKETS) {
		return -1;
	}
	memcpy(link->data[link->count], packet, bytes);
	link->length[link->count] = bytes;
	link->count++;
	return 0;
}

/* Returns the payload length of the captured packet or 0. */
static size_t
captured_payload(const Link *link, size_t index, K60QrtrHeader *header,
    const uint8_t **payload)
{
	if (index >= link->count) {
		return 0;
	}
	if (k60_qrtr_parse(link->data[index], link->length[index], header,
	    payload) != K60QrtrOk) {
		return 0;
	}
	return header->size;
}

int
main(void)
{
	Link link;
	K60IpaQrtr session;
	K60QrtrHeader header;
	const uint8_t *payload;
	uint8_t packet[512];
	uint8_t qmi[128];
	uint8_t expected[512];
	size_t bytes, length;
	uint32_t built;

	memset(&link, 0, sizeof(link));
	k60_ipa_qrtr_reset(&session, 0x8b900000u, send_link, &link);
	check(session.remote_known == 0, "reset clears the endpoint");

	/* Announce and lookup must be the exact builders the link already uses. */
	check(k60_ipa_qrtr_announce(&session, K60_QRTR_BROADCAST_NODE) ==
	    K60IpaQrtrOk, "announce");
	check(link.count == 1 && link.length[0] == K60_QRTR_LOOKUP_BYTES,
	    "announce length");
	built = k60_qrtr_build_new_server(expected, sizeof(expected),
	    K60_IPA_QMI_SERVICE, K60_IPA_QMI_INSTANCE_AP,
	    K60_QRTR_BROADCAST_NODE, K60_IPA_QMI_HOST_PORT);
	check(built == link.length[0] &&
	    memcmp(expected, link.data[0], built) == 0, "announce bytes");
	check(k60_ipa_qrtr_lookup(&session, K60_QRTR_BROADCAST_NODE) ==
	    K60IpaQrtrOk, "lookup");
	built = k60_qrtr_build_lookup(expected, sizeof(expected),
	    K60_QRTR_BROADCAST_NODE);
	check(link.count == 2 && built == link.length[1] &&
	    memcmp(expected, link.data[1], built) == 0, "lookup bytes");

	/* The name service reports the modem's own 49/0x201 endpoint. */
	bytes = new_server(packet, 0, K60_IPA_QMI_SERVICE,
	    K60_IPA_QMI_INSTANCE_MODEM, 42, 0x4001, K60_QRTR_AP_NODE);
	check(k60_ipa_qrtr_receive(&session, packet, bytes) == K60IpaQrtrOk,
	    "discovery");
	check(session.remote_known == 1 && session.remote_node == 42 &&
	    session.remote_port == 0x4001, "endpoint recorded");
	check(link.count == 3, "one INIT_DRIVER sent");
	length = captured_payload(&link, 2, &header, &payload);
	check(header.type == K60QrtrData && header.from_node == K60_QRTR_AP_NODE &&
	    header.from_port == K60_IPA_QMI_CLIENT_PORT &&
	    header.to_node == 42 && header.to_port == 0x4001,
	    "INIT_DRIVER datagram header");
	check(length == K60_IPA_QMI_INIT_DRIVER_BYTES, "INIT_DRIVER length");
	check(payload != NULL && payload[0] == K60_QMI_REQUEST &&
	    payload[3] == K60_IPA_QMI_INIT_DRIVER, "INIT_DRIVER message");

	/* Modem response to INIT_DRIVER: no reply, but the state advances. */
	bytes = qmi_response(qmi, 1, K60_IPA_QMI_INIT_DRIVER);
	length = data_packet(packet, 42, 0x4001, K60_IPA_QMI_HOST_PORT, qmi,
	    bytes);
	check(k60_ipa_qrtr_receive(&session, packet, length) == K60IpaQrtrOk,
	    "init response");
	check(link.count == 3, "init response draws no reply");

	/* INDICATION_REGISTER: exactly one 14-byte response from the server port. */
	bytes = qmi_request(qmi, 7, K60_IPA_QMI_INDICATION_REGISTER);
	length = data_packet(packet, 42, 0x4001, K60_IPA_QMI_HOST_PORT, qmi,
	    bytes);
	check(k60_ipa_qrtr_receive(&session, packet, length) == K60IpaQrtrOk,
	    "subscribe request");
	check(link.count == 4, "subscribe answered");
	length = captured_payload(&link, 3, &header, &payload);
	check(header.from_port == K60_IPA_QMI_HOST_PORT &&
	    header.to_port == 0x4001 && length == K60_IPA_QMI_SIMPLE_BYTES,
	    "subscribe reply envelope");
	check(payload != NULL && payload[0] == K60_QMI_RESPONSE &&
	    payload[3] == K60_IPA_QMI_INDICATION_REGISTER, "subscribe reply id");

	/* DRIVER_INIT_COMPLETE: reply plus the single INIT_COMPLETE indication. */
	bytes = qmi_status_request(qmi, 8, 1);
	length = data_packet(packet, 42, 0x4001, K60_IPA_QMI_HOST_PORT, qmi,
	    bytes);
	check(k60_ipa_qrtr_receive(&session, packet, length) == K60IpaQrtrOk,
	    "status request");
	check(link.count == 6, "status reply and completion");
	length = captured_payload(&link, 5, &header, &payload);
	check(length == K60_IPA_QMI_SIMPLE_BYTES && payload != NULL &&
	    payload[0] == K60_QMI_INDICATION &&
	    payload[3] == K60_IPA_QMI_INIT_COMPLETE, "completion indication");
	check(k60_ipa_qrtr_ready(&session) == 1, "ready after delivery");

	/* A late request still gets one reply and never a second completion. */
	bytes = qmi_request(qmi, 9, K60_IPA_QMI_INDICATION_REGISTER);
	length = data_packet(packet, 42, 0x4001, K60_IPA_QMI_HOST_PORT, qmi,
	    bytes);
	check(k60_ipa_qrtr_receive(&session, packet, length) == K60IpaQrtrOk,
	    "late request");
	check(link.count == 7, "late request draws only a reply");

	/* BYE drops the endpoint; traffic from it is then ignored. */
	put_header(packet, K60QrtrBye, 42, 0x4001, 0, K60_QRTR_AP_NODE,
	    K60_IPA_QMI_HOST_PORT);
	check(k60_ipa_qrtr_receive(&session, packet, K60_QRTR_HEADER_BYTES) ==
	    K60IpaQrtrOk, "bye");
	check(session.remote_known == 0, "bye clears the endpoint");
	bytes = qmi_request(qmi, 10, K60_IPA_QMI_INDICATION_REGISTER);
	length = data_packet(packet, 42, 0x4001, K60_IPA_QMI_HOST_PORT, qmi,
	    bytes);
	check(k60_ipa_qrtr_receive(&session, packet, length) ==
	    K60IpaQrtrIgnored, "stale endpoint ignored");

	/* A failed link write keeps the INIT_DRIVER queued for flush. */
	memset(&link, 0, sizeof(link));
	k60_ipa_qrtr_reset(&session, 0x8b900000u, send_link, &link);
	link.fail = 1;
	bytes = new_server(packet, 0, K60_IPA_QMI_SERVICE,
	    K60_IPA_QMI_INSTANCE_MODEM, 42, 0x4001, K60_QRTR_AP_NODE);
	check(k60_ipa_qrtr_receive(&session, packet, bytes) ==
	    K60IpaQrtrSendFailed, "failed send reported");
	check(link.attempts == 1 && link.count == 0, "nothing delivered");
	link.fail = 0;
	check(k60_ipa_qrtr_flush(&session) == K60IpaQrtrOk, "flush");
	check(link.count == 1 && link.length[0] == K60_QRTR_HEADER_BYTES +
	    ((K60_IPA_QMI_INIT_DRIVER_BYTES + 3u) & ~(size_t)3u),
	    "flush delivers the queued frame");

	/* Argument and shape errors. */
	check(k60_ipa_qrtr_receive(&session, packet, 8) == K60IpaQrtrMalformed,
	    "short datagram");
	check(k60_ipa_qrtr_announce(NULL, 0) == K60IpaQrtrBadArgument,
	    "null announce");
	check(k60_ipa_qrtr_lookup(NULL, 0) == K60IpaQrtrBadArgument,
	    "null lookup");
	check(k60_ipa_qrtr_receive(NULL, packet, 52) == K60IpaQrtrBadArgument,
	    "null session");
	check(k60_ipa_qrtr_ready(NULL) == 0, "null ready");
	memset(&link, 0, sizeof(link));
	k60_ipa_qrtr_reset(&session, 0, send_link, &link);
	bytes = new_server(packet, 0, K60_IPA_QMI_SERVICE, 0x999, 42, 0x4001,
	    K60_QRTR_AP_NODE);
	check(k60_ipa_qrtr_receive(&session, packet, bytes) ==
	    K60IpaQrtrIgnored, "other instance ignored");
	bytes = new_server(packet, 0, K60_IPA_QMI_SERVICE,
	    K60_IPA_QMI_INSTANCE_MODEM, 0, 0x4001, K60_QRTR_AP_NODE);
	check(k60_ipa_qrtr_receive(&session, packet, bytes) ==
	    K60IpaQrtrMalformed, "node zero rejected");
	bytes = new_server(packet, 0, 2, 0x201, 42, 0x4001,
	    K60_QRTR_AP_NODE);
	check(k60_ipa_qrtr_receive(&session, packet, bytes) ==
	    K60IpaQrtrIgnored, "other service ignored");

	if (failures != 0) {
		printf("K60 IPA QRTR FAIL %d\n", failures);
		return 1;
	}
	printf("K60 IPA QRTR PASS announce lookup discovery init-driver response "
	    "subscribe completion bye failures\n");
	return 0;
}
