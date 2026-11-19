/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* QRTR wire format plus the small QMI surface the modem bring-up needs: the
 * service locator answer and DMS GetRevision. No locking, no IO, no kernel
 * headers: the same file is compiled into the kernel and into the host test
 * (scripts/tests/test-k60-modem-qrtr.c), so the bytes a boot would put on the
 * wire are the bytes the test proved. */
#include "K60ModemQrtr.h"

static void put16(uint8_t *at, uint16_t value)
{
	at[0] = (uint8_t)(value & 0xffu);
	at[1] = (uint8_t)((value >> 8) & 0xffu);
}

static uint16_t get16(const uint8_t *at)
{
	return (uint16_t)((uint16_t)at[0] | (uint16_t)at[1] << 8);
}

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

static void put_header(uint8_t *out, uint32_t type, uint32_t from_node, uint32_t from_port, uint32_t to_node, uint32_t to_port, uint32_t payload)
{
	put32(out + 0, K60_QRTR_VERSION);
	put32(out + 4, type);
	put32(out + 8, from_node);
	put32(out + 12, from_port);
	put32(out + 16, 0);           /* confirm: no reply is requested */
	put32(out + 20, payload);
	put32(out + 24, to_node);
	put32(out + 28, to_port);
}

uint32_t
k60_qrtr_build_hello(uint8_t *out, size_t cap)
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
	put_header(out, K60QrtrHello, K60_QRTR_AP_NODE, K60_QRTR_CONTROL_PORT,
	    K60_QRTR_BROADCAST_NODE, K60_QRTR_CONTROL_PORT, K60_QRTR_CONTROL_BYTES);
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
/* A lookup with service 0 asks for every name; a non-zero service asks for one.
 * k36's unicast-to-node-0 lookup was never answered, so the probe now sends
 * both forms to the broadcast node. */
uint32_t
k60_qrtr_build_lookup_service(uint8_t *out, size_t cap, uint32_t to_node,
    uint32_t service, uint32_t instance)
{
	if (out == NULL || cap < K60_QRTR_LOOKUP_BYTES) {
		return 0;
	}
	put_header(out, K60QrtrNewLookup, K60_QRTR_AP_NODE, K60_QRTR_CONTROL_PORT,
	    to_node, K60_QRTR_CONTROL_PORT, K60_QRTR_CONTROL_BYTES);
	put32(out + K60_QRTR_HEADER_BYTES + 0, K60QrtrNewLookup);
	put32(out + K60_QRTR_HEADER_BYTES + 4, service);
	put32(out + K60_QRTR_HEADER_BYTES + 8, instance);
	put32(out + K60_QRTR_HEADER_BYTES + 12, 0);
	put32(out + K60_QRTR_HEADER_BYTES + 16, 0);
	return K60_QRTR_LOOKUP_BYTES;
}

uint32_t
k60_qrtr_build_lookup(uint8_t *out, size_t cap, uint32_t to_node)
{
	return k60_qrtr_build_lookup_service(out, cap, to_node, 0, 0);
}

/* NEW_SERVER: the AP's own service 64, instance 0x101, locator port 0x100.
 * The modem asks that endpoint for the protection-domain table. */
uint32_t
k60_qrtr_build_new_server(uint8_t *out, size_t cap, uint32_t service,
    uint32_t instance, uint32_t to_node, uint32_t port)
{
	if (out == NULL || cap < K60_QRTR_LOOKUP_BYTES) {
		return 0;
	}
	put_header(out, K60QrtrNewServer, K60_QRTR_AP_NODE, K60_QRTR_CONTROL_PORT,
	    to_node, K60_QRTR_CONTROL_PORT, K60_QRTR_CONTROL_BYTES);
	put32(out + K60_QRTR_HEADER_BYTES + 0, K60QrtrNewServer);
	put32(out + K60_QRTR_HEADER_BYTES + 4, service);
	put32(out + K60_QRTR_HEADER_BYTES + 8, instance);
	put32(out + K60_QRTR_HEADER_BYTES + 12, K60_QRTR_AP_NODE);
	put32(out + K60_QRTR_HEADER_BYTES + 16, port);
	return K60_QRTR_LOOKUP_BYTES;
}

