/* Host test for the QRTR wire format: no device, no kernel headers.
 * Build: gcc -O1 -Wall -Wextra -Werror -Idrivers/PongCellular \
 *   -o /mnt/e/k60-work/artifacts/tests/t-modem-qrtr \
 *   scripts/tests/test-k60-modem-qrtr.c drivers/PongCellular/K60ModemQrtr.c */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "K60ModemQrtr.h"

static uint32_t le32(const uint8_t *at)
{
	return (uint32_t)at[0] | (uint32_t)at[1] << 8 | (uint32_t)at[2] << 16 | (uint32_t)at[3] << 24;
}

static uint16_t le16(const uint8_t *at)
{
	return (uint16_t)((uint16_t)at[0] | (uint16_t)at[1] << 8);
}

static void put16(uint8_t *at, uint16_t value)
{
	at[0] = (uint8_t)(value & 0xffu);
	at[1] = (uint8_t)(value >> 8);
}

static void put32(uint8_t *at, uint32_t value)
{
	at[0] = (uint8_t)(value & 0xffu);
	at[1] = (uint8_t)((value >> 8) & 0xffu);
	at[2] = (uint8_t)((value >> 16) & 0xffu);
	at[3] = (uint8_t)((value >> 24) & 0xffu);
}

/* A NEW_SERVER datagram exactly as the modem's name service sends it: a v1
 * header from node 0, port 0xfffffffe, and the 20 byte control payload. */
static size_t server_packet(uint8_t *out, uint32_t service, uint32_t instance, uint32_t node, uint32_t port)
{
	const uint32_t words[8] = {K60_QRTR_VERSION, K60QrtrNewServer, 0, 0xfffffff0u, 0, 20,
	    K60_QRTR_BROADCAST_NODE, K60_QRTR_CONTROL_PORT};
	const uint32_t payload[5] = {K60QrtrNewServer, service, instance, node, port};
	for (unsigned i = 0; i < 8; ++i) {
		put32(out + i * 4, words[i]);
	}
	for (unsigned i = 0; i < 5; ++i) {
		put32(out + 32 + i * 4, payload[i]);
	}
	return 52;
}

static void check_lookup(void)
{
	uint8_t packet[64];
	uint32_t n = k60_qrtr_build_lookup(packet, sizeof(packet), K60_QRTR_BROADCAST_NODE);
	assert(n == 52);
	assert(le32(packet + 0) == 1);                    /* version */
	assert(le32(packet + 4) == 10);                   /* NEW_LOOKUP */
	assert(le32(packet + 8) == K60_QRTR_AP_NODE);     /* from_node: us */
	assert(le32(packet + 12) == 0xfffffffeu);         /* from_port: control */
	assert(le32(packet + 16) == 0);                   /* confirm */
	assert(le32(packet + 20) == 20);                  /* size */
	assert(le32(packet + 24) == 0xffffffffu);         /* broadcast node */
	assert(le32(packet + 28) == 0xfffffffeu);         /* control port */
	assert(le32(packet + 32) == 10);                  /* command */
	assert(le32(packet + 36) == 0 && le32(packet + 48) == 0);
	assert(k60_qrtr_build_lookup(packet, 51, K60_QRTR_BROADCAST_NODE) == 0); /* short buffer */
	assert(k60_qrtr_build_lookup(NULL, 64, K60_QRTR_BROADCAST_NODE) == 0);
	printf("lookup ok: 52 bytes, type 10, node 0xffffffff port 0xfffffffe\n");
}

static void check_hello(void)
{
	uint8_t packet[64];
	assert(k60_qrtr_build_hello(packet, sizeof(packet)) == 52);
	assert(le32(packet + 4) == 2);
	assert(le32(packet + 8) == K60_QRTR_AP_NODE);
	assert(le32(packet + 12) == 0xfffffffeu);
	assert(le32(packet + 32) == 2);
	assert(le32(packet + 24) == K60_QRTR_BROADCAST_NODE);
	printf("hello ok: type 2 from node 1 to the broadcast node\n");
}

