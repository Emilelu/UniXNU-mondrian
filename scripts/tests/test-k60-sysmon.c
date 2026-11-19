/* SPDX-License-Identifier: BSD-2-Clause-Patent */

#include <stdio.h>
#include <string.h>

#include "K60ModemSysmon.h"

static int failures;

#define CHECK(what, condition) do { \
	if (!(condition)) { \
		printf("FAIL %s (line %d)\n", what, __LINE__); \
		++failures; \
	} \
} while (0)

static void
put16(uint8_t *at, unsigned value)
{
	at[0] = (uint8_t)(value & 0xffu);
	at[1] = (uint8_t)((value >> 8) & 0xffu);
}

static size_t
reply(uint8_t *out, unsigned transaction, unsigned message, int error, unsigned code)
{
	size_t at = 7;

	out[0] = 1;
	put16(out + 1, transaction);
	put16(out + 3, message);
	out[at++] = 2;
	put16(out + at, 4);
	at += 2;
	put16(out + at, error ? 1u : 0u);
	put16(out + at + 2, code);
	at += 4;
	put16(out + 5, (unsigned)(at - 7));
	return at;
}

int
main(void)
{
	uint8_t event[K60_SYSMON_MAX_BYTES];
	uint8_t answer[32];
	size_t bytes, at;
	uint16_t code = 0;

	bytes = k60_sysmon_build_event(event, sizeof(event), 7, "adsp",
	    K60_SYSMON_STATE_AFTER_POWERUP);
	CHECK("length", bytes == 7 + (3 + 1 + 4) + 7 * 3);
	CHECK("type", event[0] == 0);
	CHECK("transaction", event[1] == 7 && event[2] == 0);
	CHECK("message", event[3] == 0x25 && event[4] == 0);
	CHECK("tlv bytes", event[5] == (uint8_t)(bytes - 7) && event[6] == 0);
	CHECK("tlv1 tag", event[7] == 1);
	CHECK("tlv1 length", event[8] == 5 && event[9] == 0);
	CHECK("tlv1 name length", event[10] == 4);
	CHECK("tlv1 name", memcmp(event + 11, "adsp", 4) == 0);
	at = 15;
	CHECK("tlv2 tag", event[at] == 2);
	CHECK("tlv2 length", event[at + 1] == 4);
	CHECK("tlv2 state", event[at + 3] == 1 && event[at + 4] == 0);
	at += 7;
	CHECK("tlv3 tag", event[at] == 3);
	CHECK("tlv3 transaction", event[at + 3] == 7);
	at += 7;
	CHECK("tlv10 tag", event[at] == 0x10);
	CHECK("tlv10 zero", event[at + 3] == 0 && event[at + 6] == 0);

	CHECK("no room", k60_sysmon_build_event(event, 32, 1, "adsp", 1) == 0);
	CHECK("no name", k60_sysmon_build_event(event, sizeof(event), 1, "", 1) == 0);
	CHECK("null name", k60_sysmon_build_event(event, sizeof(event), 1, NULL, 1) == 0);
	CHECK("null out", k60_sysmon_build_event(NULL, 64, 1, "adsp", 1) == 0);

	bytes = reply(answer, 7, 0x25, 0, 0);
	CHECK("ack", k60_sysmon_parse_reply(answer, bytes, 7, &code) == 0);
	CHECK("ack code", code == 0);
	bytes = reply(answer, 7, 0x25, 1, 48);
	CHECK("refusal", k60_sysmon_parse_reply(answer, bytes, 7, &code) == 48);
	CHECK("refusal code", code == 48);
	CHECK("other transaction", k60_sysmon_parse_reply(answer, bytes, 8, NULL) == -1);
	bytes = reply(answer, 7, 0x24, 0, 0);
	CHECK("other message", k60_sysmon_parse_reply(answer, bytes, 7, NULL) == -1);
	bytes = reply(answer, 7, 0x25, 0, 0);
	answer[0] = 0;
	CHECK("request is not a reply", k60_sysmon_parse_reply(answer, bytes, 7, NULL) == -1);
	answer[0] = 1;
	CHECK("truncated", k60_sysmon_parse_reply(answer, 6, 7, NULL) == -1);
	CHECK("short tlv", k60_sysmon_parse_reply(answer, 9, 7, NULL) == -1);
	CHECK("null bytes", k60_sysmon_parse_reply(NULL, 16, 7, NULL) == -1);
	answer[7] = 0x10;
	CHECK("no result tlv", k60_sysmon_parse_reply(answer, bytes, 7, NULL) == -1);

	if (failures != 0) {
		printf("K60 SYSMON FAIL %d check(s)\n", failures);
		return 1;
	}
	printf("K60 SYSMON PASS event, reply, refusals\n");
	return 0;
}
