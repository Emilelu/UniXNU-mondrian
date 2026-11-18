/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Host test for the IPA QMI server state machine: the three INIT_DRIVER
 * attempts, an accepted and a refused INIT_DRIVER response, the 0x20/0x23/
 * 0x24/0x27/0x35 request handlers, the 0x22 INIT_COMPLETE gate and the
 * error-94 reply for an unknown message. */

#include <stdio.h>
#include <string.h>

#include "K60IpaQmiServer.h"

static int failures;

static void
check(int condition, const char *name)
{
	if (!condition) {
		printf("FAIL %s\n", name);
		failures++;
	}
}

static uint16_t
get16(const uint8_t *p)
{
	return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8));
}

static void
put16(uint8_t *p, uint16_t value)
{
	p[0] = (uint8_t)value;
	p[1] = (uint8_t)(value >> 8);
}

static void
put32(uint8_t *p, uint32_t value)
{
	p[0] = (uint8_t)value;
	p[1] = (uint8_t)(value >> 8);
	p[2] = (uint8_t)(value >> 16);
	p[3] = (uint8_t)(value >> 24);
}

static size_t
request(uint8_t *out, uint16_t transaction, uint16_t message,
    const uint8_t *tlvs, size_t tlv_bytes)
{
	out[0] = 0;
	put16(out + 1, transaction);
	put16(out + 3, message);
	put16(out + 5, (uint16_t)tlv_bytes);
	if (tlv_bytes != 0) {
		memcpy(out + 7, tlvs, tlv_bytes);
	}
	return 7u + tlv_bytes;
}

static size_t
add_tlv(uint8_t *out, size_t at, uint8_t type, const uint8_t *value,
    size_t bytes)
{
	out[at] = type;
	put16(out + at + 1, (uint16_t)bytes);
	memcpy(out + at + 3, value, bytes);
	return at + 3u + bytes;
}

static uint16_t
reply_result(const uint8_t *reply, size_t bytes, uint16_t *error)
{
	if (bytes < 14 || reply[7] != 2 || get16(reply + 8) != 4) {
		return 0xffff;
	}
	*error = get16(reply + 12);
	return get16(reply + 10);
}

static void
test_attempts(void)
{
	K60IpaQmiServer server;
	uint8_t frame[256];
	size_t bytes;

	k60_ipa_qmi_server_reset(&server, 0x00580000u);
	bytes = k60_ipa_qmi_server_init_driver(&server, frame, sizeof(frame));
	check(bytes == 154 && get16(frame + 1) == 1, "attempt one");
	bytes = k60_ipa_qmi_server_init_driver(&server, frame, sizeof(frame));
	check(bytes == 154 && get16(frame + 1) == 2, "attempt two");
	bytes = k60_ipa_qmi_server_init_driver(&server, frame, sizeof(frame));
	check(bytes == 154 && get16(frame + 1) == 3, "attempt three");
	check(k60_ipa_qmi_server_init_driver(&server, frame,
	    sizeof(frame)) == 0, "attempt four refused");
	check(server.state == K60IpaQmiServerInitSent &&
	    server.attempts == 3, "attempt state");
	check(k60_ipa_qmi_server_ready(&server) == 0, "not ready");
}

static void
test_refused(void)
{
	K60IpaQmiServer server;
	uint8_t frame[256], reply[256];
	size_t bytes, reply_bytes = 1;

	k60_ipa_qmi_server_reset(&server, 0);
	bytes = k60_ipa_qmi_server_init_driver(&server, frame, sizeof(frame));
	check(bytes == 154, "refused init built");
	bytes = k60_ipa_qmi_build_response(frame, sizeof(frame), 1, 0x21, 1,
	    0x20, NULL, 0);
	check(k60_ipa_qmi_server_receive(&server, frame, bytes, reply,
	    sizeof(reply), &reply_bytes) == K60IpaQmiServerInitRejected,
	    "refused verdict");
	check(server.state == K60IpaQmiServerFailed && reply_bytes == 0,
	    "refused state");
	check(k60_ipa_qmi_server_init_complete(&server, reply,
	    sizeof(reply)) == 0, "refused no indication");
	check(k60_ipa_qmi_server_init_driver(&server, frame,
	    sizeof(frame)) == 0, "refused stops attempts");
}

