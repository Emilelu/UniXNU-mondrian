/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* The IPA 5.1 QMI server state machine: what the AP does between the QRTR
 * transport and the K60IpaQmi codec. It mirrors Pong's same-board
 * implementation (references/pong-baseband/PongModemWan.h:138-181 and
 * :382-424): send INIT_DRIVER from the client port with three attempts,
 * answer the modem's 0x20/0x23/0x24/0x27/0x35 requests, and publish the
 * 0x22 INIT_COMPLETE indication once the driver, the uC and the subscriber
 * are all present. Transport and QMI addressing stay with the caller. */

#ifndef K60_IPA_QMI_SERVER_H
#define K60_IPA_QMI_SERVER_H

#include <stddef.h>
#include <stdint.h>

#include "K60IpaQmi.h"

/* Pong answers an unknown request with result 1 and this error code
 * (PongModemWan.h:158, :168-176). */
#define K60_IPA_QMI_SERVER_UNHANDLED 94u
/* The one-byte DRIVER_INIT_COMPLETE status is not a QMI result TLV. */
#define K60_IPA_QMI_SERVER_MAX_RULES K60_IPA_QMI_MAX_RULES
#define K60_IPA_QMI_SERVER_CONFIG_BYTES 256u

typedef enum {
	K60IpaQmiServerIdle = 0,
	K60IpaQmiServerInitSent,
	K60IpaQmiServerDriverReady,
	K60IpaQmiServerComplete,
	K60IpaQmiServerFailed,
} K60IpaQmiServerState;

typedef enum {
	K60IpaQmiServerOk = 0,
	/* A frame that is not addressed to this handshake or already handled. */
	K60IpaQmiServerIgnored = 1,
	/* A request with no handler; a result 1 / error 94 reply was built. */
	K60IpaQmiServerUnhandled = 2,
	K60IpaQmiServerMalformed = -1,
	K60IpaQmiServerBadArgument = -2,
	/* The modem refused INIT_DRIVER; the state machine is failed. */
	K60IpaQmiServerInitRejected = -3,
} K60IpaQmiServerResult;

typedef struct {
	uint32_t restricted_base;
	uint16_t transaction;
	uint16_t attempts;
	uint8_t state;
	uint8_t subscribed;
	uint8_t driver_ready;
	uint8_t uc_ready;
	uint8_t indicated;
	uint8_t last_filter_pipe;
	uint8_t last_filter_status;
	uint8_t config_fields[4];
	uint16_t config_bytes;
	uint16_t notifications;
	uint16_t rules;
	uint16_t requests;
	uint16_t errors;
	uint8_t config[K60_IPA_QMI_SERVER_CONFIG_BYTES];
} K60IpaQmiServer;

/* Reset a server for one service 49 instance. */
void k60_ipa_qmi_server_reset(K60IpaQmiServer *server,
    uint32_t restricted_base);

/* Build the next INIT_DRIVER request. Returns 0 once three attempts are
 * spent, so the caller can time the 60 s retry the way Pong does. */
size_t k60_ipa_qmi_server_init_driver(K60IpaQmiServer *server, uint8_t *out,
    size_t capacity);

/* Feed one QRTR-delivered QMI frame. When a reply is due, out holds it and
 * *out_bytes is its length; *out_bytes stays 0 for a response to our own
 * request. */
int k60_ipa_qmi_server_receive(K60IpaQmiServer *server, const uint8_t *frame,
    size_t bytes, uint8_t *out, size_t capacity, size_t *out_bytes);

/* Build the 0x22 INIT_COMPLETE indication once driver + uC + subscriber are
 * all present; 0 until then, and only once. */
size_t k60_ipa_qmi_server_init_complete(K60IpaQmiServer *server, uint8_t *out,
    size_t capacity);

/* True once the handshake is complete and INIT_COMPLETE has been built. */
int k60_ipa_qmi_server_ready(const K60IpaQmiServer *server);

#endif /* K60_IPA_QMI_SERVER_H */
