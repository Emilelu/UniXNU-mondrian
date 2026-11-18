/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Host regression for K60IpaQmiTransport: the QMI server driven through a fake
 * link, with the retry, subscription, completion and failure paths checked. */

#include <stdio.h>
#include <string.h>

#include "K60IpaQmiTransport.h"

#define CHECK(cond) do { \
	if (!(cond)) { \
		printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #cond); \
		return 1; \
	} \
} while (0)

#define MAX_FRAMES 16

typedef struct {
	unsigned attempts;
	unsigned sends;
	unsigned fail_at;
	int fail_code;
	uint8_t frame[MAX_FRAMES][K60_IPA_QMI_TRANSPORT_FRAME_BYTES];
	size_t bytes[MAX_FRAMES];
} Fake;

static int
fake_send(void *context, const uint8_t *frame, size_t bytes)
{
	Fake *fake = context;

	fake->attempts++;
	if (fake->fail_at != 0 && fake->attempts == fake->fail_at) {
		return fake->fail_code;
	}
	if (fake->sends < MAX_FRAMES) {
		memcpy(fake->frame[fake->sends], frame, bytes);
		fake->bytes[fake->sends] = bytes;
	}
	fake->sends++;
	return 0;
}

static void
put16(uint8_t *p, uint16_t value)
{
	p[0] = (uint8_t)value;
	p[1] = (uint8_t)(value >> 8);
}

static size_t
request(uint8_t *out, uint16_t transaction, uint16_t message,
    const uint8_t *tlv, size_t tlv_bytes)
{
	out[0] = 0;
	put16(out + 1, transaction);
	put16(out + 3, message);
	if (tlv_bytes != 0) {
		memcpy(out + 7, tlv, tlv_bytes);
	}
	put16(out + 5, (uint16_t)tlv_bytes);
	return 7u + tlv_bytes;
}

static size_t
response(uint8_t *out, size_t capacity, uint16_t transaction,
    uint16_t message, uint16_t result)
{
	return k60_ipa_qmi_build_response(out, capacity, transaction, message,
	    result, result != 0 ? 1 : 0, NULL, 0);
}

