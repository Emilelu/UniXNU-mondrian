/* SPDX-License-Identifier: BSD-2-Clause-Patent */

#include "K60ModemSysmon.h"

#define K60_SYSMON_REQUEST  0u
#define K60_SYSMON_RESPONSE 1u

static void
put16(uint8_t *at, uint16_t value)
{
	at[0] = (uint8_t)(value & 0xffu);
	at[1] = (uint8_t)((value >> 8) & 0xffu);
}

static uint16_t
get16(const uint8_t *at)
{
	return (uint16_t)(at[0] | ((uint16_t)at[1] << 8));
}

static size_t
name_length(const char *name)
{
	size_t length = 0;

	while (length < K60_SYSMON_NAME_MAX && name[length] != '\0') {
		++length;
	}
	return length;
}

size_t
k60_sysmon_build_event(uint8_t *out, size_t capacity, uint16_t transaction,
    const char *name, uint32_t state)
{
	size_t length, at;

	if (out == NULL || name == NULL || capacity < K60_SYSMON_MAX_BYTES) {
		return 0;
	}
	length = name_length(name);
	if (length == 0 || length >= K60_SYSMON_NAME_MAX) {
		return 0;
	}
	/* Header: type, transaction, message, then the length of the TLVs. */
	out[0] = K60_SYSMON_REQUEST;
	put16(out + 1, transaction);
	put16(out + 3, K60_SYSMON_MESSAGE);
	at = 7;
	out[at++] = 1;                        /* TLV 1: the subsystem name */
	put16(out + at, (uint16_t)(length + 1));
	at += 2;
	out[at++] = (uint8_t)length;
	for (size_t i = 0; i < length; ++i) {
		out[at++] = (uint8_t)name[i];
	}
	out[at++] = 2;                        /* TLV 2: the new state */
	put16(out + at, 4);
	at += 2;
	put16(out + at, (uint16_t)(state & 0xffu));
	put16(out + at + 2, 0);
	at += 4;
	out[at++] = 3;                        /* TLV 3: the transaction echo */
	put16(out + at, 4);
	at += 2;
	put16(out + at, transaction);
	put16(out + at + 2, 0);
	at += 4;
	out[at++] = 0x10;                     /* TLV 0x10: zero, as Pong sends */
	put16(out + at, 4);
	at += 2;
	put16(out + at, 0);
	put16(out + at + 2, 0);
	at += 4;
	put16(out + 5, (uint16_t)(at - 7));
	return at;
}

int
k60_sysmon_parse_reply(const void *bytes, size_t length, uint16_t transaction,
    uint16_t *code_out)
{
	const uint8_t *data = (const uint8_t *)bytes;
	size_t at, end;

	if (data == NULL || length < 7) {
		return -1;
	}
	if (data[0] != K60_SYSMON_RESPONSE ||
	    get16(data + 1) != transaction ||
	    get16(data + 3) != K60_SYSMON_MESSAGE) {
		return -1;
	}
	end = 7 + get16(data + 5);
	if (end > length) {
		end = length;
	}
	at = 7;
	while (at + 3 <= end) {
		uint8_t tag = data[at];
		size_t size = get16(data + at + 1);
		size_t start = at + 3;

		if (start + size > end) {
			return -1;
		}
		if (tag == 2) {
			if (size != 4) {
				return -1;
			}
			if (code_out != NULL) {
				*code_out = get16(data + start + 2);
			}
			return (get16(data + start) == 0) ? 0 : (int)get16(data + start + 2);
		}
		at = start + size;
	}
	return -1;
}
