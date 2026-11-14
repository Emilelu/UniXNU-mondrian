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

/* A NEW_SERVER datagram exactly as the modem's name service sends it: a v1
 * header from node 0, port 0xfffffffe, and the 20 byte control payload. */
static size_t server_packet(uint8_t *out, uint32_t service, uint32_t instance, uint32_t node, uint32_t port)
{
	const uint32_t words[8] = {K60_QRTR_VERSION, K60QrtrNewServer, 0, 0xfffffff0u, 0, 20,
	    K60_QRTR_BROADCAST_NODE, K60_QRTR_CONTROL_PORT};
	const uint32_t payload[5] = {K60QrtrNewServer, service, instance, node, port};
	for (unsigned i = 0; i < 8; ++i) {
		out[i * 4 + 0] = (uint8_t)words[i];
		out[i * 4 + 1] = (uint8_t)(words[i] >> 8);
		out[i * 4 + 2] = (uint8_t)(words[i] >> 16);
		out[i * 4 + 3] = (uint8_t)(words[i] >> 24);
	}
	for (unsigned i = 0; i < 5; ++i) {
		uint8_t *at = out + 32 + i * 4;
		at[0] = (uint8_t)payload[i];
		at[1] = (uint8_t)(payload[i] >> 8);
		at[2] = (uint8_t)(payload[i] >> 16);
		at[3] = (uint8_t)(payload[i] >> 24);
	}
	return 52;
}

static void check_lookup(void)
{
	uint8_t packet[64];
	uint32_t n = k60_qrtr_build_lookup(packet, sizeof(packet), K60_QRTR_FIRST_PORT);
	assert(n == 52);
	assert(le32(packet + 0) == 1);                    /* version */
	assert(le32(packet + 4) == 10);                   /* NEW_LOOKUP */
	assert(le32(packet + 8) == 0);                    /* from_node: us */
	assert(le32(packet + 12) == 0x4000);              /* from_port */
	assert(le32(packet + 16) == 0);                   /* confirm */
	assert(le32(packet + 20) == 20);                  /* size */
	assert(le32(packet + 24) == 0xffffffffu);         /* broadcast node */
	assert(le32(packet + 28) == 0xfffffffeu);         /* control port */
	assert(le32(packet + 32) == 10);                  /* command */
	assert(le32(packet + 36) == 0 && le32(packet + 48) == 0);
	assert(k60_qrtr_build_lookup(packet, 51, 0) == 0); /* refuses a short buffer */
	assert(k60_qrtr_build_lookup(NULL, 64, 0) == 0);
	printf("lookup ok: 52 bytes, type 10, node 0xffffffff port 0xfffffffe\n");
}

static void check_hello(void)
{
	uint8_t packet[64];
	assert(k60_qrtr_build_hello(packet, sizeof(packet), 0x4000) == 52);
	assert(le32(packet + 4) == 2);
	assert(le32(packet + 32) == 2);
	assert(le32(packet + 24) == 0xfffffffeu);
	printf("hello ok: type 2 to the control port\n");
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

int main(void)
{
	check_lookup();
	check_hello();
	check_parse_and_verdict();
	check_services_and_array();
	check_malformed();
	check_node_filter();
	printf("TESTS OK 6 groups (lookup, hello, verdict, services, malformed, node)\n");
	return 0;
}
