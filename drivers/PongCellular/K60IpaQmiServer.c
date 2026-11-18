/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* See K60IpaQmiServer.h. The sequencing, the per-message verdicts and the
 * result/error convention follow Pong's same-board implementation
 * (references/pong-baseband/PongModemWan.h:138-181, :382-424):
 *   - INIT_DRIVER is sent from the client port, at most three attempts;
 *   - 0x20 answers success and subscribes the sender;
 *   - 0x35 reads the one-byte driver status and marks the uC ready;
 *   - 0x27 stores the configuration body and the TLV field mask;
 *   - 0x24 validates and acknowledges the filter notification;
 *   - 0x23 returns the accepted rule ids;
 *   - an unknown message answers result 1 / error 94.
 */

#include <string.h>

#include "K60IpaQmiServer.h"

#define K60_IPA_QMI_INIT_DRIVER 0x21u
#define K60_IPA_QMI_INIT_COMPLETE 0x22u
#define K60_IPA_QMI_INDICATION_REGISTER 0x20u
#define K60_IPA_QMI_DRIVER_INIT_COMPLETE 0x35u
#define K60_IPA_QMI_CONFIGURATION 0x27u
#define K60_IPA_QMI_FILTER_INSTALLED 0x24u
#define K60_IPA_QMI_RULES 0x23u

static uint16_t
get16(const uint8_t *p)
{
	return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8));
}

