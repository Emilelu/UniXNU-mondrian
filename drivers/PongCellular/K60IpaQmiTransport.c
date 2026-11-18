/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* See K60IpaQmiTransport.h. The server marks INIT_COMPLETE as indicated when
 * it builds the frame, so the transport keeps that frame queued until the
 * link accepts it; readiness therefore reports delivery, not composition. */

#include <string.h>

#include "K60IpaQmiTransport.h"

static int
send_pending(K60IpaQmiTransport *transport)
{
	int rc;

	if (transport->pending_bytes == 0) {
		return K60IpaQmiTransportOk;
	}
	if (transport->send == NULL) {
		return K60IpaQmiTransportBadArgument;
	}
	rc = transport->send(transport->context, transport->tx,
	    transport->pending_bytes);
	if (rc < 0) {
		transport->last_error = rc;
		transport->send_errors++;
		return K60IpaQmiTransportSendFailed;
	}
	transport->frames_sent++;
	if (transport->pending_complete != 0) {
		transport->complete_sent = 1;
	}
	transport->pending_bytes = 0;
	transport->pending_complete = 0;
	return K60IpaQmiTransportOk;
}

void
k60_ipa_qmi_transport_reset(K60IpaQmiTransport *transport,
    uint32_t restricted_base, K60IpaQmiTransportSend send, void *context)
{
	if (transport == NULL) {
		return;
	}
	memset(transport, 0, sizeof(*transport));
	transport->send = send;
	transport->context = context;
	k60_ipa_qmi_server_reset(&transport->server, restricted_base);
}

int
k60_ipa_qmi_transport_start(K60IpaQmiTransport *transport)
{
	size_t bytes;
	int rc;

	if (transport == NULL || transport->send == NULL) {
		return K60IpaQmiTransportBadArgument;
	}
	rc = send_pending(transport);
	if (rc != K60IpaQmiTransportOk) {
		return rc;
	}
	if (transport->complete_sent != 0) {
		return K60IpaQmiTransportIgnored;
	}
	if (transport->server.state != K60IpaQmiServerIdle &&
	    transport->server.state != K60IpaQmiServerInitSent) {
		return K60IpaQmiTransportIgnored;
	}
	bytes = k60_ipa_qmi_server_init_driver(&transport->server,
	    transport->tx, sizeof(transport->tx));
	if (bytes == 0) {
		return K60IpaQmiTransportExhausted;
	}
	transport->pending_bytes = bytes;
	transport->pending_complete = 0;
	return send_pending(transport);
}

int
k60_ipa_qmi_transport_receive(K60IpaQmiTransport *transport,
    const uint8_t *frame, size_t bytes)
{
	size_t reply = 0;
	int rc, source, sent = 0;

	if (transport == NULL || transport->send == NULL || frame == NULL) {
		return K60IpaQmiTransportBadArgument;
	}
	rc = send_pending(transport);
	if (rc != K60IpaQmiTransportOk) {
		return rc;
	}
	transport->receives++;
	source = k60_ipa_qmi_server_receive(&transport->server, frame, bytes,
	    transport->tx, sizeof(transport->tx), &reply);
	if (source < 0) {
		return source;
	}
	if (reply != 0) {
		transport->pending_bytes = reply;
		transport->pending_complete = 0;
		rc = send_pending(transport);
		if (rc != K60IpaQmiTransportOk) {
			return rc;
		}
		sent++;
	}
	if (transport->complete_sent == 0) {
		bytes = k60_ipa_qmi_server_init_complete(&transport->server,
		    transport->tx, sizeof(transport->tx));
		if (bytes != 0) {
			transport->pending_bytes = bytes;
			transport->pending_complete = 1;
			rc = send_pending(transport);
			if (rc != K60IpaQmiTransportOk) {
				return rc;
			}
			sent++;
		}
	}
	return sent;
}

int
k60_ipa_qmi_transport_flush(K60IpaQmiTransport *transport)
{
	if (transport == NULL || transport->send == NULL) {
		return K60IpaQmiTransportBadArgument;
	}
	return send_pending(transport);
}

int
k60_ipa_qmi_transport_ready(const K60IpaQmiTransport *transport)
{
	if (transport == NULL) {
		return 0;
	}
	return transport->complete_sent != 0;
}