static void
test_happy_path(void)
{
	static const uint8_t expected[14] = {
		4, 0, 0, 0x22, 0, 7, 0, 2, 4, 0, 0, 0, 0, 0
	};
	K60IpaQmiServer server;
	uint8_t frame[512], reply[512], tlvs[64];
	uint8_t status = 1;
	size_t bytes, reply_bytes = 1, at;
	uint16_t error = 0;

	k60_ipa_qmi_server_reset(&server, 0x00580000u);
	bytes = k60_ipa_qmi_server_init_driver(&server, frame, sizeof(frame));
	check(bytes == 154, "happy init built");
	bytes = k60_ipa_qmi_build_response(frame, sizeof(frame), 1, 0x21, 0, 0,
	    NULL, 0);
	check(k60_ipa_qmi_server_receive(&server, frame, bytes, reply,
	    sizeof(reply), &reply_bytes) == K60IpaQmiServerOk &&
	    reply_bytes == 0 && server.driver_ready == 1, "happy accepted");
	check(k60_ipa_qmi_server_init_complete(&server, reply,
	    sizeof(reply)) == 0, "no indication before subscriber");
	bytes = request(frame, 7, 0x20, NULL, 0);
	check(k60_ipa_qmi_server_receive(&server, frame, bytes, reply,
	    sizeof(reply), &reply_bytes) == K60IpaQmiServerOk &&
	    reply_bytes == 14, "indication register reply");
	check(get16(reply + 1) == 7 && get16(reply + 3) == 0x20 &&
	    reply_result(reply, reply_bytes, &error) == 0 && error == 0,
	    "indication register result");
	check(server.subscribed == 1, "subscribed");
	check(k60_ipa_qmi_server_init_complete(&server, reply,
	    sizeof(reply)) == 0, "no indication before uc");
	at = add_tlv(tlvs, 0, 1, &status, 1);
	bytes = request(frame, 8, 0x35, tlvs, at);
	reply_bytes = 1;
	check(k60_ipa_qmi_server_receive(&server, frame, bytes, reply,
	    sizeof(reply), &reply_bytes) == K60IpaQmiServerOk &&
	    reply_bytes == 14, "driver status reply");
	check(reply_result(reply, reply_bytes, &error) == 0 &&
	    error == 0 && server.uc_ready == 1, "driver status accepted");
	reply_bytes = 1;
	bytes = k60_ipa_qmi_server_init_complete(&server, reply,
	    sizeof(reply));
	check(bytes == 14 && memcmp(reply, expected, 14) == 0 &&
	    server.indicated == 1 && server.state == K60IpaQmiServerComplete,
	    "init complete indication");
	check(k60_ipa_qmi_server_init_complete(&server, reply,
	    sizeof(reply)) == 0, "indication once");
	check(k60_ipa_qmi_server_ready(&server) == 1, "ready");
}

static void
test_driver_status_failure(void)
{
	K60IpaQmiServer server;
	uint8_t frame[128], reply[128], tlvs[16];
	uint8_t status = 0;
	size_t at, bytes, reply_bytes = 1;
	uint16_t error = 0;

	k60_ipa_qmi_server_reset(&server, 0);
	at = add_tlv(tlvs, 0, 1, &status, 1);
	bytes = request(frame, 1, 0x35, tlvs, at);
	reply_bytes = 1;
	check(k60_ipa_qmi_server_receive(&server, frame, bytes, reply,
	    sizeof(reply), &reply_bytes) == K60IpaQmiServerOk,
	    "status zero handled");
	check(reply_result(reply, reply_bytes, &error) == 1 && error == 1 &&
	    server.uc_ready == 0, "status zero refused");
}

