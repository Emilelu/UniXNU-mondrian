/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* See K60IpaQrtr.h. */

#include <string.h>

#include "K60IpaQrtr.h"

static uint32_t
get32(const uint8_t *p)
{
	return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
	    ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

/* Wraps one QMI frame into a QRTR DATA datagram and writes it to the link.
 * The source port follows the SDU type, as Pong does: client requests leave
 * from 0x123, responses and indications from the registered server 0x122. */
static int
session_send_qmi(void *context, const uint8_t *frame, size_t bytes)
{
	K60IpaQrtr *session = (K60IpaQrtr *)context;
	uint8_t packet[K60_IPA_QRTR_PACKET_BYTES];
	uint32_t from_port, framed;
	int rc;

	if (session == NULL || session->send == NULL || frame == NULL ||
	    bytes == 0 || bytes > K60_IPA_QMI_TRANSPORT_FRAME_BYTES) {
		return -1;
	}
	if (session->remote_known == 0) {
		return -1;
	}
	from_port = frame[0] == K60_QMI_REQUEST ? K60_IPA_QMI_CLIENT_PORT :
	    K60_IPA_QMI_HOST_PORT;
	framed = k60_qrtr_build_data(packet, sizeof(packet), from_port,
	    session->remote_node, session->remote_port, frame, bytes);
	if (framed == 0) {
		return -1;
	}
	rc = session->send(session->context, packet, framed);
	if (rc < 0) {
		session->send_errors++;
		session->last_error = rc;
		return -1;
	}
	return 0;
}

void
k60_ipa_qrtr_reset(K60IpaQrtr *session, uint32_t restricted_base,
    K60IpaQrtrSend send, void *context)
{
	if (session == NULL) {
		return;
	}
	memset(session, 0, sizeof(*session));
	session->send = send;
	session->context = context;
	session->restricted_base = restricted_base;
	k60_ipa_qmi_transport_reset(&session->transport, restricted_base,
	    session_send_qmi, session);
}

int
k60_ipa_qrtr_announce(K60IpaQrtr *session, uint32_t to_node)
{
	uint8_t packet[K60_QRTR_LOOKUP_BYTES];
	uint32_t bytes;

	if (session == NULL || session->send == NULL) {
		return K60IpaQrtrBadArgument;
	}
	bytes = k60_qrtr_build_new_server(packet, sizeof(packet),
	    K60_IPA_QMI_SERVICE, K60_IPA_QMI_INSTANCE_AP, to_node,
	    K60_IPA_QMI_HOST_PORT);
	if (bytes == 0) {
		return K60IpaQrtrBadArgument;
	}
	if (session->send(session->context, packet, bytes) < 0) {
		session->send_errors++;
		return K60IpaQrtrSendFailed;
	}
	session->announces++;
	return K60IpaQrtrOk;
}

int
k60_ipa_qrtr_lookup(K60IpaQrtr *session, uint32_t to_node)
{
	uint8_t packet[K60_QRTR_LOOKUP_BYTES];
	uint32_t bytes;

	if (session == NULL || session->send == NULL) {
		return K60IpaQrtrBadArgument;
	}
	bytes = k60_qrtr_build_lookup(packet, sizeof(packet), to_node);
	if (bytes == 0) {
		return K60IpaQrtrBadArgument;
	}
	if (session->send(session->context, packet, bytes) < 0) {
		session->send_errors++;
		return K60IpaQrtrSendFailed;
	}
	session->lookups++;
	return K60IpaQrtrOk;
}

/* Records the modem endpoint; a changed endpoint restarts the handshake
 * because the old INIT_DRIVER exchange no longer describes the peer. */
static int
note_modem_server(K60IpaQrtr *session, uint32_t node, uint32_t port)
{
	int rc;

	if (node == 0 || node == K60_QRTR_BROADCAST_NODE || port == 0 ||
	    port == K60_QRTR_CONTROL_PORT || port == K60_QRTR_BROADCAST_NODE) {
		session->malformed++;
		return K60IpaQrtrMalformed;
	}
	if (session->remote_known != 0 &&
	    (session->remote_node != node || session->remote_port != port)) {
		k60_ipa_qmi_transport_reset(&session->transport,
		    session->restricted_base, session_send_qmi, session);
		session->started = 0;
	}
	session->remote_node = node;
	session->remote_port = port;
	session->remote_known = 1;
	if (session->started != 0) {
		return K60IpaQrtrOk;
	}
	session->started = 1;
	rc = k60_ipa_qmi_transport_start(&session->transport);
	if (rc < 0) {
		session->last_error = rc;
		if (rc == K60IpaQmiTransportExhausted) {
			return K60IpaQrtrTransportError;
		}
		return K60IpaQrtrSendFailed;
	}
	return K60IpaQrtrOk;
}

int
k60_ipa_qrtr_receive(K60IpaQrtr *session, const uint8_t *packet,
    size_t bytes)
{
	K60QrtrHeader header;
	const uint8_t *payload = NULL;
	uint32_t service, instance, node, port;
	int rc;

	if (session == NULL || packet == NULL) {
		return K60IpaQrtrBadArgument;
	}
	if (k60_qrtr_parse(packet, bytes, &header, &payload) != K60QrtrOk) {
		session->malformed++;
		return K60IpaQrtrMalformed;
	}
	session->datagrams++;
	if (header.type == K60QrtrData) {
		if (header.to_port != K60_IPA_QMI_HOST_PORT ||
		    session->remote_known == 0 ||
		    header.from_node != session->remote_node) {
			session->ignored++;
			return K60IpaQrtrIgnored;
		}
		if (header.size == 0 ||
		    header.size > K60_IPA_QMI_TRANSPORT_FRAME_BYTES) {
			session->malformed++;
			return K60IpaQrtrMalformed;
		}
		session->data_in++;
		rc = k60_ipa_qmi_transport_receive(&session->transport, payload,
		    header.size);
		if (rc < 0) {
			session->last_error = rc;
			return K60IpaQrtrTransportError;
		}
		return K60IpaQrtrOk;
	}
	if (header.type == K60QrtrNewServer) {
		if (payload == NULL || header.size != K60_QRTR_CONTROL_BYTES ||
		    get32(payload) != K60QrtrNewServer) {
			session->malformed++;
			return K60IpaQrtrMalformed;
		}
		service = get32(payload + 4);
		instance = get32(payload + 8);
		node = get32(payload + 12);
		port = get32(payload + 16);
		if (service != K60_IPA_QMI_SERVICE) {
			session->ignored++;
			return K60IpaQrtrIgnored;
		}
		if (instance != K60_IPA_QMI_INSTANCE_MODEM) {
			/* Our own announcement coming back from the name service. */
			session->ignored++;
			return K60IpaQrtrIgnored;
		}
		return note_modem_server(session, node, port);
	}
	if (header.type == K60QrtrBye && session->remote_known != 0 &&
	    header.from_node == session->remote_node) {
		session->remote_known = 0;
		session->started = 0;
		k60_ipa_qmi_transport_reset(&session->transport,
		    session->restricted_base, session_send_qmi, session);
		return K60IpaQrtrOk;
	}
	session->ignored++;
	return K60IpaQrtrIgnored;
}

int
k60_ipa_qrtr_flush(K60IpaQrtr *session)
{
	int rc;

	if (session == NULL || session->send == NULL) {
		return K60IpaQrtrBadArgument;
	}
	if (session->remote_known == 0) {
		return K60IpaQrtrIgnored;
	}
	rc = k60_ipa_qmi_transport_flush(&session->transport);
	if (rc < 0) {
		session->last_error = rc;
		return rc == K60IpaQmiTransportSendFailed ? K60IpaQrtrSendFailed :
		    K60IpaQrtrTransportError;
	}
	return K60IpaQrtrOk;
}

int
k60_ipa_qrtr_ready(const K60IpaQrtr *session)
{
	if (session == NULL) {
		return 0;
	}
	return k60_ipa_qmi_transport_ready(&session->transport);
}