uint32_t
k60_qrtr_build_data(uint8_t *out, size_t cap, uint32_t from_port,
    uint32_t to_node, uint32_t to_port, const uint8_t *payload, size_t length)
{
	const size_t padded = (length + 3u) & ~(size_t)3u;

	if (out == NULL || (payload == NULL && length != 0) ||
	    cap < K60_QRTR_HEADER_BYTES + padded || length > K60_QRTR_MAX_PACKET) {
		return 0;
	}
	put_header(out, K60QrtrData, K60_QRTR_AP_NODE, from_port, to_node, to_port,
	    (uint32_t)length);
	for (size_t i = 0; i < length; ++i) {
		out[K60_QRTR_HEADER_BYTES + i] = payload[i];
	}
	for (size_t i = length; i < padded; ++i) {
		out[K60_QRTR_HEADER_BYTES + i] = 0;
	}
	return (uint32_t)(K60_QRTR_HEADER_BYTES + padded);
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

/* ---- QMI ---- */
int
k60_qmi_parse(const uint8_t *data, uint32_t length, K60QmiMessage *message)
{
	if (data == NULL || message == NULL || length < K60_QMI_HEADER) {
		return -1;
	}
	message->type = data[0];
	message->transaction = get16(data + 1);
	message->message = get16(data + 3);
	message->length = get16(data + 5);
	if (message->length > length - K60_QMI_HEADER) {
		return -1;
	}
	message->tlvs = data + K60_QMI_HEADER;
	return 0;
}

const uint8_t *
k60_qmi_tlv(const K60QmiMessage *message, uint8_t type, uint32_t *size)
{
	uint32_t at = 0;

	if (message == NULL || size == NULL) {
		return NULL;
	}
	while (at + 3u <= message->length) {
		const uint32_t n = get16(message->tlvs + at + 1);

		if (n > message->length - at - 3u) {
			return NULL;
		}
		if (message->tlvs[at] == type) {
			*size = n;
			return message->tlvs + at + 3u;
		}
		at += 3u + n;
	}
	return NULL;
}

uint32_t
k60_qmi_build_dms_revision(uint8_t *out, size_t cap, uint16_t transaction)
{
	if (out == NULL || cap < K60_QMI_HEADER) {
		return 0;
	}
	out[0] = K60_QMI_REQUEST;
	put16(out + 1, transaction);
	put16(out + 3, K60_QMI_DMS_GET_REVISION);
	put16(out + 5, 0);
	return K60_QMI_HEADER;
}

int
k60_qmi_dms_revision(const uint8_t *data, uint32_t length, uint16_t transaction,
    char *out, size_t cap)
{
	K60QmiMessage message;
	const uint8_t *result, *revision;
	uint32_t result_size = 0, revision_size = 0;

	if (k60_qmi_parse(data, length, &message) != 0 ||
	    message.type != K60_QMI_RESPONSE ||
	    message.message != K60_QMI_DMS_GET_REVISION ||
	    message.transaction != transaction || out == NULL || cap == 0) {
		return -1;
	}
	result = k60_qmi_tlv(&message, 0x02, &result_size);
	if (result == NULL || result_size != 4 || get16(result) != 0) {
		return -2;
	}
	revision = k60_qmi_tlv(&message, 0x01, &revision_size);
	if (revision == NULL || revision_size == 0 || revision_size >= cap) {
		return -3;
	}
	for (uint32_t i = 0; i < revision_size; ++i) {
		if (revision[i] < 0x20 || revision[i] > 0x7e) {
			return -4;
		}
		out[i] = (char)revision[i];
	}
	out[revision_size] = '\0';
	return (int)revision_size;
}

/* ---- the service locator ---- */
#define K60_NAME_MAX 64u
#define K60_LIST_MAX 32u

static int
same_name(const char *a, const uint8_t *b, uint32_t n)
{
	uint32_t i = 0;

	for (; i < n && a[i]; ++i) {
		if ((uint8_t)a[i] != b[i]) {
			return 0;
		}
	}
	return i == n && !a[i];
}

static int
provides(const K60PdDomain *domain, const uint8_t *name, uint32_t n)
{
	if (same_name("tms/servreg", name, n)) {
		return 1;
	}
	for (unsigned i = 0; domain->services && domain->services[i]; ++i) {
		if (same_name(domain->services[i], name, n)) {
			return 1;
		}
	}
	return 0;
}

static const char *const k60_pd_audio_services[] = { "avs/audio", NULL };
static const char *const k60_pd_gps_services[] = { "gps/gps_service", NULL };
static const K60PdDomain k60_pd_domains[] = {
	{ "msm/adsp/root_pd", 74, NULL },
	{ "msm/adsp/audio_pd", 74, k60_pd_audio_services },
	{ "msm/adsp/charger_pd", 74, NULL },
	{ "msm/cdsp/root_pd", 76, NULL },
	{ "msm/modem/root_pd", 180, k60_pd_gps_services },
	{ "msm/slpi/root_pd", 90, NULL },
	{ "msm/slpi/sensor_pd", 90, NULL },
};

uint32_t
k60_qrtr_servloc_answer(const uint8_t *request, uint32_t length,
    uint8_t *out, uint32_t capacity)
{
	K60QmiMessage message;
	uint32_t name_size = 0, offset_size = 0, total = 0, listed = 0;
	const uint8_t *name, *skip;
	const uint32_t count = (uint32_t)(sizeof(k60_pd_domains) / sizeof(k60_pd_domains[0]));
	uint8_t *p, *list, *entry;

	if (out == NULL || k60_qmi_parse(request, length, &message) != 0 ||
	    message.type != K60_QMI_REQUEST ||
	    message.message != 0x21u) { /* SERVLOC GET_DOMAIN_LIST */
		return 0;
	}
	name = k60_qmi_tlv(&message, 0x01, &name_size);
	skip = k60_qmi_tlv(&message, 0x10, &offset_size);
	if (name == NULL || name_size > K60_NAME_MAX ||
	    (skip != NULL && offset_size != 4)) {
		return 0;
	}
	while (name_size && !name[name_size - 1]) {
		--name_size;
	}
	const uint32_t first = skip ? get32(skip) : 0;

	if (capacity < K60_QMI_HEADER + 7u + 5u + 5u + 4u) {
		return 0;
	}
	p = out + K60_QMI_HEADER;
	p[0] = 0x02;
	put16(p + 1, 4);
	put32(p + 3, 0);
	p += 7;
	list = p + 5 + 5;
	entry = list + 4;
	for (uint32_t i = 0; i < count; ++i) {
		uint32_t n = 0;

		if (!provides(&k60_pd_domains[i], name, name_size)) {
			continue;
		}
		const uint32_t index = total++;
		if (index < first || listed == K60_LIST_MAX) {
			continue;
		}
		while (k60_pd_domains[i].domain[n] && n < K60_NAME_MAX) {
			++n;
		}
		if ((uint32_t)(entry - out) + 1u + n + 9u > capacity) {
			return 0;
		}
		entry[0] = (uint8_t)n;
		for (uint32_t b = 0; b < n; ++b) {
			entry[1 + b] = (uint8_t)k60_pd_domains[i].domain[b];
		}
		entry += 1 + n;
		put32(entry, k60_pd_domains[i].instance);
		entry[4] = 0;
		put32(entry + 5, 0);
		entry += 9;
		++listed;
	}
	p[0] = 0x10;
	put16(p + 1, 2);
	put16(p + 3, (uint16_t)total);
	p += 5;
	p[0] = 0x11;
	put16(p + 1, 2);
	put16(p + 3, 1);
	p += 5;
	if (listed) {
		p[0] = 0x12;
		put16(p + 1, (uint16_t)(entry - p - 3));
		p[3] = (uint8_t)listed;
		p = entry;
	}
	out[0] = K60_QMI_RESPONSE;
	put16(out + 1, message.transaction);
	put16(out + 3, message.message);
	put16(out + 5, (uint16_t)(p - out - K60_QMI_HEADER));
	return (uint32_t)(p - out);
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
		state->remote_node = header.from_node;
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
		if (control.words[0] == K60_QRTR_DMS_SERVICE &&
		    control.words[2] == state->dms_node &&
		    control.words[3] == state->dms_port) {
			state->dms_found = 0;
			state->dms_node = 0;
			state->dms_port = 0;
		}
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
	if (control.words[0] == K60_QRTR_DMS_SERVICE) {
		state->dms_node = control.words[2];
		state->dms_port = control.words[3];
		state->dms_found = 1;
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