static void
test_configuration(void)
{
	K60IpaQmiServer server;
	uint8_t frame[512], reply[512], tlvs[64];
	uint8_t value[10] = { 0 };
	size_t at = 0, bytes, reply_bytes = 1;
	uint16_t error = 0;

	k60_ipa_qmi_server_reset(&server, 0);
	at = add_tlv(tlvs, at, 0x10, value, 4);
	at = add_tlv(tlvs, at, 0x13, value, 10);
	bytes = request(frame, 4, 0x27, tlvs, at);
	reply_bytes = 1;
	check(k60_ipa_qmi_server_receive(&server, frame, bytes, reply,
	    sizeof(reply), &reply_bytes) == K60IpaQmiServerOk,
	    "configuration handled");
	check(reply_result(reply, reply_bytes, &error) == 0,
	    "configuration accepted");
	check(server.config_bytes == 20 && (server.config_fields[0] & 1) != 0 &&
	    (server.config_fields[0] & 8) != 0, "configuration fields");
}

static void
test_filter(void)
{
	K60IpaQmiServer server;
	uint8_t frame[512], reply[512], tlvs[96];
	uint8_t pipe[4], status[2], list[17] = { 2 };
	size_t at, bytes, reply_bytes = 1;
	uint16_t error = 0;

	put32(pipe, 3);
	put16(status, 1);
	list[1] = 0xaa;
	list[9] = 0xbb;
	k60_ipa_qmi_server_reset(&server, 0);
	at = add_tlv(tlvs, 0, 1, pipe, 4);
	at = add_tlv(tlvs, at, 2, status, 2);
	at = add_tlv(tlvs, at, 3, list, sizeof(list));
	bytes = request(frame, 5, 0x24, tlvs, at);
	reply_bytes = 1;
	check(k60_ipa_qmi_server_receive(&server, frame, bytes, reply,
	    sizeof(reply), &reply_bytes) == K60IpaQmiServerOk,
	    "filter handled");
	check(reply_result(reply, reply_bytes, &error) == 0 &&
	    server.notifications == 1 && server.last_filter_pipe == 3 &&
	    server.last_filter_status == 1, "filter accepted");
	put32(pipe, 40);
	at = add_tlv(tlvs, 0, 1, pipe, 4);
	at = add_tlv(tlvs, at, 2, status, 2);
	at = add_tlv(tlvs, at, 3, list, sizeof(list));
	bytes = request(frame, 6, 0x24, tlvs, at);
	reply_bytes = 1;
	check(k60_ipa_qmi_server_receive(&server, frame, bytes, reply,
	    sizeof(reply), &reply_bytes) == K60IpaQmiServerOk &&
	    reply_result(reply, reply_bytes, &error) == 1 &&
	    server.notifications == 1, "filter bad pipe refused");
}

static void
test_rules(void)
{
	K60IpaQmiServer server;
	uint8_t frame[512], reply[512], tlvs[32];
	uint8_t list[9] = { 2 };
	size_t at, bytes, reply_bytes = 1;
	const uint8_t *value = NULL;
	size_t length = 0;

	put32(list + 1, 0x41);
	put32(list + 5, 0x42);
	k60_ipa_qmi_server_reset(&server, 0);
	at = add_tlv(tlvs, 0, 0x11, list, sizeof(list));
	bytes = request(frame, 9, 0x23, tlvs, at);
	reply_bytes = 1;
	check(k60_ipa_qmi_server_receive(&server, frame, bytes, reply,
	    sizeof(reply), &reply_bytes) == K60IpaQmiServerOk,
	    "rules handled");
	check(reply_bytes == 26 && server.rules == 2, "rules reply length");
	for (size_t p = 14; p + 3 <= reply_bytes; ) {
		const size_t n = get16(reply + p + 1);

		if (reply[p] == 0x11) {
			value = reply + p + 3;
			length = n;
			break;
		}
		p += 3 + n;
	}
	check(value != NULL && length == 9 && value[0] == 2 &&
	    value[1] == 0x41 && value[5] == 0x42, "rules ids echoed");
}