static void check_new_server(void)
{
	uint8_t packet[64];
	assert(k60_qrtr_build_new_server(packet, sizeof(packet), K60_QRTR_SERVLOC_SERVICE,
	    K60_QRTR_SERVLOC_INSTANCE, 0, K60_QRTR_LOCATOR_PORT) == 52);
	assert(le32(packet + 4) == K60QrtrNewServer);
	assert(le32(packet + 8) == K60_QRTR_AP_NODE);
	assert(le32(packet + 12) == K60_QRTR_CONTROL_PORT);
	assert(le32(packet + 24) == 0);
	assert(le32(packet + 32) == K60QrtrNewServer);
	assert(le32(packet + 36) == K60_QRTR_SERVLOC_SERVICE);
	assert(le32(packet + 40) == K60_QRTR_SERVLOC_INSTANCE);
	assert(le32(packet + 44) == K60_QRTR_AP_NODE);
	assert(le32(packet + 48) == K60_QRTR_LOCATOR_PORT);
	printf("new_server ok: service 64 instance 0x101 on AP port 0x100\n");
}

static void check_data_and_qmi(void)
{
	uint8_t packet[64], query[16];
	K60QmiMessage message;
	uint32_t n;

	assert(k60_qmi_build_dms_revision(query, sizeof(query), 0x1234) == 7);
	assert(query[0] == K60_QMI_REQUEST);
	assert(le16(query + 1) == 0x1234);
	assert(le16(query + 3) == K60_QMI_DMS_GET_REVISION);
	assert(le16(query + 5) == 0);
	assert(k60_qmi_parse(query, 7, &message) == 0);
	assert(message.type == K60_QMI_REQUEST && message.transaction == 0x1234);
	assert(message.message == K60_QMI_DMS_GET_REVISION && message.length == 0);
	n = k60_qrtr_build_data(packet, sizeof(packet), K60_QRTR_DMS_PORT, 0,
	    K60_QRTR_DMS_SERVICE, query, 7);
	assert(n == 40);                                  /* 32 + 8, padded */
	assert(le32(packet + 4) == K60QrtrData);
	assert(le32(packet + 12) == K60_QRTR_DMS_PORT);
	assert(le32(packet + 20) == 7);                   /* unpadded payload */
	assert(le32(packet + 24) == 0);
	assert(le32(packet + 28) == K60_QRTR_DMS_SERVICE);
	assert(packet[39] == 0);                          /* padding byte */
	assert(k60_qrtr_build_data(packet, 39, K60_QRTR_DMS_PORT, 0, 2, query, 7) == 0);
	printf("data ok: QMI request 7 bytes, QRTR DATA padded to 40\n");
}

static void check_servloc(void)
{
	uint8_t request[64], answer[K60_QRTR_MAX_PACKET];
	K60QmiMessage message;
	uint32_t n, size = 0;
	const char name[] = "tms/servreg";
	const uint8_t *value;

	memset(request, 0, sizeof(request));
	request[0] = K60_QMI_REQUEST;
	put16(request + 1, 0x2222);
	put16(request + 3, 0x21);                         /* GET_DOMAIN_LIST */
	put16(request + 5, (uint16_t)(3 + sizeof(name) - 1));
	request[7] = 0x01;
	put16(request + 8, (uint16_t)(sizeof(name) - 1));
	memcpy(request + 10, name, sizeof(name) - 1);
	n = k60_qrtr_servloc_answer(request, 10 + sizeof(name) - 1, answer, sizeof(answer));
	assert(n != 0);
	assert(k60_qmi_parse(answer, n, &message) == 0);
	assert(message.type == K60_QMI_RESPONSE && message.transaction == 0x2222);
	assert(message.message == 0x21);
	value = k60_qmi_tlv(&message, 0x02, &size);
	assert(value != NULL && size == 4 && le16(value) == 0);
	value = k60_qmi_tlv(&message, 0x10, &size);
	assert(value != NULL && size == 2 && le16(value) == 7);
	value = k60_qmi_tlv(&message, 0x11, &size);
	assert(value != NULL && size == 2 && le16(value) == 1);
	value = k60_qmi_tlv(&message, 0x12, &size);
	assert(value != NULL && size >= 5 && value[0] == 7); /* one-byte entry count */
	printf("servloc ok: QMI response with seven protection domains\n");
}