static uint32_t
get32(const uint8_t *p)
{
	return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
	    ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

/* A QMI SDU is a 7-byte header (type, transaction, message, length) plus
 * exactly the declared TLVs. Anything else is dropped before it can reach a
 * handler. */
static int
sdu_ok(const uint8_t *frame, size_t bytes)
{
	if (frame[0] != 0 && frame[0] != 2) {
		return 0;
	}
	if (bytes < 7 || 7u + get16(frame + 5) != bytes) {
		return 0;
	}
	return 1;
}

/* Store the configuration body (bounded) and record which 0x10..0x2f TLVs
 * arrived, the way Pong's configuration() keeps configBytes/configFields. */
static int
config_apply(K60IpaQmiServer *server, const uint8_t *frame, size_t bytes)
{
	const size_t body = bytes - 7u;
	size_t at = 7;

	if (body > sizeof(server->config)) {
		return -1;
	}
	if (body != 0) {
		memcpy(server->config, frame + 7, body);
	}
	server->config_bytes = (uint16_t)body;
	memset(server->config_fields, 0, sizeof(server->config_fields));
	while (at + 3u <= bytes) {
		const size_t length = get16(frame + at + 1);

		if (at + 3u + length > bytes) {
			return -1;
		}
		if (frame[at] >= 0x10 && frame[at] < 0x30) {
			const unsigned bit = frame[at] - 0x10;

			server->config_fields[bit >> 3] |=
			    (uint8_t)(1u << (bit & 7));
		}
		at += 3u + length;
	}
	return at == bytes ? 0 : -1;
}

/* The filter notification carries pipe (TLV 1, u32), status (TLV 2, u16) and
 * a list of 64-bit rule indices (TLV 3, count + 8*count), exactly the shape
 * Pong validates at PongModemWan.h:123-136. */
static int
filter_apply(K60IpaQmiServer *server, const uint8_t *frame, size_t bytes)
{
	size_t at = 7;
	int have_pipe = 0, have_status = 0, have_ids = 0;
	uint32_t pipe = 0;
	uint16_t status = 0;

	while (at + 3u <= bytes) {
		const size_t length = get16(frame + at + 1);

		if (at + 3u + length > bytes) {
			return -1;
		}
		switch (frame[at]) {
		case 1:
			if (length != 4) {
				return -1;
			}
			pipe = get32(frame + at + 3);
			have_pipe = 1;
			break;
		case 2:
			if (length != 2) {
				return -1;
			}
			status = get16(frame + at + 3);
			have_status = 1;
			break;
		case 3:
			if (length < 1 || frame[at + 3] > 64 ||
			    length != 1u + 8u * frame[at + 3]) {
				return -1;
			}
			have_ids = 1;
			break;
		default:
			break;
		}
		at += 3u + length;
	}
	if (at != bytes || !have_pipe || !have_status || !have_ids) {
		return -1;
	}
	if (pipe >= 32 || status > 1) {
		return -1;
	}
	server->last_filter_pipe = (uint8_t)pipe;
	server->last_filter_status = (uint8_t)status;
	server->notifications++;
	return 0;
}

void
k60_ipa_qmi_server_reset(K60IpaQmiServer *server, uint32_t restricted_base)
{
	if (server == NULL) {
		return;
	}
	memset(server, 0, sizeof(*server));
	server->restricted_base = restricted_base;
	server->state = K60IpaQmiServerIdle;
}

size_t
k60_ipa_qmi_server_init_driver(K60IpaQmiServer *server, uint8_t *out,
    size_t capacity)
{
	uint16_t transaction;
	size_t bytes;

	if (server == NULL || out == NULL) {
		return 0;
	}
	if (server->state != K60IpaQmiServerIdle &&
	    server->state != K60IpaQmiServerInitSent) {
		return 0;
	}
	if (server->attempts >= 3) {
		return 0;
	}
	transaction = (uint16_t)(server->transaction + 1u);
	if (transaction == 0) {
		transaction = 1;
	}
	bytes = k60_ipa_qmi_build_init_driver(out, capacity, transaction,
	    server->restricted_base);
	if (bytes == 0) {
		return 0;
	}
	server->transaction = transaction;
	server->attempts++;
	server->state = K60IpaQmiServerInitSent;
	return bytes;
}

int
k60_ipa_qmi_server_receive(K60IpaQmiServer *server, const uint8_t *frame,
    size_t bytes, uint8_t *out, size_t capacity, size_t *out_bytes)
{
	uint16_t transaction, message, result, error;
	size_t reply;

	if (server == NULL || frame == NULL || out == NULL ||
	    out_bytes == NULL) {
		return K60IpaQmiServerBadArgument;
	}
	*out_bytes = 0;
	if (!sdu_ok(frame, bytes)) {
		return K60IpaQmiServerMalformed;
	}
	transaction = get16(frame + 1);
	message = get16(frame + 3);
	if (frame[0] == 2) {
		if (server->state != K60IpaQmiServerInitSent ||
		    message != K60_IPA_QMI_INIT_DRIVER ||
		    transaction != server->transaction) {
			return K60IpaQmiServerIgnored;
		}
		if (k60_ipa_qmi_parse_response(frame, bytes, transaction,
		    K60_IPA_QMI_INIT_DRIVER, &result, &error) < 0) {
			return K60IpaQmiServerMalformed;
		}
		if (result != 0) {
			server->driver_ready = 0;
			server->state = K60IpaQmiServerFailed;
			server->errors++;
			return K60IpaQmiServerInitRejected;
		}
		server->driver_ready = 1;
		server->state = K60IpaQmiServerDriverReady;
		return K60IpaQmiServerOk;
	}
	if (frame[0] != 0) {
		return K60IpaQmiServerIgnored;
	}

	server->requests++;
	switch (message) {
	case K60_IPA_QMI_INDICATION_REGISTER:
		reply = k60_ipa_qmi_build_response(out, capacity, transaction,
		    message, 0, 0, NULL, 0);
		if (reply == 0) {
			return K60IpaQmiServerBadArgument;
		}
		server->subscribed = 1;
		break;
	case K60_IPA_QMI_DRIVER_INIT_COMPLETE: {
		uint8_t status = 0;

		if (k60_ipa_qmi_driver_status(frame, bytes, &status) < 0) {
			reply = k60_ipa_qmi_build_response(out, capacity,
			    transaction, message, 1, 1, NULL, 0);
			server->errors++;
		} else {
			reply = k60_ipa_qmi_build_response(out, capacity,
			    transaction, message, status != 0 ? 0 : 1,
			    status != 0 ? 0 : 1, NULL, 0);
			server->uc_ready = status != 0 ? 1 : 0;
		}
		if (reply == 0) {
			return K60IpaQmiServerBadArgument;
		}
		break;
	}
	case K60_IPA_QMI_CONFIGURATION: {
		const int rc = config_apply(server, frame, bytes);

		reply = k60_ipa_qmi_build_response(out, capacity, transaction,
		    message, rc != 0 ? 1 : 0, rc != 0 ? 1 : 0, NULL, 0);
		if (rc != 0) {
			server->errors++;
		}
		if (reply == 0) {
			return K60IpaQmiServerBadArgument;
		}
		break;
	}
	case K60_IPA_QMI_FILTER_INSTALLED: {
		const int rc = filter_apply(server, frame, bytes);

		reply = k60_ipa_qmi_build_response(out, capacity, transaction,
		    message, rc != 0 ? 1 : 0, rc != 0 ? 1 : 0, NULL, 0);
		if (rc != 0) {
			server->errors++;
		}
		if (reply == 0) {
			return K60IpaQmiServerBadArgument;
		}
		break;
	}
	case K60_IPA_QMI_RULES: {
		uint32_t ids[K60_IPA_QMI_SERVER_MAX_RULES];
		size_t count = 0;

		if (k60_ipa_qmi_rules(frame, bytes, ids,
		    K60_IPA_QMI_SERVER_MAX_RULES, &count) < 0) {
			reply = k60_ipa_qmi_build_response(out, capacity,
			    transaction, message, 1, 1, NULL, 0);
			server->errors++;
		} else {
			reply = k60_ipa_qmi_build_response(out, capacity,
			    transaction, message, 0, 0, ids, count);
			if (reply != 0) {
				server->rules = (uint16_t)count;
			}
		}
		if (reply == 0) {
			return K60IpaQmiServerBadArgument;
		}
		break;
	}
	default:
		reply = k60_ipa_qmi_build_response(out, capacity, transaction,
		    message, 1, K60_IPA_QMI_SERVER_UNHANDLED, NULL, 0);
		if (reply == 0) {
			return K60IpaQmiServerBadArgument;
		}
		server->errors++;
		*out_bytes = reply;
		return K60IpaQmiServerUnhandled;
	}
	*out_bytes = reply;
	return K60IpaQmiServerOk;
}

size_t
k60_ipa_qmi_server_init_complete(K60IpaQmiServer *server, uint8_t *out,
    size_t capacity)
{
	size_t bytes;

	if (server == NULL || out == NULL) {
		return 0;
	}
	if (server->indicated != 0 || server->driver_ready == 0 ||
	    server->uc_ready == 0 || server->subscribed == 0) {
		return 0;
	}
	bytes = k60_ipa_qmi_build_init_complete(out, capacity);
	if (bytes == 0) {
		return 0;
	}
	server->indicated = 1;
	server->state = K60IpaQmiServerComplete;
	return bytes;
}

int
k60_ipa_qmi_server_ready(const K60IpaQmiServer *server)
{
	if (server == NULL) {
		return 0;
	}
	return server->driver_ready != 0 && server->uc_ready != 0 &&
	    server->subscribed != 0 && server->indicated != 0;
}
