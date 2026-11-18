/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* QRTR framing for the IPA service 0x31 handshake. This is the layer between
 * K60IpaQmiTransport (which sequences INIT_DRIVER and answers modem requests)
 * and the QRTR link: it announces the AP server 49/0x101 on port 0x122, learns
 * the modem endpoint 49/0x201 from the name service, wraps every QMI frame in
 * a DATA datagram and unwraps the ones addressed to our registered port.
 *
 * Pong does the same split: references/pong-baseband/PongModemWan.h:388
 * registers service 49 instance 0x101 on IpaHostPort 0x122, :62 accepts
 * incoming traffic only for service 49 instance 0x201, :410 sends INIT_DRIVER
 * as a client from IpaClientPort 0x123 and :400/:417 answer and publish from
 * IpaHostPort. The source port is therefore chosen by the QMI SDU type: a
 * request (0) is a client frame from 0x123, a response (2) or indication (4)
 * belongs to the registered server on 0x122.
 *
 * Pure QRTR and QMI: no GLINK, no SMEM, no allocation. K60ModemLink hands each
 * datagram to k60_ipa_qrtr_receive() and the send callback writes one datagram
 * to the link. */

#ifndef K60_IPA_QRTR_H
#define K60_IPA_QRTR_H

#include <stddef.h>
#include <stdint.h>

#include "K60IpaQmi.h"
#include "K60IpaQmiTransport.h"
#include "K60ModemQrtr.h"

#define K60_IPA_QRTR_PACKET_BYTES \
	(K60_QRTR_HEADER_BYTES + K60_IPA_QMI_TRANSPORT_FRAME_BYTES + 4u)

/* Returns 0 when the datagram was handed to the link, negative otherwise. */
typedef int (*K60IpaQrtrSend)(void *context, const uint8_t *packet,
    size_t bytes);

typedef struct {
	K60IpaQmiTransport transport;
	K60IpaQrtrSend send;
	void *context;
	uint32_t restricted_base;
	uint32_t remote_node;
	uint32_t remote_port;
	uint32_t datagrams;
	uint32_t announces;
	uint32_t lookups;
	uint32_t data_in;
	uint32_t ignored;
	uint32_t malformed;
	uint32_t send_errors;
	uint8_t remote_known;
	uint8_t started;
	int last_error;
} K60IpaQrtr;

enum {
	K60IpaQrtrOk = 0,
	K60IpaQrtrIgnored = 1,
	K60IpaQrtrBadArgument = -1,
	K60IpaQrtrMalformed = -2,
	K60IpaQrtrSendFailed = -3,
	K60IpaQrtrTransportError = -4,
};

void k60_ipa_qrtr_reset(K60IpaQrtr *session, uint32_t restricted_base,
    K60IpaQrtrSend send, void *context);

/* NEW_SERVER for the AP's service 49/0x101 on port 0x122. */
int k60_ipa_qrtr_announce(K60IpaQrtr *session, uint32_t to_node);
/* The generic NEW_LOOKUP the link uses to collect NEW_SERVER replies. */
int k60_ipa_qrtr_lookup(K60IpaQrtr *session, uint32_t to_node);
/* One received QRTR datagram. A NEW_SERVER for 49/0x201 records the endpoint
 * and starts the INIT_DRIVER exchange; DATA to 0x122 is fed to the transport.
 * Returns Ok, Ignored, or a negative error. */
int k60_ipa_qrtr_receive(K60IpaQrtr *session, const uint8_t *packet,
    size_t bytes);
/* Retry a QMI frame left queued by a failed link write. */
int k60_ipa_qrtr_flush(K60IpaQrtr *session);
int k60_ipa_qrtr_ready(const K60IpaQrtr *session);

#endif /* K60_IPA_QRTR_H */
