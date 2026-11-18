/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* K60 IPA service 0x31 QMI codec; see K60IpaQmi.h for the message directions
 * and the Pong reference.  Pure buffer movement, so the host test runs the
 * same code as the kernel.
 */

#include "K60IpaQmi.h"

_Static_assert(K60_IPA_QMI_HEADER_BYTES == 7u, "QMI header is seven bytes");
_Static_assert(K60_IPA_QMI_INIT_DRIVER_BYTES == 154u,
    "seventeen SRAM TLVs plus the header");
_Static_assert(K60_IPA_QMI_SIMPLE_BYTES == 14u, "result TLV is seven bytes");

static uint16_t
qmi_get16(const uint8_t *p)
{
	return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8));
}

static uint32_t
qmi_get32(const uint8_t *p)
{
	return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
	    ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static void
qmi_put16(uint8_t *p, uint16_t value)
{
	p[0] = (uint8_t)value;
	p[1] = (uint8_t)(value >> 8);
}

static void
qmi_put32(uint8_t *p, uint32_t value)
{
	p[0] = (uint8_t)value;
	p[1] = (uint8_t)(value >> 8);
	p[2] = (uint8_t)(value >> 16);
	p[3] = (uint8_t)(value >> 24);
}

static int
qmi_begin(uint8_t *out, size_t capacity, uint8_t type, uint16_t transaction,
    uint16_t message, size_t *used)
{
	if (out == NULL || capacity < K60_IPA_QMI_HEADER_BYTES) {
		return K60IpaQmiTooLong;
	}
	out[0] = type;
	qmi_put16(out + 1, transaction);
	qmi_put16(out + 3, message);
	qmi_put16(out + 5, 0);
	*used = K60_IPA_QMI_HEADER_BYTES;
	return K60IpaQmiOk;
}

static int
qmi_finish(uint8_t *out, size_t used)
{
	if (used < K60_IPA_QMI_HEADER_BYTES ||
	    used - K60_IPA_QMI_HEADER_BYTES > 0xffffu) {
		return K60IpaQmiTooLong;
	}
	qmi_put16(out + 5, (uint16_t)(used - K60_IPA_QMI_HEADER_BYTES));
	return K60IpaQmiOk;
}

static int
qmi_tlv(uint8_t *out, size_t capacity, size_t *used, uint8_t type,
    const uint8_t *value, size_t bytes)
{
	size_t at = *used;

	if (bytes > 0xffffu || at + 3u + bytes > capacity) {
		return K60IpaQmiTooLong;
	}
	out[at] = type;
	qmi_put16(out + at + 1, (uint16_t)bytes);
	for (size_t i = 0; i < bytes; i++) {
		out[at + 3u + i] = value[i];
	}
	*used = at + 3u + bytes;
	return K60IpaQmiOk;
}

static int
qmi_tlv_u32(uint8_t *out, size_t capacity, size_t *used, uint8_t type,
    uint32_t value)
{
	uint8_t encoded[4];

	qmi_put32(encoded, value);
	return qmi_tlv(out, capacity, used, type, encoded, sizeof(encoded));
}

static int
qmi_tlv_pair(uint8_t *out, size_t capacity, size_t *used, uint8_t type,
    uint32_t first, uint32_t second)
{
	uint8_t encoded[8];

	qmi_put32(encoded, first);
	qmi_put32(encoded + 4, second);
	return qmi_tlv(out, capacity, used, type, encoded, sizeof(encoded));
}

static int
qmi_find_tlv(const uint8_t *data, size_t bytes, uint8_t type,
    const uint8_t **value, size_t *value_bytes)
{
	size_t at = 0;

	while (at + 3u <= bytes) {
		const uint8_t kind = data[at];
		const size_t length = qmi_get16(data + at + 1);

		if (at + 3u + length > bytes) {
			return K60IpaQmiMalformed;
		}
		if (kind == type) {
			if (value != NULL) {
				*value = data + at + 3u;
			}
			if (value_bytes != NULL) {
				*value_bytes = length;
			}
			return 1;
		}
		at += 3u + length;
	}
	return 0;
}

/* Validates one request header and hands back its TLV region. */
static int
qmi_request(const uint8_t *data, size_t bytes, uint16_t *transaction,
    uint16_t *message, const uint8_t **tlvs, size_t *tlv_bytes)
{
	size_t length;

	if (data == NULL || bytes < K60_IPA_QMI_HEADER_BYTES) {
		return K60IpaQmiMalformed;
	}
	if (data[0] != 0u) {
		return K60IpaQmiMalformed;
	}
	length = qmi_get16(data + 5);
	if (length > bytes - K60_IPA_QMI_HEADER_BYTES) {
		return K60IpaQmiMalformed;
	}
	if (transaction != NULL) {
		*transaction = qmi_get16(data + 1);
	}
	if (message != NULL) {
		*message = qmi_get16(data + 3);
	}
	if (tlvs != NULL) {
		*tlvs = data + K60_IPA_QMI_HEADER_BYTES;
	}
	if (tlv_bytes != NULL) {
		*tlv_bytes = length;
	}
	return K60IpaQmiOk;
}

size_t
k60_ipa_qmi_build_init_driver(uint8_t *out, size_t capacity,
    uint16_t transaction, uint32_t restricted_base)
{
	const uint32_t base = restricted_base;
	size_t used = 0;

	if (out == NULL || capacity < K60_IPA_QMI_INIT_DRIVER_BYTES) {
		return 0;
	}
	if (qmi_begin(out, capacity, 0, transaction, K60_IPA_QMI_INIT_DRIVER,
	    &used) != K60IpaQmiOk ||
	    qmi_tlv_u32(out, capacity, &used, 0x10, 3u) != K60IpaQmiOk ||
	    qmi_tlv_pair(out, capacity, &used, 0x11, base + 0x1708u,
	    base + 0x1947u) != K60IpaQmiOk ||
	    qmi_tlv_pair(out, capacity, &used, 0x12, base + 0x1528u,
	    10u) != K60IpaQmiOk ||
	    qmi_tlv_pair(out, capacity, &used, 0x13, base + 0x1668u,
	    10u) != K60IpaQmiOk ||
	    qmi_tlv_u32(out, capacity, &used, 0x14, base + 0x1308u) != K60IpaQmiOk ||
	    qmi_tlv_u32(out, capacity, &used, 0x15, base + 0x1408u) != K60IpaQmiOk ||
	    qmi_tlv_pair(out, capacity, &used, 0x16, base + 0x3898u,
	    0xd48u) != K60IpaQmiOk ||
	    qmi_tlv_u32(out, capacity, &used, 0x17, 23u) != K60IpaQmiOk ||
	    qmi_tlv_pair(out, capacity, &used, 0x19, base + 0x1b40u,
	    base + 0x265fu) != K60IpaQmiOk ||
	    qmi_tlv_pair(out, capacity, &used, 0x1b, base + 0x1488u,
	    10u) != K60IpaQmiOk ||
	    qmi_tlv_pair(out, capacity, &used, 0x1c, base + 0x15c8u,
	    10u) != K60IpaQmiOk ||
	    qmi_tlv_u32(out, capacity, &used, 0x1d, base + 0x1288u) != K60IpaQmiOk ||
	    qmi_tlv_u32(out, capacity, &used, 0x1e, base + 0x1388u) != K60IpaQmiOk ||
	    qmi_tlv_u32(out, capacity, &used, 0x1f, base + 0x2868u) != K60IpaQmiOk ||
	    qmi_tlv_u32(out, capacity, &used, 0x20, 0x60u) != K60IpaQmiOk ||
	    qmi_tlv_u32(out, capacity, &used, 0x21, base + 0x4fe8u) != K60IpaQmiOk ||
	    qmi_tlv_u32(out, capacity, &used, 0x22, 0x18u) != K60IpaQmiOk ||
	    qmi_finish(out, used) != K60IpaQmiOk) {
		return 0;
	}
	return used;
}

size_t
k60_ipa_qmi_build_init_complete(uint8_t *out, size_t capacity)
{
	static const uint8_t success[4] = { 0, 0, 0, 0 };
	size_t used = 0;

	if (out == NULL || capacity < K60_IPA_QMI_SIMPLE_BYTES) {
		return 0;
	}
	if (qmi_begin(out, capacity, 4, 0, K60_IPA_QMI_INIT_COMPLETE,
	    &used) != K60IpaQmiOk ||
	    qmi_tlv(out, capacity, &used, K60_IPA_QMI_TLV_RESULT, success,
	    sizeof(success)) != K60IpaQmiOk ||
	    qmi_finish(out, used) != K60IpaQmiOk) {
		return 0;
	}
	return used;
}

size_t
k60_ipa_qmi_build_response(uint8_t *out, size_t capacity, uint16_t transaction,
    uint16_t message, uint16_t result, uint16_t error, const uint32_t *rule_ids,
    size_t rule_count)
{
	uint8_t status[4];
	uint8_t list[1u + 4u * K60_IPA_QMI_MAX_RULES];
	size_t used = 0;

	if (out == NULL || rule_count > K60_IPA_QMI_MAX_RULES ||
	    (rule_count > 0 && rule_ids == NULL)) {
		return 0;
	}
	if (qmi_begin(out, capacity, 2, transaction, message, &used) !=
	    K60IpaQmiOk) {
		return 0;
	}
	qmi_put16(status, (uint16_t)(result != 0 ? 1 : 0));
	qmi_put16(status + 2, error);
	if (qmi_tlv(out, capacity, &used, K60_IPA_QMI_TLV_RESULT, status,
	    sizeof(status)) != K60IpaQmiOk) {
		return 0;
	}
	if (rule_count > 0) {
		list[0] = (uint8_t)rule_count;
		for (size_t i = 0; i < rule_count; i++) {
			qmi_put32(list + 1u + 4u * i, rule_ids[i]);
		}
		if (qmi_tlv(out, capacity, &used, K60_IPA_QMI_TLV_RULES, list,
		    1u + 4u * rule_count) != K60IpaQmiOk) {
			return 0;
		}
	}
	if (qmi_finish(out, used) != K60IpaQmiOk) {
		return 0;
	}
	return used;
}

int
k60_ipa_qmi_parse_response(const uint8_t *data, size_t bytes,
    uint16_t transaction, uint16_t message, uint16_t *result, uint16_t *error)
{
	const uint8_t *value = NULL;
	size_t value_bytes = 0;
	size_t length;
	int found;

	if (result == NULL || error == NULL) {
		return K60IpaQmiBadArgument;
	}
	if (data == NULL || bytes < K60_IPA_QMI_HEADER_BYTES || data[0] != 2u) {
		return K60IpaQmiMalformed;
	}
	if (qmi_get16(data + 1) != transaction ||
	    qmi_get16(data + 3) != message) {
		return K60IpaQmiMalformed;
	}
	length = qmi_get16(data + 5);
	if (length > bytes - K60_IPA_QMI_HEADER_BYTES) {
		return K60IpaQmiMalformed;
	}
	found = qmi_find_tlv(data + K60_IPA_QMI_HEADER_BYTES, length,
	    K60_IPA_QMI_TLV_RESULT, &value, &value_bytes);
	if (found != 1 || value_bytes != 4u) {
		return K60IpaQmiMalformed;
	}
	*result = qmi_get16(value);
	*error = qmi_get16(value + 2);
	return K60IpaQmiOk;
}

int
k60_ipa_qmi_classify(const uint8_t *data, size_t bytes, uint16_t *transaction,
    uint16_t *message)
{
	uint16_t kind;

	if (qmi_request(data, bytes, transaction, &kind, NULL, NULL) !=
	    K60IpaQmiOk) {
		return K60IpaQmiMalformed;
	}
	if (message != NULL) {
		*message = kind;
	}
	switch (kind) {
	case K60_IPA_QMI_INDICATION_REGISTER:
		return K60IpaQmiKindIndicationRegister;
	case K60_IPA_QMI_DRIVER_INIT_COMPLETE:
		return K60IpaQmiKindDriverInitComplete;
	case K60_IPA_QMI_CONFIGURATION:
		return K60IpaQmiKindConfiguration;
	case K60_IPA_QMI_FILTER_INSTALLED:
		return K60IpaQmiKindFilterInstalled;
	case K60_IPA_QMI_RULES:
		return K60IpaQmiKindRules;
	default:
		return K60IpaQmiKindUnknown;
	}
}

int
k60_ipa_qmi_driver_status(const uint8_t *data, size_t bytes, uint8_t *status)
{
	const uint8_t *value = NULL;
	const uint8_t *tlvs = NULL;
	size_t value_bytes = 0;
	size_t tlv_bytes = 0;
	uint16_t message = 0;

	if (status == NULL) {
		return K60IpaQmiBadArgument;
	}
	if (qmi_request(data, bytes, NULL, &message, &tlvs, &tlv_bytes) !=
	    K60IpaQmiOk || message != K60_IPA_QMI_DRIVER_INIT_COMPLETE) {
		return K60IpaQmiMalformed;
	}
	if (qmi_find_tlv(tlvs, tlv_bytes, K60_IPA_QMI_TLV_DRIVER_STATUS,
	    &value, &value_bytes) != 1 || value_bytes != 1u) {
		return K60IpaQmiMalformed;
	}
	*status = value[0];
	return K60IpaQmiOk;
}

int
k60_ipa_qmi_rules(const uint8_t *data, size_t bytes, uint32_t *ids,
    size_t capacity, size_t *count)
{
	const uint8_t *value = NULL;
	const uint8_t *tlvs = NULL;
	size_t value_bytes = 0;
	size_t tlv_bytes = 0;
	size_t wanted;
	uint16_t message = 0;

	if (ids == NULL || count == NULL) {
		return K60IpaQmiBadArgument;
	}
	if (qmi_request(data, bytes, NULL, &message, &tlvs, &tlv_bytes) !=
	    K60IpaQmiOk || message != K60_IPA_QMI_RULES) {
		return K60IpaQmiMalformed;
	}
	if (qmi_find_tlv(tlvs, tlv_bytes, K60_IPA_QMI_TLV_RULES, &value,
	    &value_bytes) != 1 || value_bytes < 1u) {
		return K60IpaQmiMalformed;
	}
	wanted = value[0];
	if (wanted > K60_IPA_QMI_MAX_RULES || wanted > capacity ||
	    value_bytes != 1u + 4u * wanted) {
		return K60IpaQmiMalformed;
	}
	for (size_t i = 0; i < wanted; i++) {
		ids[i] = qmi_get32(value + 1u + 4u * i);
	}
	*count = wanted;
	return K60IpaQmiOk;
}
