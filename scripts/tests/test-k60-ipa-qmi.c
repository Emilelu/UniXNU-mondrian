/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Host test for the K60 IPA service 0x31 QMI codec: the INIT_DRIVER window
 * TLVs, INIT_COMPLETE, request classification, the DRIVER_INIT_COMPLETE
 * status, extended rules and every refused header shape. */

#include <stdio.h>
#include <string.h>

#include "K60IpaQmi.h"

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

static uint32_t
get32(const uint8_t *p)
{
	return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
	    ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
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
	if (tlv_bytes > 0) {
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

static const uint8_t *
find_tlv(const uint8_t *message, size_t bytes, uint8_t type, size_t *length)
{
	size_t at = 7;

	while (at + 3u <= bytes) {
		const size_t n = get16(message + at + 1);

		if (at + 3u + n > bytes) {
			return NULL;
		}
		if (message[at] == type) {
			*length = n;
			return message + at + 3u;
		}
		at += 3u + n;
	}
	return NULL;
}

static unsigned
count_tlvs(const uint8_t *message, size_t bytes)
{
	size_t at = 7;
	unsigned count = 0;

	while (at + 3u <= bytes) {
		const size_t n = get16(message + at + 1);

		if (at + 3u + n > bytes) {
			return 0xffffu;
		}
		at += 3u + n;
		count++;
	}
	return at == bytes ? count : 0xffffu;
}

static void
test_init_driver(void)
{
	uint8_t out[256];
	const uint8_t *value;
	size_t length = 0;
	size_t bytes;

	bytes = k60_ipa_qmi_build_init_driver(out, sizeof(out), 0x1234,
	    0x00580000u);
	check(bytes == K60_IPA_QMI_INIT_DRIVER_BYTES, "init-driver length");
	check(out[0] == 0 && get16(out + 1) == 0x1234 &&
	    get16(out + 3) == 0x21 && get16(out + 5) == 147,
	    "init-driver header");
	check(count_tlvs(out, bytes) == 17, "init-driver seventeen TLVs");
	value = find_tlv(out, bytes, 0x10, &length);
	check(value != NULL && length == 4 && get32(value) == 3,
	    "init-driver 0x10 platform");
	value = find_tlv(out, bytes, 0x11, &length);
	check(value != NULL && length == 8 && get32(value) == 0x00581708u &&
	    get32(value + 4) == 0x00581947u, "init-driver 0x11 SRAM window");
	value = find_tlv(out, bytes, 0x16, &length);
	check(value != NULL && length == 8 && get32(value) == 0x00583898u &&
	    get32(value + 4) == 0xd48u, "init-driver 0x16 timer window");
	value = find_tlv(out, bytes, 0x17, &length);
	check(value != NULL && length == 4 && get32(value) == 23,
	    "init-driver 0x17 endpoint 23");
	value = find_tlv(out, bytes, 0x21, &length);
	check(value != NULL && length == 4 && get32(value) == 0x00584fe8u,
	    "init-driver 0x21 rule window");
	value = find_tlv(out, bytes, 0x22, &length);
	check(value != NULL && length == 4 && get32(value) == 0x18,
	    "init-driver 0x22 rule size");
	check(k60_ipa_qmi_build_init_driver(out,
	    K60_IPA_QMI_INIT_DRIVER_BYTES - 1, 1, 0) == 0,
	    "init-driver short capacity");
	check(k60_ipa_qmi_build_init_driver(out,
	    K60_IPA_QMI_INIT_DRIVER_BYTES, 1, 0) ==
	    K60_IPA_QMI_INIT_DRIVER_BYTES, "init-driver exact capacity");
	check(k60_ipa_qmi_build_init_driver(NULL, sizeof(out), 1, 0) == 0,
	    "init-driver null buffer");
}

static void
test_init_complete(void)
{
	static const uint8_t expected[14] = {
		4, 0, 0, 0x22, 0, 7, 0, 2, 4, 0, 0, 0, 0, 0
	};
	uint8_t out[32];
	size_t bytes;

	bytes = k60_ipa_qmi_build_init_complete(out, sizeof(out));
	check(bytes == 14, "init-complete length");
	check(memcmp(out, expected, sizeof(expected)) == 0,
	    "init-complete bytes");
	check(k60_ipa_qmi_build_init_complete(out, 13) == 0,
	    "init-complete short capacity");
	check(k60_ipa_qmi_build_init_complete(NULL, sizeof(out)) == 0,
	    "init-complete null buffer");
}

static void
test_response(void)
{
	uint8_t out[256];
	uint32_t ids[3] = { 0x101, 0x102, 0x103 };
	const uint8_t *value;
	size_t length = 0;
	size_t bytes;

	bytes = k60_ipa_qmi_build_response(out, sizeof(out), 7, 0x35, 0, 0,
	    NULL, 0);
	check(bytes == 14, "response length");
	check(out[0] == 2 && get16(out + 1) == 7 && get16(out + 3) == 0x35 &&
	    get16(out + 5) == 7, "response header");
	check(out[7] == 2 && get16(out + 8) == 4 && get16(out + 10) == 0 &&
	    get16(out + 12) == 0, "response success result");
	bytes = k60_ipa_qmi_build_response(out, sizeof(out), 8, 0x23, 1, 0x10,
	    NULL, 0);
	check(get16(out + 10) == 1 && get16(out + 12) == 0x10,
	    "response failure result");
	bytes = k60_ipa_qmi_build_response(out, sizeof(out), 9, 0x23, 0, 0,
	    ids, 3);
	check(bytes == 30, "rules response length");
	value = find_tlv(out, bytes, 0x11, &length);
	check(value != NULL && length == 13 && value[0] == 3 &&
	    get32(value + 1) == 0x101 && get32(value + 5) == 0x102 &&
	    get32(value + 9) == 0x103, "rules response ids");
	check(k60_ipa_qmi_build_response(out, sizeof(out), 1, 0x23, 0, 0,
	    NULL, 1) == 0, "rules response null ids");
	check(k60_ipa_qmi_build_response(out, sizeof(out), 1, 0x23, 0, 0,
	    ids, K60_IPA_QMI_MAX_RULES + 1) == 0, "rules response too many");
	check(k60_ipa_qmi_build_response(out, 13, 1, 0x23, 0, 0, NULL, 0) == 0,
	    "response short capacity");
}

static void
test_parse_response(void)
{
	uint8_t out[256];
	uint16_t result = 0xffff, error = 0xffff;
	size_t bytes;

	bytes = k60_ipa_qmi_build_response(out, sizeof(out), 0x4242, 0x21, 0, 0,
	    NULL, 0);
	check(k60_ipa_qmi_parse_response(out, bytes, 0x4242, 0x21, &result,
	    &error) == 0 && result == 0 && error == 0, "parse response ok");
	check(k60_ipa_qmi_parse_response(out, bytes, 0x4243, 0x21, &result,
	    &error) != 0, "parse response transaction");
	check(k60_ipa_qmi_parse_response(out, bytes, 0x4242, 0x20, &result,
	    &error) != 0, "parse response message");
	out[0] = 0;
	check(k60_ipa_qmi_parse_response(out, bytes, 0x4242, 0x21, &result,
	    &error) != 0, "parse response type");
	out[0] = 2;
	check(k60_ipa_qmi_parse_response(out, 13, 0x4242, 0x21, &result,
	    &error) != 0, "parse response short");
	put16(out + 5, 0);
	check(k60_ipa_qmi_parse_response(out, bytes, 0x4242, 0x21, &result,
	    &error) != 0, "parse response no TLV");
	check(k60_ipa_qmi_parse_response(out, bytes, 0x4242, 0x21, NULL,
	    &error) == K60IpaQmiBadArgument, "parse response null result");
}

static void
test_classify(void)
{
	static const struct {
		uint16_t message;
		int kind;
	} kinds[] = {
		{ 0x20, K60IpaQmiKindIndicationRegister },
		{ 0x35, K60IpaQmiKindDriverInitComplete },
		{ 0x27, K60IpaQmiKindConfiguration },
		{ 0x24, K60IpaQmiKindFilterInstalled },
		{ 0x23, K60IpaQmiKindRules },
	};
	uint8_t request_bytes[16];
	uint16_t transaction = 0, message = 0;

	for (size_t i = 0; i < sizeof(kinds) / sizeof(kinds[0]); i++) {
		const size_t bytes = request(request_bytes, 5, kinds[i].message,
		    NULL, 0);

		check(k60_ipa_qmi_classify(request_bytes, bytes, &transaction,
		    &message) == kinds[i].kind, "classify known");
		check(transaction == 5 && message == kinds[i].message,
		    "classify ids");
	}
	check(k60_ipa_qmi_classify(request_bytes, request(request_bytes, 1, 0x99,
	    NULL, 0), NULL, NULL) == K60IpaQmiKindUnknown, "classify unknown");
	request_bytes[0] = 2;
	check(k60_ipa_qmi_classify(request_bytes, 7, NULL, NULL) < 0,
	    "classify response");
	request_bytes[0] = 0;
	check(k60_ipa_qmi_classify(request_bytes, 6, NULL, NULL) < 0,
	    "classify short");
}

static void
test_driver_status(void)
{
	uint8_t status = 0xff;
	uint8_t tlvs[16];
	uint8_t request_bytes[32];
	size_t at = 0;
	size_t bytes;
	uint8_t value[2];

	value[0] = 1;
	at = add_tlv(tlvs, at, 1, value, 1);
	bytes = request(request_bytes, 3, 0x35, tlvs, at);
	check(k60_ipa_qmi_driver_status(request_bytes, bytes, &status) == 0 &&
	    status == 1, "driver status ok");
	bytes = request(request_bytes, 3, 0x35, NULL, 0);
	check(k60_ipa_qmi_driver_status(request_bytes, bytes, &status) < 0,
	    "driver status missing TLV");
	value[0] = 0;
	value[1] = 0;
	at = add_tlv(tlvs, 0, 1, value, 2);
	bytes = request(request_bytes, 3, 0x35, tlvs, at);
	check(k60_ipa_qmi_driver_status(request_bytes, bytes, &status) < 0,
	    "driver status two byte TLV");
	bytes = request(request_bytes, 3, 0x20, NULL, 0);
	check(k60_ipa_qmi_driver_status(request_bytes, bytes, &status) < 0,
	    "driver status wrong message");
	check(k60_ipa_qmi_driver_status(request_bytes, bytes, NULL) ==
	    K60IpaQmiBadArgument, "driver status null");
}

static void
test_rules(void)
{
	uint32_t ids[8];
	size_t count = 0;
	uint8_t list[64];
	uint8_t tlvs[96];
	uint8_t request_bytes[128];
	size_t at = 0;
	size_t bytes;

	list[0] = 3;
	put32(list + 1, 0x101);
	put32(list + 5, 0x102);
	put32(list + 9, 0x103);
	at = add_tlv(tlvs, 0, 0x11, list, 13);
	bytes = request(request_bytes, 4, 0x23, tlvs, at);
	check(k60_ipa_qmi_rules(request_bytes, bytes, ids, 8, &count) == 0 &&
	    count == 3 && ids[0] == 0x101 && ids[1] == 0x102 &&
	    ids[2] == 0x103, "rules parse");
	check(k60_ipa_qmi_rules(request_bytes, bytes, ids, 2, &count) < 0,
	    "rules capacity");
	list[0] = 0;
	at = add_tlv(tlvs, 0, 0x11, list, 1);
	bytes = request(request_bytes, 4, 0x23, tlvs, at);
	check(k60_ipa_qmi_rules(request_bytes, bytes, ids, 8, &count) == 0 &&
	    count == 0, "rules empty");
	list[0] = K60_IPA_QMI_MAX_RULES + 1;
	at = add_tlv(tlvs, 0, 0x11, list, 1);
	bytes = request(request_bytes, 4, 0x23, tlvs, at);
	check(k60_ipa_qmi_rules(request_bytes, bytes, ids, 8, &count) < 0,
	    "rules too many");
	list[0] = 2;
	put32(list + 1, 1);
	at = add_tlv(tlvs, 0, 0x11, list, 5);
	bytes = request(request_bytes, 4, 0x23, tlvs, at);
	check(k60_ipa_qmi_rules(request_bytes, bytes, ids, 8, &count) < 0,
	    "rules truncated list");
	bytes = request(request_bytes, 4, 0x24, tlvs, at);
	check(k60_ipa_qmi_rules(request_bytes, bytes, ids, 8, &count) < 0,
	    "rules wrong message");
	check(k60_ipa_qmi_rules(request_bytes, bytes, NULL, 0, &count) ==
	    K60IpaQmiBadArgument, "rules null ids");
}

int
main(void)
{
	test_init_driver();
	test_init_complete();
	test_response();
	test_parse_response();
	test_classify();
	test_driver_status();
	test_rules();
	if (failures != 0) {
		printf("K60 IPA QMI FAIL %d\n", failures);
		return 1;
	}
	printf("K60 IPA QMI PASS init-driver init-complete response parse "
	    "classify driver-status rules\n");
	return 0;
}