int
main(void)
{
	K60IpaQmiTransport transport;
	Fake fake;
	uint8_t frame[K60_IPA_QMI_TRANSPORT_FRAME_BYTES];
	uint8_t tlv[4] = { 1, 1, 0, 1 }; /* type 1, length 1, status 1 */
	uint16_t transaction, message, result, error;
	size_t bytes;
	int rc;

	memset(&fake, 0, sizeof(fake));
	fake.fail_code = -12;
	k60_ipa_qmi_transport_reset(&transport, 0x8b900000u, fake_send, &fake);

	/* First attempt, then a retry before any response. */
	CHECK(k60_ipa_qmi_transport_start(&transport) == 0);
	CHECK(fake.sends == 1);
	CHECK(fake.bytes[0] == K60_IPA_QMI_INIT_DRIVER_BYTES);
	CHECK(fake.frame[0][0] == 0);
	transaction = (uint16_t)(fake.frame[0][1] | (fake.frame[0][2] << 8));
	message = (uint16_t)(fake.frame[0][3] | (fake.frame[0][4] << 8));
	CHECK(transaction == 1);
	CHECK(message == K60_IPA_QMI_INIT_DRIVER);

	/* Retry before the first response: attempt 2 carries transaction 2. */
	CHECK(k60_ipa_qmi_transport_start(&transport) == 0);
	CHECK(fake.sends == 2);
	CHECK((fake.frame[1][1] | (fake.frame[1][2] << 8)) == 2);

	/* The second attempt is accepted: driver ready. */
	bytes = response(frame, sizeof(frame), 2, K60_IPA_QMI_INIT_DRIVER, 0);
	CHECK(k60_ipa_qmi_transport_receive(&transport, frame, bytes) == 0);
	CHECK(transport.server.state == K60IpaQmiServerDriverReady);

	/* INDICATION_REGISTER: one 14-byte success response. */
	bytes = request(frame, 3, K60_IPA_QMI_INDICATION_REGISTER, NULL, 0);
	CHECK(k60_ipa_qmi_transport_receive(&transport, frame, bytes) == 1);
	CHECK(fake.sends == 3);
	CHECK(fake.bytes[2] == K60_IPA_QMI_SIMPLE_BYTES);
	CHECK(k60_ipa_qmi_parse_response(fake.frame[2], fake.bytes[2], 3,
	    K60_IPA_QMI_INDICATION_REGISTER, &result, &error) == 0);
	CHECK(result == 0 && error == 0);

	/* DRIVER_INIT_COMPLETE status 1: reply plus the INIT_COMPLETE indication. */
	bytes = request(frame, 4, K60_IPA_QMI_DRIVER_INIT_COMPLETE, tlv, sizeof(tlv));
	CHECK(k60_ipa_qmi_transport_receive(&transport, frame, bytes) == 2);
	CHECK(fake.sends == 5);
	CHECK(fake.bytes[3] == K60_IPA_QMI_SIMPLE_BYTES);
	CHECK(fake.frame[4][0] == 4);
	CHECK((fake.frame[4][1] | (fake.frame[4][2] << 8)) == 0);
	CHECK((fake.frame[4][3] | (fake.frame[4][4] << 8)) == K60_IPA_QMI_INIT_COMPLETE);
	CHECK(fake.bytes[4] == K60_IPA_QMI_SIMPLE_BYTES);
	CHECK(k60_ipa_qmi_transport_ready(&transport) == 1);

	/* A later request still gets its reply but never a second INIT_COMPLETE. */
	bytes = request(frame, 5, K60_IPA_QMI_INDICATION_REGISTER, NULL, 0);
	CHECK(k60_ipa_qmi_transport_receive(&transport, frame, bytes) == 1);
	CHECK(fake.sends == 6);
	CHECK(k60_ipa_qmi_transport_ready(&transport) == 1);

	/* Three unanswered attempts exhaust the retry window. */
	memset(&fake, 0, sizeof(fake));
	fake.fail_code = -12;
	k60_ipa_qmi_transport_reset(&transport, 0x8b900000u, fake_send, &fake);
	CHECK(k60_ipa_qmi_transport_start(&transport) == 0);
	CHECK(k60_ipa_qmi_transport_start(&transport) == 0);
	CHECK(k60_ipa_qmi_transport_start(&transport) == 0);
	CHECK(fake.sends == 3);
	CHECK((fake.frame[2][1] | (fake.frame[2][2] << 8)) == 3);
	CHECK(k60_ipa_qmi_transport_start(&transport) ==
	    K60IpaQmiTransportExhausted);
	CHECK(fake.sends == 3);
	CHECK(transport.server.attempts == K60_IPA_QMI_TRANSPORT_ATTEMPTS);

	/* A failed send leaves the frame queued; flush delivers it. */
	memset(&fake, 0, sizeof(fake));
	fake.fail_code = -12;
	fake.fail_at = 1;
	k60_ipa_qmi_transport_reset(&transport, 0x8b900000u, fake_send, &fake);
	CHECK(k60_ipa_qmi_transport_start(&transport) ==
	    K60IpaQmiTransportSendFailed);
	CHECK(fake.sends == 0);
	CHECK(transport.pending_bytes == K60_IPA_QMI_INIT_DRIVER_BYTES);
	fake.fail_at = 0;
	CHECK(k60_ipa_qmi_transport_flush(&transport) == 0);
	CHECK(fake.sends == 1);
	CHECK(fake.bytes[0] == K60_IPA_QMI_INIT_DRIVER_BYTES);

	/* The INIT_COMPLETE frame itself can fail once and still be delivered. */
	memset(&fake, 0, sizeof(fake));
	fake.fail_code = -12;
	k60_ipa_qmi_transport_reset(&transport, 0x8b900000u, fake_send, &fake);
	CHECK(k60_ipa_qmi_transport_start(&transport) == 0);
	bytes = response(frame, sizeof(frame), 1, K60_IPA_QMI_INIT_DRIVER, 0);
	CHECK(k60_ipa_qmi_transport_receive(&transport, frame, bytes) == 0);
	bytes = request(frame, 2, K60_IPA_QMI_INDICATION_REGISTER, NULL, 0);
	CHECK(k60_ipa_qmi_transport_receive(&transport, frame, bytes) == 1);
	fake.fail_at = 4;
	bytes = request(frame, 3, K60_IPA_QMI_DRIVER_INIT_COMPLETE, tlv, sizeof(tlv));
	CHECK(k60_ipa_qmi_transport_receive(&transport, frame, bytes) ==
	    K60IpaQmiTransportSendFailed);
	CHECK(k60_ipa_qmi_transport_ready(&transport) == 0);
	CHECK(transport.pending_bytes == K60_IPA_QMI_SIMPLE_BYTES);
	fake.fail_at = 0;
	CHECK(k60_ipa_qmi_transport_flush(&transport) == 0);
	CHECK(k60_ipa_qmi_transport_ready(&transport) == 1);
	CHECK(fake.sends == 4);
	CHECK(fake.frame[3][0] == 4);
	CHECK((fake.frame[3][3] | (fake.frame[3][4] << 8)) == K60_IPA_QMI_INIT_COMPLETE);

	/* An unknown request is answered with result 1 / error 94. */
	memset(&fake, 0, sizeof(fake));
	fake.fail_code = -12;
	k60_ipa_qmi_transport_reset(&transport, 0x8b900000u, fake_send, &fake);
	CHECK(k60_ipa_qmi_transport_start(&transport) == 0);
	bytes = response(frame, sizeof(frame), 1, K60_IPA_QMI_INIT_DRIVER, 0);
	CHECK(k60_ipa_qmi_transport_receive(&transport, frame, bytes) == 0);
	bytes = request(frame, 2, 0x99, NULL, 0);
	CHECK(k60_ipa_qmi_transport_receive(&transport, frame, bytes) == 1);
	CHECK(fake.sends == 2);
	CHECK(k60_ipa_qmi_parse_response(fake.frame[1], fake.bytes[1], 2, 0x99,
	    &result, &error) == 0);
	CHECK(result == 1 && error == K60_IPA_QMI_SERVER_UNHANDLED);

	/* Argument handling. */
	k60_ipa_qmi_transport_reset(NULL, 0, fake_send, &fake);
	CHECK(k60_ipa_qmi_transport_start(NULL) == K60IpaQmiTransportBadArgument);
	CHECK(k60_ipa_qmi_transport_receive(NULL, frame, sizeof(frame)) ==
	    K60IpaQmiTransportBadArgument);
	CHECK(k60_ipa_qmi_transport_flush(NULL) == K60IpaQmiTransportBadArgument);
	CHECK(k60_ipa_qmi_transport_ready(NULL) == 0);

	(void)rc;
	printf("K60 IPA QMI TRANSPORT PASS start retry subscribe status complete exhaustion send-failure unhandled\n");
	return 0;
}