static void check_dms_revision(void)
{
	uint8_t answer[256];
	const char revision[] = "MPSS.DE.2.0.c1-CN-Jan 13 2026-02:08:51";
	char parsed[128];
	uint32_t at = K60_QMI_HEADER;

	memset(answer, 0, sizeof(answer));
	answer[0] = K60_QMI_RESPONSE;
	put16(answer + 1, 0x3456);
	put16(answer + 3, K60_QMI_DMS_GET_REVISION);
	answer[at++] = 0x02;                              /* result TLV */
	put16(answer + at, 4); at += 2;
	put32(answer + at, 0); at += 4;
	answer[at++] = 0x01;                              /* revision string TLV */
	put16(answer + at, (uint16_t)(sizeof(revision) - 1)); at += 2;
	memcpy(answer + at, revision, sizeof(revision) - 1); at += sizeof(revision) - 1;
	put16(answer + 5, (uint16_t)(at - K60_QMI_HEADER));
	assert(k60_qmi_dms_revision(answer, at, 0x3456, parsed, sizeof(parsed)) ==
	    (int)(sizeof(revision) - 1));
	assert(strcmp(parsed, revision) == 0);
	assert(k60_qmi_dms_revision(answer, at, 0x9999, parsed, sizeof(parsed)) < 0);
	printf("dms ok: revision TLV 1 parsed for matching transaction\n");
}

static void check_parse_and_verdict(void)
{
	uint8_t packet[64];
	K60QrtrState state;
	K60QrtrHeader header;
	const uint8_t *payload = NULL;

	memset(&state, 0, sizeof(state));
	assert(k60_qrtr_verdict(&state) == 0);
	/* EFS (21) from node 0 is one of the five services the criterion names. */
	size_t n = server_packet(packet, 21, 0, 0, 0x1000);
	assert(k60_qrtr_parse(packet, n, &header, &payload) == K60QrtrOk);
	assert(header.from_node == 0 && header.size == 20 && payload == packet + 32);
	assert(k60_qrtr_note(&state, packet, n) == K60QrtrOk);
	assert(state.services == 1 && state.from_node0 == 1 && state.wanted == 1);
	assert(state.table[0].service == 21 && state.table[0].port == 0x1000);
	assert(k60_qrtr_verdict(&state) == 1);
	printf("verdict ok: EFS 21 from node 0 counts\n");
}

static void check_services_and_array(void)
{
	uint8_t packet[64];
	K60QrtrState state;
	const uint32_t want[5] = {21, 1, 11, 3, 16};
	const uint32_t not_want[4] = {24, 4097, 23, 36};

	memset(&state, 0, sizeof(state));
	for (unsigned i = 0; i < 5; ++i) {
		assert(k60_qrtr_wanted(want[i]) == 1);
		k60_qrtr_note(&state, packet, server_packet(packet, want[i], i, 0, 0x1000 + i));
	}
	for (unsigned i = 0; i < 4; ++i) {
		assert(k60_qrtr_wanted(not_want[i]) == 0);
		k60_qrtr_note(&state, packet, server_packet(packet, not_want[i], 0, 0, 0x2000 + i));
	}
	assert(state.services == 9 && state.from_node0 == 9 && state.wanted == 5);
	assert(state.table[0].service == 21 && state.table[4].service == 16 && state.table[8].service == 36);
	printf("services ok: 5 wanted, 4 other, table keeps arrival order\n");
}

static void check_malformed(void)
{
	uint8_t packet[64];
	K60QrtrState state;
	K60QrtrHeader header;
	const uint8_t *payload = NULL;

	memset(packet, 0, sizeof(packet));
	memset(&state, 0, sizeof(state));
	assert(k60_qrtr_parse(packet, 31, &header, &payload) == K60QrtrShort);
	assert(k60_qrtr_note(&state, packet, 31) == K60QrtrShort && state.malformed == 1);
	/* A control message whose command disagrees with its type is not a reply. */
	size_t n = server_packet(packet, 21, 0, 0, 0x1000);
	packet[32] = 5; /* command DEL_SERVER while the type stays NEW_SERVER */
	assert(k60_qrtr_note(&state, packet, n) == K60QrtrBadArg && state.malformed == 2);
	assert(state.services == 0 && k60_qrtr_verdict(&state) == 0);
	/* A NEW_SERVER with a 16 byte payload is not a 20 byte reply. */
	n = server_packet(packet, 21, 0, 0, 0x1000);
	packet[20] = 16;
	assert(k60_qrtr_note(&state, packet, n) == K60QrtrShort && state.malformed == 3);
	printf("malformed ok: short header, wrong command, wrong size\n");
}

static void check_node_filter(void)
{
	uint8_t packet[64];
	K60QrtrState state;

	memset(&state, 0, sizeof(state));
	size_t n = server_packet(packet, 21, 0, 0, 0x1000);
	/* Same reply, but from another node: counted, never a verdict. */
	packet[8] = 3;
	assert(k60_qrtr_note(&state, packet, n) == K60QrtrOk);
	assert(state.services == 1 && state.from_node0 == 0 && state.wanted == 1);
	assert(k60_qrtr_verdict(&state) == 0);
	printf("node ok: a reply from node 3 does not satisfy the criterion\n");
}