static void
test_unhandled(void)
{
	K60IpaQmiServer server;
	uint8_t frame[64], reply[64];
	size_t bytes, reply_bytes = 1;
	uint16_t error = 0;

	k60_ipa_qmi_server_reset(&server, 0);
	bytes = request(frame, 3, 0x99, NULL, 0);
	check(k60_ipa_qmi_server_receive(&server, frame, bytes, reply,
	    sizeof(reply), &reply_bytes) == K60IpaQmiServerUnhandled &&
	    reply_bytes == 14, "unhandled reply");
	check(reply_result(reply, reply_bytes, &error) == 1 &&
	    error == 94 && server.errors == 1, "unhandled result");
}

static void
test_malformed(void)
{
	K60IpaQmiServer server;
	uint8_t frame[64], reply[64];
	size_t bytes, reply_bytes = 1;

	k60_ipa_qmi_server_reset(&server, 0);
	bytes = request(frame, 1, 0x20, NULL, 0);
	check(k60_ipa_qmi_server_receive(&server, frame, bytes - 1, reply,
	    sizeof(reply), &reply_bytes) == K60IpaQmiServerMalformed,
	    "short frame");
	bytes = request(frame, 1, 0x20, NULL, 0);
	frame[0] = 1;
	check(k60_ipa_qmi_server_receive(&server, frame, bytes, reply,
	    sizeof(reply), &reply_bytes) == K60IpaQmiServerMalformed,
	    "bad type");
	frame[0] = 2;
	check(k60_ipa_qmi_server_receive(&server, frame, bytes, reply,
	    sizeof(reply), &reply_bytes) == K60IpaQmiServerIgnored,
	    "stray response ignored");
	check(k60_ipa_qmi_server_receive(NULL, frame, bytes, reply,
	    sizeof(reply), &reply_bytes) == K60IpaQmiServerBadArgument,
	    "null server");
	check(k60_ipa_qmi_server_receive(&server, frame, bytes, reply,
	    sizeof(reply), NULL) == K60IpaQmiServerBadArgument,
	    "null out bytes");
}

static void
test_response_filters(void)
{
	K60IpaQmiServer server;
	uint8_t frame[64], reply[64];
	size_t bytes, reply_bytes = 1;

	k60_ipa_qmi_server_reset(&server, 0);
	(void)k60_ipa_qmi_server_init_driver(&server, frame, sizeof(frame));
	bytes = k60_ipa_qmi_build_response(frame, sizeof(frame), 2, 0x21, 0, 0,
	    NULL, 0);
	check(k60_ipa_qmi_server_receive(&server, frame, bytes, reply,
	    sizeof(reply), &reply_bytes) == K60IpaQmiServerIgnored,
	    "wrong transaction ignored");
	bytes = k60_ipa_qmi_build_response(frame, sizeof(frame), 1, 0x22, 0, 0,
	    NULL, 0);
	check(k60_ipa_qmi_server_receive(&server, frame, bytes, reply,
	    sizeof(reply), &reply_bytes) == K60IpaQmiServerIgnored,
	    "wrong message ignored");
}

int
main(void)
{
	test_attempts();
	test_refused();
	test_happy_path();
	test_driver_status_failure();
	test_configuration();
	test_filter();
	test_rules();
	test_unhandled();
	test_malformed();
	test_response_filters();
	if (failures != 0) {
		printf("K60 IPA QMI SERVER FAIL %d\n", failures);
		return 1;
	}
	printf("K60 IPA QMI SERVER PASS attempts refused happy-path status "
	    "configuration filter rules unhandled malformed\n");
	return 0;
}
