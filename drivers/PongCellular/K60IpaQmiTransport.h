/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* The glue between the IPA service 0x31 QMI server and whatever carries the
 * frames (QRTR over GLINK in the kernel). It owns the three-attempt
 * INIT_DRIVER retry, answers every modem request, and publishes the single
 * 0x22 INIT_COMPLETE indication, so the runtime layer only has to move
 * buffers and time the retries. Pong does the same sequencing inline in
 * references/pong-baseband/PongModemWan.h:382-424. */

#ifndef K60_IPA_QMI_TRANSPORT_H
#define K60_IPA_QMI_TRANSPORT_H

#include <stddef.h>
#include <stdint.h>

#include "K60IpaQmiServer.h"

/* The largest frame the transport can emit: a rules response. */
#define K60_IPA_QMI_TRANSPORT_FRAME_BYTES K60_IPA_QMI_RULES_BYTES
#define K60_IPA_QMI_TRANSPORT_ATTEMPTS 3u

/* Returns 0 when the frame was handed to the link, a negative value when it
 * was not. A failed frame stays queued, so the caller can retry it. */
typedef int (*K60IpaQmiTransportSend)(void *context, const uint8_t *frame,
    size_t bytes);

typedef struct {
	K60IpaQmiServer server;
	K60IpaQmiTransportSend send;
	void *context;
	uint8_t tx[K60_IPA_QMI_TRANSPORT_FRAME_BYTES];
	size_t pending_bytes;
	uint16_t frames_sent;
	uint16_t send_errors;
	uint16_t receives;
	uint8_t pending_complete;
	uint8_t complete_sent;
	int last_error;
} K60IpaQmiTransport;

enum {
	K60IpaQmiTransportOk = 0,
	/* Already complete, or the handshake is past the retry window. */
	K60IpaQmiTransportIgnored = 1,
	K60IpaQmiTransportBadArgument = -1,
	K60IpaQmiTransportSendFailed = -2,
	/* All three INIT_DRIVER attempts were built without a response. */
	K60IpaQmiTransportExhausted = -3,
};

void k60_ipa_qmi_transport_reset(K60IpaQmiTransport *transport,
    uint32_t restricted_base, K60IpaQmiTransportSend send, void *context);

/* Build and send the next INIT_DRIVER attempt, or resend a frame that failed
 * earlier. Returns 0 when a frame went out, 1 when there is nothing to do and
 * K60IpaQmiTransportExhausted after three unanswered attempts. */
int k60_ipa_qmi_transport_start(K60IpaQmiTransport *transport);

/* Feed one QMI frame. Replies and the INIT_COMPLETE indication are sent
 * immediately; the return value is the number of frames sent (0, 1 or 2), or
 * a negative error. A frame whose send failed is retried by the next call. */
int k60_ipa_qmi_transport_receive(K60IpaQmiTransport *transport,
    const uint8_t *frame, size_t bytes);

/* Retry a frame left queued by a failed send. */
int k60_ipa_qmi_transport_flush(K60IpaQmiTransport *transport);

/* True only once INIT_COMPLETE actually reached the link. */
int k60_ipa_qmi_transport_ready(const K60IpaQmiTransport *transport);

#endif /* K60_IPA_QMI_TRANSPORT_H */