static void check_dms_discovery(void)
{
	uint8_t packet[64];
	K60QrtrState state;

	memset(&state, 0, sizeof(state));
	assert(k60_qrtr_note(&state, packet, server_packet(packet, 2, 0, 0, 96)) == K60QrtrOk);
	assert(state.dms_found == 1 && state.dms_node == 0 && state.dms_port == 96);

	/* DEL_SERVER for the same endpoint clears it without changing the count. */
	put32(packet + 4, K60QrtrDelServer);
	put32(packet + 32, K60QrtrDelServer);
	assert(k60_qrtr_note(&state, packet, 52) == K60QrtrOk);
	assert(state.dms_found == 0 && state.dms_node == 0 && state.dms_port == 0);
	assert(state.services == 1);
	printf("dms discovery ok: service 2 found and DEL_SERVER clears it\n");
}

static void check_qmi_bounds(void)
{
	uint8_t packet[32];
	K60QmiMessage message;
	uint32_t size = 0;

	memset(packet, 0, sizeof(packet));
	assert(k60_qmi_parse(NULL, 0, &message) < 0);
	assert(k60_qmi_parse(packet, K60_QMI_HEADER - 1, &message) < 0);

	packet[0] = K60_QMI_REQUEST;
	put16(packet + 5, 26);
	assert(k60_qmi_parse(packet, sizeof(packet), &message) < 0);

	put16(packet + 5, 9);
	packet[7] = 0x01;
	put16(packet + 8, 8);
	assert(k60_qmi_parse(packet, sizeof(packet), &message) == 0);
	assert(k60_qmi_tlv(&message, 0x01, &size) == NULL);
	printf("qmi bounds ok: short header, long TLV region, overrun TLV rejected\n");
}

static void check_dms_errors(void)
{
	uint8_t answer[64];
	char parsed[16], small[8];
	uint32_t at = K60_QMI_HEADER;

	/* result TLV 2 with a non-zero QMI error. */
	memset(answer, 0, sizeof(answer));
	answer[0] = K60_QMI_RESPONSE;
	put16(answer + 1, 0x4567);
	put16(answer + 3, K60_QMI_DMS_GET_REVISION);
	answer[at++] = 0x02;
	put16(answer + at, 4); at += 2;
	put16(answer + at, 1); at += 4;
	put16(answer + 5, (uint16_t)(at - K60_QMI_HEADER));
	assert(k60_qmi_dms_revision(answer, at, 0x4567, parsed, sizeof(parsed)) == -2);

	/* Revision longer than the caller buffer is rejected, never truncated. */
	memset(answer, 0, sizeof(answer));
	at = K60_QMI_HEADER;
	answer[0] = K60_QMI_RESPONSE;
	put16(answer + 1, 0x4567);
	put16(answer + 3, K60_QMI_DMS_GET_REVISION);
	answer[at++] = 0x02;
	put16(answer + at, 4); at += 2;
	put32(answer + at, 0); at += 4;
	answer[at++] = 0x01;
	put16(answer + at, 10); at += 2;
	memcpy(answer + at, "0123456789", 10); at += 10;
	put16(answer + 5, (uint16_t)(at - K60_QMI_HEADER));
	assert(k60_qmi_dms_revision(answer, at, 0x4567, small, sizeof(small)) == -3);

	/* A control byte in the revision string is rejected. */
	answer[K60_QMI_HEADER + 7 + 7] = 0x1f;
	assert(k60_qmi_dms_revision(answer, at, 0x4567, parsed, sizeof(parsed)) == -4);
	printf("dms errors ok: QMI error, oversized and non-printable revision rejected\n");
}

int main(void)
{
	check_lookup();
	check_hello();
	check_new_server();
	check_data_and_qmi();
	check_servloc();
	check_dms_revision();
	check_parse_and_verdict();
	check_services_and_array();
	check_malformed();
	check_node_filter();
	check_dms_discovery();
	check_qmi_bounds();
	check_dms_errors();
	printf("TESTS OK 13 groups (lookup, hello, new_server, data, servloc, dms, verdict, services, malformed, node, discovery, qmi bounds, dms errors)\n");
	return 0;
}
