/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* QRTR wire format only. No locking, no IO, no kernel headers: the same file
 * is compiled into the kernel and into the host test (scripts/tests/
 * test-k60-modem-qrtr.c), so the bytes a boot would put on the wire are the
 * bytes the test proved. */
#include "K60ModemQrtr.h"

static void put32(uint8_t *at, uint32_t value)
{
	at[0] = (uint8_t)(value & 0xffu);
	at[1] = (uint8_t)((value >> 8) & 0xffu);
	at[2] = (uint8_t)((value >> 16) & 0xffu);
	at[3] = (uint8_t)((value >> 24) & 0xffu);
}

static uint32_t get32(const uint8_t *at)
{
	return (uint32_t)at[0] | (uint32_t)at[1] << 8 | (uint32_t)at[2] << 16 | (uint32_t)at[3] << 24;
}

static void put_header(uint8_t *out, uint32_t type, uint32_t from_port, uint32_t to_node, uint32_t to_port, uint32_t payload)
{
	put32(out + 0, K60_QRTR_VERSION);
	put32(out + 4, type);
	put32(out + 8, 0);            /* from_node: 0 is this host (the APSS side) */
	put32(out + 12, from_port);
	put32(out + 16, 0);           /* confirm: no reply is requested */
	put32(out + 20, payload);
	put32(out + 24, to_node);
	put32(out + 28, to_port);
}

uint32_t
k60_qrtr_build_hello(uint8_t *out, size_t cap, uint32_t from_port)
{
	K60QrtrControl control;

	if (out == NULL || cap < K60_QRTR_LOOKUP_BYTES) {
		return 0;
	}
	control.command = K60QrtrHello;
	control.words[0] = 0;
	control.words[1] = 0;
	control.words[2] = 0;
	control.words[3] = 0;
	put_header(out, K60QrtrHello, from_port, K60_QRTR_CONTROL_PORT, K60_QRTR_CONTROL_PORT,
	    K60_QRTR_CONTROL_BYTES);
	put32(out + K60_QRTR_HEADER_BYTES + 0, control.command);
	put32(out + K60_QRTR_HEADER_BYTES + 4, control.words[0]);
	put32(out + K60_QRTR_HEADER_BYTES + 8, control.words[1]);
	put32(out + K60_QRTR_HEADER_BYTES + 12, control.words[2]);
	put32(out + K60_QRTR_HEADER_BYTES + 16, control.words[3]);
	return K60_QRTR_LOOKUP_BYTES;
}

/* NEW_LOOKUP to node 0xffffffff: "every name server, tell me what you have".
 * The modem's own name service (node 0) answers with one NEW_SERVER per
 * service; that is the reply the completion criterion is written against. */
uint32_t
k60_qrtr_build_lookup(uint8_t *out, size_t cap, uint32_t from_port)
{
	if (out == NULL || cap < K60_QRTR_LOOKUP_BYTES) {
		return 0;
	}
	put_header(out, K60QrtrNewLookup, from_port, K60_QRTR_BROADCAST_NODE, K60_QRTR_CONTROL_PORT,
	    K60_QRTR_CONTROL_BYTES);
	put32(out + K60_QRTR_HEADER_BYTES + 0, K60QrtrNewLookup);
	put32(out + K60_QRTR_HEADER_BYTES + 4, 0);
	put32(out + K60_QRTR_HEADER_BYTES + 8, 0);
	put32(out + K60_QRTR_HEADER_BYTES + 12, 0);
	put32(out + K60_QRTR_HEADER_BYTES + 16, 0);
	return K60_QRTR_LOOKUP_BYTES;
}

int
k60_qrtr_parse(const uint8_t *data, size_t length, K60QrtrHeader *header, const uint8_t **payload)
{
	if (data == NULL || header == NULL || length < K60_QRTR_HEADER_BYTES) {
		return K60QrtrShort;
	}
	header->version = get32(data + 0);
	header->type = get32(data + 4);
	header->from_node = get32(data + 8);
	header->from_port = get32(data + 12);
	header->confirm = get32(data + 16);
	header->size = get32(data + 20);
	header->to_node = get32(data + 24);
	header->to_port = get32(data + 28);
	if (header->version != K60_QRTR_VERSION) {
		return K60QrtrBadArg;
	}
	if (header->size > length - K60_QRTR_HEADER_BYTES) {
		return K60QrtrShort;
	}
	if (payload != NULL) {
		*payload = data + K60_QRTR_HEADER_BYTES;
	}
	return K60QrtrOk;
}

int
k60_qrtr_wanted(uint32_t service)
{
	switch (service) {
	case 1:  /* WDS */
	case 3:  /* NAS */
	case 11: /* UIM */
	case 16: /* PDS */
	case 21: /* EFS */
		return 1;
	default:
		return 0;
	}
}

int
k60_qrtr_note(K60QrtrState *state, const uint8_t *data, size_t length)
{
	K60QrtrHeader header;
	const uint8_t *payload = NULL;
	K60QrtrControl control;
	int rc;

	if (state == NULL || data == NULL) {
		return K60QrtrBadArg;
	}
	rc = k60_qrtr_parse(data, length, &header, &payload);
	if (rc != K60QrtrOk) {
		state->malformed++;
		return rc;
	}
	if (header.type == K60QrtrHello) {
		state->hello_acks++;
		return K60QrtrOk;
	}
	if (header.type != K60QrtrNewServer && header.type != K60QrtrDelServer) {
		return K60QrtrOk; /* BYE, RESUME_TX and DATA are not ours to judge */
	}
	if (header.size != K60_QRTR_CONTROL_BYTES) {
		state->malformed++;
		return K60QrtrShort;
	}
	control.command = get32(payload + 0);
	control.words[0] = get32(payload + 4);
	control.words[1] = get32(payload + 8);
	control.words[2] = get32(payload + 12);
	control.words[3] = get32(payload + 16);
	if (control.command != header.type) {
		state->malformed++;
		return K60QrtrBadArg;
	}
	if (header.type == K60QrtrDelServer) {
		return K60QrtrOk; /* a removal never counts against the verdict */
	}
	state->services++;
	if (header.from_node == 0) {
		state->from_node0++;
	}
	if (k60_qrtr_wanted(control.words[0])) {
		state->wanted++;
	}
	if (state->services <= K60_QRTR_MAX_SERVICES) {
		K60QrtrServer *slot = &state->table[state->services - 1];
		slot->service = control.words[0];
		slot->instance = control.words[1];
		slot->node = control.words[2];
		slot->port = control.words[3];
	}
	return K60QrtrOk;
}

int
k60_qrtr_verdict(const K60QrtrState *state)
{
	if (state == NULL) {
		return 0;
	}
	return state->from_node0 != 0 && state->wanted != 0;
}
