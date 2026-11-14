/*
 * Host test for the RPMh command-database reader.
 *
 * The synthetic database is built here from the layout that
 * UniXNU-sheng/package/QcomRpmh.c documents and that its own host test pins,
 * so a wrong offset, a wrong magic or a wrong entry size fails on the host
 * instead of on the phone.
 *
 *   cc -std=c11 -O1 -I drivers/PongPower -o build/railtest \
 *      scripts/tests/test-k60-pmic-rail.c drivers/PongPower/K60PmicRail.c
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "K60PmicRail.h"

static int failures;

#define CHECK(cond) do { \
	if (!(cond)) { \
		printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #cond); \
		failures++; \
	} \
} while (0)

static void
put16(uint8_t *p, uint16_t v)
{
	p[0] = (uint8_t)(v & 0xff);
	p[1] = (uint8_t)(v >> 8);
}

static void
put32(uint8_t *p, uint32_t v)
{
	put16(p, (uint16_t)(v & 0xffff));
	put16(p + 2, (uint16_t)(v >> 16));
}

static uint8_t db[512];

static void
build_db(void)
{
	static const uint16_t ldoc2_levels[] = { 1400, 1600, 1800, 1900 };
	static const uint16_t lcx_levels[] = { 500, 700, 900 };
	uint8_t *entries = db + 144;
	uint8_t *aux = db + 144 + 3 * 24;
	size_t aux_at = 0;

	memset(db, 0, sizeof(db));
	put32(db + 0, 1);                 /* version */
	put32(db + 4, K60_CMD_DB_MAGIC);

	/* slave 0: id 2, entries at +0, aux data at +72, three entries */
	put16(db + 8 + 0, 2);
	put16(db + 8 + 2, 0);
	put16(db + 8 + 4, 72);
	put16(db + 8 + 6, 3);
	put16(db + 8 + 8, 1);

	memcpy(entries + 0, "ldoc2\0\0\0", 8);
	put32(entries + 0 + 16, 0x1c000);
	put16(entries + 0 + 20, (uint16_t)(sizeof(ldoc2_levels)));
	put16(entries + 0 + 22, (uint16_t)aux_at);
	memcpy(aux + aux_at, ldoc2_levels, sizeof(ldoc2_levels));
	aux_at += sizeof(ldoc2_levels);

	memcpy(entries + 24, "lcx.lvl\0", 8);
	put32(entries + 24 + 16, 0x30010);
	put16(entries + 24 + 20, (uint16_t)(sizeof(lcx_levels)));
	put16(entries + 24 + 22, (uint16_t)aux_at);
	memcpy(aux + aux_at, lcx_levels, sizeof(lcx_levels));
	aux_at += sizeof(lcx_levels);

	memcpy(entries + 48, "mx.lvl\0\0", 8);
	put32(entries + 48 + 16, 0x31000);
	put16(entries + 48 + 20, 0);
	put16(entries + 48 + 22, 0);
}

int
main(void)
{
	K60RpmhResource res;
	K60RscLayout l;
	uint32_t index = 0;

	build_db();

	CHECK(k60_cmd_db_find(db, sizeof(db), "ldoc2", &res) == K60RpmhOk);
	CHECK(res.address == 0x1c000);
	CHECK(res.level_count == 4);
	CHECK(res.levels[0] == 1400 && res.levels[2] == 1800 && res.levels[3] == 1900);

	CHECK(k60_cmd_db_find(db, sizeof(db), "lcx.lvl", &res) == K60RpmhOk);
	CHECK(res.address == 0x30010 && res.level_count == 3);

	/* An eight-character name is not truncated: "ldoc2xxx" must not match. */
	CHECK(k60_cmd_db_find(db, sizeof(db), "ldoc2xxx", &res) == K60RpmhMissing);
	CHECK(k60_cmd_db_find(db, sizeof(db), "nope", &res) == K60RpmhMissing);

	CHECK(k60_cmd_db_find(db, sizeof(db), "ldoc2", &res) == K60RpmhOk);
	CHECK(k60_rpmh_level_index(&res, 0, &index) == K60RpmhOk && index == 0);
	CHECK(k60_rpmh_level_index(&res, 1400, &index) == K60RpmhOk && index == 0);
	CHECK(k60_rpmh_level_index(&res, 1800, &index) == K60RpmhOk && index == 2);
	CHECK(k60_rpmh_level_index(&res, 1801, &index) == K60RpmhOk && index == 3);
	/* A level the table cannot express must not look like a success: a
	 * caller would otherwise vote the top corner believing it asked for
	 * 1800 mV (touch agent review, 2026-11-14). */
	CHECK(k60_rpmh_level_index(&res, 9999, &index) == K60RpmhNoLevel);
	CHECK(index == 3);

	/* Bad magic, short buffer, entry counts that overrun the buffer. */
	put32(db + 4, 0xdeadbeef);
	CHECK(k60_cmd_db_find(db, sizeof(db), "ldoc2", &res) == K60RpmhNoDb);
	put32(db + 4, K60_CMD_DB_MAGIC);
	CHECK(k60_cmd_db_find(db, 100, "ldoc2", &res) == K60RpmhNoDb);
	put16(db + 8 + 6, 1000);
	CHECK(k60_cmd_db_find(db, sizeof(db), "ldoc2", &res) == K60RpmhCorrupt);

	/* NULL arguments are rejected without touching memory. */
	CHECK(k60_cmd_db_find(NULL, sizeof(db), "ldoc2", &res) == K60RpmhArgument);
	CHECK(k60_cmd_db_find(db, sizeof(db), NULL, &res) == K60RpmhArgument);
	CHECK(k60_cmd_db_find(db, sizeof(db), "ldoc2", NULL) == K60RpmhArgument);

	/* RSC layouts: major version in bits 23:16 selects the TCS register map. */
	l = k60_rsc_layout(0x00020000);
	CHECK(l.tcs_stride == 672 && l.cmd_stride == 20);
	/* wait_for_cmpl 0x10, control 0x14, status 0x18, cmd_enable 0x1c */
	CHECK(l.wait_for_cmpl == 0x10 && l.control == 0x14 && l.status == 0x18);
	CHECK(l.cmd_enable == 0x1c && l.cmd_msgid == 0x30 && l.cmd_addr == 0x34 && l.cmd_data == 0x38);
	l = k60_rsc_layout(0x00030000);
	CHECK(l.tcs_stride == 672 && l.cmd_stride == 24);
	CHECK(l.control == 0x24 && l.cmd_enable == 0x2c && l.cmd_msgid == 0x34);

	if (failures != 0) {
		printf("TESTS OK 0 cases (%d failure(s))\n", failures);
		return 1;
	}
	printf("TESTS OK 16 cases (0 failure(s))\n");
	return 0;
}
