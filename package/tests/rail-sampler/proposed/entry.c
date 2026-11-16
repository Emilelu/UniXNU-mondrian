/* Offline candidate contract harness. Synthetic buffers only; no hardware access.
 *
 * This file links the candidate observation core (rail_obs.c) directly. It does
 * not link, include, or reproduce the canonical K60PmicRail.c implementation.
 * Every candidate read goes through the counted read32 seam below; the fixture
 * arrays are seeded only before a call and checked byte-for-byte afterwards.
 *
 * Usage:  entry --list
 *         entry <mode-label> <case>
 *         entry <case>
 * One fresh process per case. The candidate has no reset hook, so this harness
 * never runs two independent attempts in one process.
 */
#define _POSIX_C_SOURCE 200809L
#include "rail_obs.h"

#include <errno.h>
#include <pthread.h>
#include <setjmp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define FIX_LCX UINT32_C(0x00030010)
#define FIX_LMX UINT32_C(0x00031000)
#define FIX_MSGID UINT32_C(0x00010108)
#define FIX_STATUS_OK UINT32_C(0x00010100)

static unsigned char db_mem[K60_RAIL_OBS_DB_BYTES];
static unsigned char rsc_mem[K60_RAIL_OBS_RSC_BYTES];
static unsigned char db_snap[K60_RAIL_OBS_DB_BYTES];
static unsigned char rsc_snap[K60_RAIL_OBS_RSC_BYTES];
static int snapshot_taken;

typedef struct {
	int map_calls[2];
	int map_ok[2];
	int unmap_calls[2];
	int read_calls[2];
	int late_rsc;
	int active[2];
	size_t mapped[2];
	size_t short_map[2];
	int fail_map;   /* -1 none, 0 DB, 1 RSC */
	int fail_read;  /* -1 none, 0 DB, 1 RSC */
	int expect_db;
	int expect_rsc;
	int bad_phys;
	int bad_extent;
	int bad_region;
	int bad_read;
	int bad_unmap;
	int bad_token;
	int reentry;
	int did_reentry;
	int nested_rc;
	int hold;
	int did_hold;
	int hold_timeout;
	int inside_map;
	int contender_done;
	int contender_rc;
} Ctl;

static Ctl ctl;
static pthread_mutex_t mu = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t cv = PTHREAD_COND_INITIALIZER;

static K60RailObsPermit permit;
static K60RailObsSpan db_span = { 0, 0x200 };
static K60RailObsSpan rsc_span = { 0x10, 0xff0 };
static K60RailObsResult last_result;
static int last_rc;
static int saw_result;
static K60RailObsGate gate_good = { 1, 1, 1 };

static const char *case_name;
static int failed;
static int checks;
static jmp_buf fail_jmp;

static void fail_at(int line, const char *expr)
{
	printf("CASE %s FAIL line=%d expr=%s\n", case_name, line, expr);
	failed = 1;
	longjmp(fail_jmp, 1);
}

#define CHECK(cond) do { checks++; if (!(cond)) fail_at(__LINE__, #cond); } while (0)

static uint32_t get32(const unsigned char *p)
{
	return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
	    ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static void put16(unsigned char *p, size_t off, uint16_t v)
{
	p[off] = (unsigned char)(v & 0xffu);
	p[off + 1] = (unsigned char)((v >> 8) & 0xffu);
}

static void put32(unsigned char *p, size_t off, uint32_t v)
{
	unsigned i;
	for (i = 0; i < 4; i++)
		p[off + i] = (unsigned char)((v >> (8u * i)) & 0xffu);
}

static void put_name(unsigned char *p, size_t off, const char *s)
{
	unsigned i;
	for (i = 0; i < 8; i++)
		p[off + i] = s[i] ? (unsigned char)s[i] : 0u;
}

static int io_total(void)
{
	return ctl.map_calls[0] + ctl.map_calls[1] +
	    ctl.read_calls[0] + ctl.read_calls[1];
}

static unsigned char *region_base(uint32_t region)
{
	return region == K60_RAIL_OBS_REGION_RSC ? rsc_mem : db_mem;
}

static int cb_map(void *ctx, uint32_t region, uint64_t physical,
    size_t requested, void **token, size_t *mapped);
static int cb_read32(void *ctx, void *token, size_t offset, uint32_t *value);
static void cb_unmap(void *ctx, void *token);

static int cb_map(void *ctx, uint32_t region, uint64_t physical,
    size_t requested, void **token, size_t *mapped)
{
	(void)ctx;
	if (region > 1u) {
		ctl.bad_region = 1;
		return -1;
	}
	ctl.map_calls[region]++;
	if (physical != (region ? K60_RAIL_OBS_RSC_PHYS : K60_RAIL_OBS_DB_PHYS))
		ctl.bad_phys = 1;
	if (requested != (size_t)(region ? ctl.expect_rsc : ctl.expect_db))
		ctl.bad_extent = 1;
	if (ctl.fail_map == (int)region)
		return -1;
	*token = (void *)region_base(region);
	*mapped = requested;
	if (ctl.short_map[region] != 0 && requested > ctl.short_map[region])
		*mapped = ctl.short_map[region];
	ctl.mapped[region] = *mapped;
	ctl.active[region] = 1;
	ctl.map_ok[region]++;
	if (ctl.reentry && region == 0u && !ctl.did_reentry) {
		K60RailObsResult nested;
		ctl.did_reentry = 1;
		memset(&nested, 0xa5, sizeof nested);
		ctl.nested_rc = k60_rail_observe_once(gate_good, &permit,
		    &(K60RailObsIo){ &ctl, cb_map, cb_read32, cb_unmap }, &nested);
	}
	if (ctl.hold && region == 0u && !ctl.did_hold) {
		struct timespec ts;
		int r;
		ctl.did_hold = 1;
		(void)clock_gettime(CLOCK_REALTIME, &ts);
		ts.tv_sec += 5;
		pthread_mutex_lock(&mu);
		ctl.inside_map = 1;
		pthread_cond_broadcast(&cv);
		while (!ctl.contender_done) {
			r = pthread_cond_timedwait(&cv, &mu, &ts);
			if (r == ETIMEDOUT) {
				ctl.hold_timeout = 1;
				break;
			}
		}
		pthread_mutex_unlock(&mu);
	}
	return 0;
}

static int cb_read32(void *ctx, void *token, size_t offset, uint32_t *value)
{
	uint32_t region;
	(void)ctx;
	if (token == (void *)db_mem) region = 0;
	else if (token == (void *)rsc_mem) region = 1;
	else {
		ctl.bad_token = 1;
		return -1;
	}
	if (!ctl.active[region]) {
		ctl.bad_read = 1;
		return -1;
	}
	if ((offset & 3u) != 0u || offset + 4u > ctl.mapped[region]) {
		ctl.bad_read = 1;
		return -1;
	}
	ctl.read_calls[region]++;
	if (region == 1u && offset >= 0x10u)
		ctl.late_rsc++;
	if (ctl.fail_read == (int)region)
		return -1;
	*value = get32(region_base(region) + offset);
	return 0;
}

static void cb_unmap(void *ctx, void *token)
{
	uint32_t region;
	(void)ctx;
	if (token == (void *)db_mem) region = 0;
	else if (token == (void *)rsc_mem) region = 1;
	else {
		ctl.bad_token = 1;
		return;
	}
	if (!ctl.active[region]) {
		ctl.bad_unmap = 1;
		return;
	}
	ctl.active[region] = 0;
	ctl.unmap_calls[region]++;
}

static K60RailObsIo io_seam = { &ctl, cb_map, cb_read32, cb_unmap };

static void reset_ctl(void)
{
	memset(&ctl, 0, sizeof ctl);
	ctl.fail_map = -1;
	ctl.fail_read = -1;
	ctl.expect_db = 0x200;
	ctl.expect_rsc = 0x1000;
}

static void snapshot(void)
{
	memcpy(db_snap, db_mem, sizeof db_snap);
	memcpy(rsc_snap, rsc_mem, sizeof rsc_snap);
	snapshot_taken = 1;
}

static void seed_db_full(void)
{
	memset(db_mem, 0, sizeof db_mem);
	put32(db_mem, 0, 1);
	put32(db_mem, 4, UINT32_C(0x0c0330db));
	put16(db_mem, 8, 1);
	put16(db_mem, 10, 0);
	put16(db_mem, 12, 0);
	put16(db_mem, 14, 2);
	put16(db_mem, 16, 1);
	put_name(db_mem, 0x90, "lcx.lvl");
	put32(db_mem, 0xa0, FIX_LCX);
	put_name(db_mem, 0xa8, "lmx.lvl");
	put32(db_mem, 0xb8, FIX_LMX);
}

static void seed_db_one(void)
{
	seed_db_full();
	put16(db_mem, 14, 1);
}

static size_t tcs_base(unsigned slot)
{
	return 0xd00u + (size_t)slot * 672u;
}

static size_t stride_for(uint32_t version)
{
	return version == UINT32_C(0x00020700) ? 20u : 24u;
}

static size_t status_off_for(uint32_t version)
{
	return version == UINT32_C(0x00020700) ? 0x18u : 0x28u;
}

static size_t enable_off_for(uint32_t version)
{
	return version == UINT32_C(0x00020700) ? 0x1cu : 0x2cu;
}

static size_t msgid_off_for(uint32_t version)
{
	return version == UINT32_C(0x00020700) ? 0x30u : 0x34u;
}

static size_t addr_off_for(uint32_t version)
{
	return version == UINT32_C(0x00020700) ? 0x34u : 0x38u;
}

static size_t data_off_for(uint32_t version)
{
	return version == UINT32_C(0x00020700) ? 0x38u : 0x3cu;
}

static size_t cmd_status_off_for(uint32_t version)
{
	return version == UINT32_C(0x00020700) ? 0x3cu : 0x40u;
}

static void seed_rsc(uint32_t version)
{
	memset(rsc_mem, 0, sizeof rsc_mem);
	put32(rsc_mem, 0, version);
	put32(rsc_mem, 0xc, UINT32_C(0x10002000));
}

static void set_slot(uint32_t version, unsigned slot, uint32_t status,
    uint32_t enable)
{
	size_t base = tcs_base(slot);
	put32(rsc_mem, base + status_off_for(version), status);
	put32(rsc_mem, base + enable_off_for(version), enable);
}

static void set_cmd(uint32_t version, unsigned slot, unsigned command,
    uint32_t address, uint32_t msgid, uint32_t data, uint32_t cmd_status)
{
	size_t at = tcs_base(slot) + (size_t)command * stride_for(version);
	put32(rsc_mem, at + addr_off_for(version), address);
	put32(rsc_mem, at + msgid_off_for(version), msgid);
	put32(rsc_mem, at + data_off_for(version), data);
	put32(rsc_mem, at + cmd_status_off_for(version), cmd_status);
}

static void make_permit(void)
{
	memset(&permit, 0, sizeof permit);
	permit.reviewed = K60_RAIL_OBS_REVIEWED;
	permit.plan_id = UINT32_C(0x12345678);
	permit.logical_drv_id = 2;
	permit.type_count[0] = 1;
	permit.type_count[1] = 0;
	permit.type_count[2] = 1;
	permit.type_count[3] = 0;
	permit.type_count[4] = 0;
	permit.type_order[0] = 2;
	permit.type_order[1] = 0;
	permit.type_order[2] = 1;
	permit.type_order[3] = 3;
	permit.type_order[4] = 4;
	permit.tcs_offset = 0xd00u;
	permit.reviewed_max_slots = 2;
	permit.reviewed_max_commands = 2;
	permit.db_spans = &db_span;
	permit.db_span_count = 1;
	permit.db_span_capacity = 1;
	permit.rsc_spans = &rsc_span;
	permit.rsc_span_count = 1;
	permit.rsc_span_capacity = 1;
	permit.bootstrap[0] = (K60RailObsSpan){ 0, 4 };
	permit.bootstrap[1] = (K60RailObsSpan){ 0x0c, 4 };
	permit.map_extent_db = 0x200;
	permit.map_extent_rsc = 0x1000;
	permit.db_block = 0x200;
	/* Core bounds every command by base+command_block, so the reviewed
	 * block must cover command 1's status word end (0x5c for v3). */
	permit.command_block = 0x5c;
}

static void setup_v2(void)
{
	seed_db_full();
	seed_rsc(UINT32_C(0x00020700));
	set_slot(UINT32_C(0x00020700), 0, 1, 0);
	set_slot(UINT32_C(0x00020700), 1, 1, 0);
	make_permit();
}

static void setup_v3(void)
{
	seed_db_full();
	seed_rsc(UINT32_C(0x00030000));
	set_slot(UINT32_C(0x00030000), 0, 1, 0);
	set_slot(UINT32_C(0x00030000), 1, 1, 0);
	make_permit();
}

static void seed_observed(uint32_t version, unsigned command, uint32_t lcx_data,
    uint32_t lmx_data)
{
	set_slot(version, 0, 1, (uint32_t)1u << command);
	set_slot(version, 1, 1, (uint32_t)1u << command);
	set_cmd(version, 0, command, FIX_LCX, FIX_MSGID, lcx_data, FIX_STATUS_OK);
	set_cmd(version, 1, command, FIX_LMX, FIX_MSGID, lmx_data, FIX_STATUS_OK);
}

static int invoke(K60RailObsGate g)
{
	last_rc = k60_rail_observe_once(g, &permit, &io_seam, &last_result);
	saw_result = 1;
	return last_rc;
}

static const char *outcome_name(uint32_t v);

static void expect_result(uint32_t outcome)
{
	CHECK(last_rc == K60_RAIL_OBS_RETURNED);
	CHECK(last_result.magic == K60_RAIL_OBS_MAGIC);
	CHECK(last_result.schema == K60_RAIL_OBS_SCHEMA);
	CHECK(last_result.bytes == sizeof(K60RailObsResult));
	CHECK(last_result.state == K60_RAIL_OBS_TERMINAL);
	CHECK(last_result.authority == K60_RAIL_OBS_NO_AUTHORITY);
	CHECK(last_result.outcome == outcome);
	CHECK(k60_rail_obs_test_state() == K60_RAIL_OBS_TERMINAL);
}

static void expect_observed(uint32_t qualifiers)
{
	expect_result(K60_RAIL_OBS_OUTCOME_OBSERVED_REQUEST);
	CHECK(last_result.qualifiers == qualifiers);
	CHECK(last_result.coverage_complete == 1);
	CHECK(strcmp(last_result.stop_field, "none") == 0);
}

static void expect_cached_terminal(const K60RailObsPermit *p,
    const K60RailObsResult *want)
{
	int before = io_total();
	int maps0 = ctl.map_calls[0], maps1 = ctl.map_calls[1];
	int reads0 = ctl.read_calls[0], reads1 = ctl.read_calls[1];

	CHECK(k60_rail_observe_once(gate_good, p, &io_seam, &last_result) ==
	    K60_RAIL_OBS_RETURNED);
	CHECK(io_total() == before);
	CHECK(ctl.map_calls[0] == maps0 && ctl.map_calls[1] == maps1);
	CHECK(ctl.read_calls[0] == reads0 && ctl.read_calls[1] == reads1);
	CHECK(memcmp(want, &last_result, sizeof *want) == 0);
}

static void check_refused(const K60RailObsPermit *p)
{
	int before = io_total();
	int rc = k60_rail_observe_once(gate_good, p, &io_seam, &last_result);
	CHECK(rc == K60_RAIL_OBS_BAD_INPUT);
	CHECK(k60_rail_obs_test_state() == K60_RAIL_OBS_UNATTEMPTED);
	CHECK(io_total() == before);
}

static const char *outcome_name(uint32_t v)
{
	switch (v) {
	case K60_RAIL_OBS_OUTCOME_NONE: return "NONE";
	case K60_RAIL_OBS_OUTCOME_INELIGIBLE: return "INELIGIBLE";
	case K60_RAIL_OBS_OUTCOME_MAP_FAILED_DB: return "MAP_FAILED_DB";
	case K60_RAIL_OBS_OUTCOME_MAP_FAILED_RSC: return "MAP_FAILED_RSC";
	case K60_RAIL_OBS_OUTCOME_READ_FAILED: return "READ_FAILED";
	case K60_RAIL_OBS_OUTCOME_DB_CORRUPT: return "DB_CORRUPT";
	case K60_RAIL_OBS_OUTCOME_DB_MISSING: return "DB_MISSING";
	case K60_RAIL_OBS_OUTCOME_PERMISSION_DENIED: return "PERMISSION_DENIED";
	case K60_RAIL_OBS_OUTCOME_UNSUPPORTED_VERSION: return "UNSUPPORTED_VERSION";
	case K60_RAIL_OBS_OUTCOME_CAPS_INVALID: return "CAPS_INVALID";
	case K60_RAIL_OBS_OUTCOME_GEOMETRY_INVALID: return "GEOMETRY_INVALID";
	case K60_RAIL_OBS_OUTCOME_COVERAGE_INCOMPLETE: return "COVERAGE_INCOMPLETE";
	case K60_RAIL_OBS_OUTCOME_NOT_FOUND: return "NOT_FOUND";
	case K60_RAIL_OBS_OUTCOME_MALFORMED_REQUEST: return "MALFORMED_REQUEST";
	case K60_RAIL_OBS_OUTCOME_DUPLICATE_CONFLICT: return "DUPLICATE_CONFLICT";
	case K60_RAIL_OBS_OUTCOME_OBSERVED_REQUEST: return "OBSERVED_REQUEST";
	case K60_RAIL_OBS_OUTCOME_CACHE_CORRUPT: return "CACHE_CORRUPT";
	default: return "UNKNOWN";
	}
}

static void finish_case(void)
{
	int r;
	CHECK(snapshot_taken);
	CHECK(memcmp(db_mem, db_snap, sizeof db_snap) == 0);
	CHECK(memcmp(rsc_mem, rsc_snap, sizeof rsc_snap) == 0);
	CHECK(!ctl.bad_phys);
	CHECK(!ctl.bad_extent);
	CHECK(!ctl.bad_region);
	CHECK(!ctl.bad_read);
	CHECK(!ctl.bad_unmap);
	CHECK(!ctl.bad_token);
	CHECK(!ctl.hold_timeout);
	CHECK(last_rc < 0);
	if (last_rc == K60_RAIL_OBS_RETURNED)
		CHECK(last_result.authority == K60_RAIL_OBS_NO_AUTHORITY);
	for (r = 0; r < 2; r++) {
		CHECK(ctl.active[r] == 0);
		CHECK(ctl.unmap_calls[r] == ctl.map_ok[r]);
	}
}

static void case_gate_ineligible(void)
{
	K60RailObsGate bad[] = {
		{ 0, 1, 1 }, { 2, 1, 1 }, { 1, 0, 1 }, { 1, 1, 0 }, { 1, 1, 2 }
	};
	K60RailObsPermit bad_permit;
	size_t i;
	int before;

	setup_v2();
	seed_observed(UINT32_C(0x00020700), 0, 16, 16);
	snapshot();
	before = io_total();
	for (i = 0; i < sizeof bad / sizeof bad[0]; i++) {
		CHECK(invoke(bad[i]) == K60_RAIL_OBS_INELIGIBLE);
		CHECK(k60_rail_obs_test_state() == K60_RAIL_OBS_UNATTEMPTED);
		CHECK(io_total() == before);
	}
	bad_permit = permit;
	bad_permit.reviewed = 0;
	CHECK(k60_rail_observe_once((K60RailObsGate){ 1, 2, 1 }, &bad_permit,
	    &io_seam, &last_result) == K60_RAIL_OBS_BAD_INPUT);
	CHECK(k60_rail_obs_test_state() == K60_RAIL_OBS_UNATTEMPTED);
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	expect_observed(0);
	CHECK(last_result.record_count == 2);
	CHECK(ctl.map_calls[0] == 1 && ctl.map_calls[1] == 1);
}

static void case_api_null(void)
{
	K60RailObsIo io2;
	int before;

	setup_v2();
	seed_observed(UINT32_C(0x00020700), 0, 16, 16);
	snapshot();
	CHECK(k60_rail_observe_once(gate_good, NULL, &io_seam, &last_result) ==
	    K60_RAIL_OBS_BAD_INPUT);
	CHECK(k60_rail_observe_once(gate_good, &permit, NULL, &last_result) ==
	    K60_RAIL_OBS_BAD_INPUT);
	CHECK(k60_rail_observe_once(gate_good, &permit, &io_seam, NULL) ==
	    K60_RAIL_OBS_BAD_INPUT);
	io2 = io_seam;
	io2.map = NULL;
	CHECK(k60_rail_observe_once(gate_good, &permit, &io2, &last_result) ==
	    K60_RAIL_OBS_BAD_INPUT);
	io2 = io_seam;
	io2.read32 = NULL;
	CHECK(k60_rail_observe_once(gate_good, &permit, &io2, &last_result) ==
	    K60_RAIL_OBS_BAD_INPUT);
	CHECK(k60_rail_obs_test_state() == K60_RAIL_OBS_UNATTEMPTED);
	before = io_total();
	CHECK(before == 0);
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	expect_observed(0);
	CHECK(ctl.map_calls[0] == 1 && ctl.map_calls[1] == 1);
}

static void case_permit_invalid_scalars(void)
{
	K60RailObsPermit p;

	setup_v2();
	seed_observed(UINT32_C(0x00020700), 0, 16, 16);
	snapshot();

	p = permit; p.reviewed = 0; check_refused(&p);
	p = permit; p.plan_id = 0; check_refused(&p);
	p = permit; p.logical_drv_id = 4; check_refused(&p);
	p = permit; p.tcs_offset = 0xd04; check_refused(&p);
	p = permit; p.reviewed_max_slots = 0; check_refused(&p);
	p = permit; p.reviewed_max_slots = 17; check_refused(&p);
	p = permit; p.reviewed_max_commands = 0; check_refused(&p);
	p = permit; p.reviewed_max_commands = 17; check_refused(&p);
	p = permit; p.type_order[1] = 2; check_refused(&p);
	p = permit; p.type_order[3] = 5; check_refused(&p);
	p = permit;
	p.type_count[0] = 0; p.type_count[2] = 0; p.type_count[3] = 1;
	check_refused(&p);
	p = permit; p.type_count[0] = 2; check_refused(&p);
	p = permit; p.reviewed_max_slots = 1; check_refused(&p);
	p = permit; p.bootstrap[0].offset = 4; check_refused(&p);
	p = permit; p.bootstrap[0].bytes = 8; check_refused(&p);
	p = permit; p.bootstrap[1].offset = 0x10; check_refused(&p);
	p = permit; p.bootstrap[1].bytes = 2; check_refused(&p);
	p = permit; p.map_extent_db = 2; check_refused(&p);
	p = permit; p.map_extent_db = K60_RAIL_OBS_DB_BYTES + 4; check_refused(&p);
	p = permit; p.map_extent_rsc = 2; check_refused(&p);
	p = permit; p.map_extent_rsc = K60_RAIL_OBS_RSC_BYTES + 4; check_refused(&p);
	p = permit; p.db_block = 143; check_refused(&p);
	p = permit; p.db_block = 0x201; check_refused(&p);
	p = permit; p.command_block = 3; check_refused(&p);
	p = permit; p.command_block = 0x1001; check_refused(&p);
	p = permit; p.db_spans = NULL; check_refused(&p);
	p = permit; p.rsc_spans = NULL; check_refused(&p);
	CHECK(k60_rail_obs_test_state() == K60_RAIL_OBS_UNATTEMPTED);
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	expect_observed(0);
	CHECK(ctl.map_calls[0] == 1 && ctl.map_calls[1] == 1);
}

static void case_permit_invalid_spans(void)
{
	K60RailObsPermit p;
	K60RailObsSpan spans[2];

	setup_v2();
	seed_observed(UINT32_C(0x00020700), 0, 16, 16);
	snapshot();

	p = permit; p.db_span_count = 0; check_refused(&p);
	p = permit; p.db_span_capacity = 0; check_refused(&p);
	p = permit; p.db_span_capacity = K60_RAIL_OBS_MAX_SPANS + 1;
	check_refused(&p);
	p = permit; p.rsc_span_count = 0; check_refused(&p);
	p = permit; p.rsc_span_capacity = 0; check_refused(&p);
	p = permit; p.rsc_span_capacity = K60_RAIL_OBS_MAX_SPANS + 1;
	check_refused(&p);

	spans[0] = (K60RailObsSpan){ 1, 4 };
	p = permit; p.db_spans = spans; check_refused(&p);

	spans[0] = (K60RailObsSpan){ 0, 0 };
	p = permit; p.db_spans = spans; check_refused(&p);

	spans[0] = (K60RailObsSpan){ 0x1fc, 8 };
	p = permit; p.db_spans = spans; check_refused(&p);

	spans[0] = (K60RailObsSpan){ 0, 0x100 };
	spans[1] = (K60RailObsSpan){ 0x80, 0x80 };
	p = permit; p.db_spans = spans; p.db_span_count = 2;
	p.db_span_capacity = 2; check_refused(&p);

	spans[0] = (K60RailObsSpan){ 0xff8, 0x0c };
	p = permit; p.rsc_spans = spans; check_refused(&p);

	spans[0] = (K60RailObsSpan){ 0x10, 0x30 };
	spans[1] = (K60RailObsSpan){ 0x20, 0x20 };
	p = permit; p.rsc_spans = spans; p.rsc_span_count = 2;
	p.rsc_span_capacity = 2; check_refused(&p);

	CHECK(k60_rail_obs_test_state() == K60_RAIL_OBS_UNATTEMPTED);
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	expect_observed(0);
}

static void case_permit_db_gap(void)
{
	K60RailObsPermit p;
	K60RailObsSpan gap = { 0, 0x10 };
	K60RailObsResult first;

	setup_v2();
	seed_observed(UINT32_C(0x00020700), 0, 16, 16);
	snapshot();
	p = permit;
	p.db_spans = &gap;
	last_rc = k60_rail_observe_once(gate_good, &p, &io_seam, &last_result);
	CHECK(last_rc == K60_RAIL_OBS_RETURNED);
	expect_result(K60_RAIL_OBS_OUTCOME_PERMISSION_DENIED);
	CHECK(last_result.coverage_complete == 0);
	CHECK(ctl.map_calls[0] == 1 && ctl.map_calls[1] == 0);
	CHECK(ctl.unmap_calls[0] == 1 && ctl.unmap_calls[1] == 0);
	first = last_result;
	expect_cached_terminal(&p, &first);
}

static void case_permit_rsc_gap(void)
{
	K60RailObsPermit p;
	K60RailObsSpan gap = { 0x10, 0x20 };
	K60RailObsResult first;

	setup_v2();
	seed_observed(UINT32_C(0x00020700), 0, 16, 16);
	snapshot();
	p = permit;
	p.rsc_spans = &gap;
	last_rc = k60_rail_observe_once(gate_good, &p, &io_seam, &last_result);
	CHECK(last_rc == K60_RAIL_OBS_RETURNED);
	expect_result(K60_RAIL_OBS_OUTCOME_PERMISSION_DENIED);
	CHECK(last_result.coverage_complete == 0);
	CHECK(ctl.map_calls[0] == 1 && ctl.map_calls[1] == 1);
	CHECK(ctl.unmap_calls[0] == 1 && ctl.unmap_calls[1] == 1);
	first = last_result;
	expect_cached_terminal(&p, &first);
}

static void case_db_short_map(void)
{
	K60RailObsResult first;

	setup_v2();
	seed_observed(UINT32_C(0x00020700), 0, 16, 16);
	snapshot();
	ctl.short_map[0] = 0x9c;
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	expect_result(K60_RAIL_OBS_OUTCOME_COVERAGE_INCOMPLETE);
	CHECK(last_result.coverage_complete == 0);
	CHECK(ctl.map_calls[0] == 1 && ctl.map_calls[1] == 0);
	first = last_result;
	expect_cached_terminal(&permit, &first);
}

static void case_rsc_short_map(void)
{
	K60RailObsResult first;

	setup_v2();
	seed_observed(UINT32_C(0x00020700), 0, 16, 16);
	snapshot();
	ctl.short_map[1] = 0xd20;
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	expect_result(K60_RAIL_OBS_OUTCOME_COVERAGE_INCOMPLETE);
	CHECK(last_result.coverage_complete == 0);
	CHECK(ctl.map_calls[0] == 1 && ctl.map_calls[1] == 1);
	CHECK(ctl.unmap_calls[0] == 1 && ctl.unmap_calls[1] == 1);
	first = last_result;
	expect_cached_terminal(&permit, &first);
}

static void case_db_map_fail(void)
{
	K60RailObsResult first;

	setup_v2();
	seed_observed(UINT32_C(0x00020700), 0, 16, 16);
	snapshot();
	ctl.fail_map = 0;
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	expect_result(K60_RAIL_OBS_OUTCOME_MAP_FAILED_DB);
	CHECK(ctl.map_calls[0] == 1 && ctl.map_calls[1] == 0);
	CHECK(ctl.map_ok[0] == 0 && ctl.map_ok[1] == 0);
	first = last_result;
	expect_cached_terminal(&permit, &first);
}

static void case_rsc_map_fail(void)
{
	K60RailObsResult first;

	setup_v2();
	seed_observed(UINT32_C(0x00020700), 0, 16, 16);
	snapshot();
	ctl.fail_map = 1;
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	expect_result(K60_RAIL_OBS_OUTCOME_MAP_FAILED_RSC);
	CHECK(ctl.map_calls[0] == 1 && ctl.map_calls[1] == 1);
	CHECK(ctl.unmap_calls[0] == 1 && ctl.unmap_calls[1] == 0);
	first = last_result;
	expect_cached_terminal(&permit, &first);
}

static void case_db_read_fail(void)
{
	K60RailObsResult first;

	setup_v2();
	seed_observed(UINT32_C(0x00020700), 0, 16, 16);
	snapshot();
	ctl.fail_read = 0;
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	expect_result(K60_RAIL_OBS_OUTCOME_READ_FAILED);
	CHECK(last_result.loads[0] == 0);
	CHECK(ctl.map_calls[0] == 1 && ctl.map_calls[1] == 0);
	first = last_result;
	expect_cached_terminal(&permit, &first);
}

static void case_db_block_table_truncated(void)
{
	K60RailObsPermit p;
	K60RailObsResult first;

	setup_v2();
	seed_observed(UINT32_C(0x00020700), 0, 16, 16);
	snapshot();
	p = permit;
	p.db_block = 0x90;
	last_rc = k60_rail_observe_once(gate_good, &p, &io_seam, &last_result);
	CHECK(last_rc == K60_RAIL_OBS_RETURNED);
	/* 0x90 cannot hold the header plus two 24-byte entries (192 > 144),
	 * so the table is truncated; GEOMETRY_INVALID is NOT established. */
	expect_result(K60_RAIL_OBS_OUTCOME_DB_CORRUPT);
	CHECK(strcmp(last_result.stop_field, "db entries") == 0);
	CHECK(last_result.stop_region == 0);
	CHECK(ctl.map_calls[0] == 1 && ctl.map_calls[1] == 0);
	CHECK(ctl.unmap_calls[0] == 1);
	first = last_result;
	expect_cached_terminal(&p, &first);
}

static void case_command_block_short(void)
{
	K60RailObsPermit p;
	K60RailObsResult first;

	setup_v3();
	seed_observed(UINT32_C(0x00030000), 0, 16, 16);
	snapshot();
	p = permit;
	p.command_block = 0x40;
	last_rc = k60_rail_observe_once(gate_good, &p, &io_seam, &last_result);
	CHECK(last_rc == K60_RAIL_OBS_RETURNED);
	expect_result(K60_RAIL_OBS_OUTCOME_GEOMETRY_INVALID);
	CHECK(ctl.map_calls[0] == 1 && ctl.map_calls[1] == 1);
	CHECK(ctl.unmap_calls[0] == 1 && ctl.unmap_calls[1] == 1);
	first = last_result;
	expect_cached_terminal(&p, &first);
}

static void case_command_block_0x44_geometry(void)
{
	K60RailObsPermit p;
	K60RailObsResult first;

	setup_v3();
	seed_observed(UINT32_C(0x00030000), 0, 16, 16);
	snapshot();
	p = permit;
	/* Observed behaviour, not frozen contract: 0x44 covers command 0 only,
	 * so the walk stops at command 1's address word (0xd00+0x18+0x38). */
	p.command_block = 0x44;
	last_rc = k60_rail_observe_once(gate_good, &p, &io_seam, &last_result);
	CHECK(last_rc == K60_RAIL_OBS_RETURNED);
	expect_result(K60_RAIL_OBS_OUTCOME_GEOMETRY_INVALID);
	CHECK(strcmp(last_result.stop_field, "cmd_address") == 0);
	CHECK(last_result.stop_offset == 0xd50u);
	CHECK(last_result.stop_region == 1);
	CHECK(ctl.map_calls[0] == 1 && ctl.map_calls[1] == 1);
	first = last_result;
	expect_cached_terminal(&p, &first);
}

static void case_observed_parse_ok_truthy(void)
{
	/* Observed deviation from the strict-1 contract: gate_ok() treats
	 * parse_ok as truthy, so 2 is admitted. Recorded as a core defect
	 * (design-doc candidate queue), not as the intended contract. */
	setup_v2();
	seed_observed(UINT32_C(0x00020700), 0, 16, 16);
	snapshot();
	CHECK(invoke((K60RailObsGate){ 1, 2, 1 }) == K60_RAIL_OBS_RETURNED);
	expect_observed(0);
	CHECK(k60_rail_obs_test_state() == K60_RAIL_OBS_TERMINAL);
}

static void case_db_missing(void)
{
	setup_v2();
	seed_db_one();
	snapshot();
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	expect_result(K60_RAIL_OBS_OUTCOME_DB_MISSING);
	CHECK(ctl.map_calls[0] == 1 && ctl.map_calls[1] == 0);
}

static void case_db_corrupt_magic(void)
{
	setup_v2();
	put32(db_mem, 4, 0);
	snapshot();
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	expect_result(K60_RAIL_OBS_OUTCOME_DB_CORRUPT);
}

static void case_db_corrupt_count(void)
{
	setup_v2();
	put16(db_mem, 14, 0xffff);
	snapshot();
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	expect_result(K60_RAIL_OBS_OUTCOME_DB_CORRUPT);
}

static void case_unsupported_version(void)
{
	setup_v2();
	put32(rsc_mem, 0, UINT32_C(0x12340000));
	snapshot();
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	expect_result(K60_RAIL_OBS_OUTCOME_UNSUPPORTED_VERSION);
	CHECK(last_result.loads[1] == 1);
	CHECK(ctl.late_rsc == 0);
	CHECK(ctl.unmap_calls[0] == 1 && ctl.unmap_calls[1] == 1);
}

static void case_caps_max_tcs(void)
{
	setup_v2();
	put32(rsc_mem, 0xc, (UINT32_C(1) << 12) | (UINT32_C(2) << 27));
	snapshot();
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	expect_result(K60_RAIL_OBS_OUTCOME_CAPS_INVALID);
	CHECK(last_result.loads[1] == 2);
}

static void case_caps_ncpt(void)
{
	setup_v2();
	put32(rsc_mem, 0xc, (UINT32_C(2) << 12) | (UINT32_C(0) << 27));
	snapshot();
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	expect_result(K60_RAIL_OBS_OUTCOME_CAPS_INVALID);
	CHECK(last_result.loads[1] == 2);
}

static void case_not_found(void)
{
	setup_v2();
	set_slot(UINT32_C(0x00020700), 0, 1, 0);
	set_slot(UINT32_C(0x00020700), 1, 1, 0);
	snapshot();
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	expect_result(K60_RAIL_OBS_OUTCOME_NOT_FOUND);
	CHECK(last_result.coverage_complete == 1);
	CHECK(last_result.record_count == 0);
	CHECK(last_result.qualifiers == 0);
}

static void case_disabled(void)
{
	setup_v2();
	set_slot(UINT32_C(0x00020700), 0, 1, 0);
	set_slot(UINT32_C(0x00020700), 1, 1, 0);
	set_cmd(UINT32_C(0x00020700), 0, 0, FIX_LCX, FIX_MSGID, 16, FIX_STATUS_OK);
	snapshot();
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	expect_result(K60_RAIL_OBS_OUTCOME_NOT_FOUND);
	CHECK(last_result.record_count == 1);
	CHECK(last_result.qualifiers == K60_RAIL_OBS_Q_DISABLED_RESIDUAL);
	if (last_result.record_count == 1) {
		const K60RailObsRecord *r = &last_result.record[0];
		CHECK((r->flags & K60_RAIL_OBS_REC_DISABLED) != 0);
		CHECK((r->flags & K60_RAIL_OBS_REC_ENABLED) == 0);
		CHECK(r->enable == 0);
		CHECK(r->address == FIX_LCX);
	}
}

static void case_malformed(void)
{
	setup_v2();
	set_slot(UINT32_C(0x00020700), 0, 1, 1);
	set_slot(UINT32_C(0x00020700), 1, 1, 0);
	set_cmd(UINT32_C(0x00020700), 0, 0, FIX_LCX, UINT32_C(0x00010000),
	    16, FIX_STATUS_OK);
	snapshot();
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	expect_result(K60_RAIL_OBS_OUTCOME_MALFORMED_REQUEST);
	CHECK(last_result.record_count == 1);
	CHECK(last_result.qualifiers == K60_RAIL_OBS_Q_MALFORMED);
	if (last_result.record_count == 1) {
		const K60RailObsRecord *r = &last_result.record[0];
		CHECK((r->flags & K60_RAIL_OBS_REC_MALFORMED) != 0);
		CHECK((r->flags & K60_RAIL_OBS_REC_FORMAT_OK) == 0);
		CHECK(r->enable == 1);
	}
}

static void case_tcs_busy(void)
{
	setup_v2();
	seed_observed(UINT32_C(0x00020700), 0, 16, 16);
	set_slot(UINT32_C(0x00020700), 0, 0, 1);
	snapshot();
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	expect_observed(K60_RAIL_OBS_Q_TCS_BUSY);
	CHECK(last_result.record_count == 2);
	if (last_result.record_count == 2) {
		CHECK((last_result.record[0].flags & K60_RAIL_OBS_REC_TCS_BUSY) != 0);
		CHECK((last_result.record[1].flags & K60_RAIL_OBS_REC_TCS_BUSY) == 0);
	}
}

static void case_not_issued(void)
{
	setup_v2();
	seed_observed(UINT32_C(0x00020700), 0, 16, 16);
	set_cmd(UINT32_C(0x00020700), 0, 0, FIX_LCX, FIX_MSGID, 16,
	    UINT32_C(0x00010000));
	snapshot();
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	expect_observed(K60_RAIL_OBS_Q_NOT_ISSUED);
	CHECK(last_result.record_count == 2);
	if (last_result.record_count == 2) {
		CHECK((last_result.record[0].flags & K60_RAIL_OBS_REC_ISSUED) == 0);
		CHECK((last_result.record[0].flags & K60_RAIL_OBS_REC_COMPLETE) != 0);
	}
}

static void case_incomplete(void)
{
	setup_v2();
	seed_observed(UINT32_C(0x00020700), 0, 16, 16);
	set_cmd(UINT32_C(0x00020700), 0, 0, FIX_LCX, FIX_MSGID, 16,
	    UINT32_C(0x00000100));
	snapshot();
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	expect_observed(K60_RAIL_OBS_Q_INCOMPLETE);
	CHECK(last_result.record_count == 2);
	if (last_result.record_count == 2) {
		CHECK((last_result.record[0].flags & K60_RAIL_OBS_REC_ISSUED) != 0);
		CHECK((last_result.record[0].flags & K60_RAIL_OBS_REC_COMPLETE) == 0);
	}
}

static void seed_duplicate(int conflict)
{
	setup_v2();
	set_slot(UINT32_C(0x00020700), 0, 1, 3);
	set_slot(UINT32_C(0x00020700), 1, 1, 1);
	set_cmd(UINT32_C(0x00020700), 0, 0, FIX_LCX, FIX_MSGID, 16, FIX_STATUS_OK);
	set_cmd(UINT32_C(0x00020700), 0, 1, FIX_LCX, FIX_MSGID,
	    conflict ? 8u : 16u, FIX_STATUS_OK);
	set_cmd(UINT32_C(0x00020700), 1, 0, FIX_LMX, FIX_MSGID, 16, FIX_STATUS_OK);
}

static void case_duplicate_identical(void)
{
	seed_duplicate(0);
	snapshot();
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	expect_observed(K60_RAIL_OBS_Q_DUPLICATE_IDENTICAL);
	CHECK(last_result.record_count == 3);
	if (last_result.record_count == 3) {
		CHECK(last_result.record[0].rail == 0);
		CHECK(last_result.record[1].rail == 0);
		CHECK(last_result.record[0].data == 16);
		CHECK(last_result.record[1].data == 16);
	}
}

static void case_duplicate_conflict(void)
{
	seed_duplicate(1);
	snapshot();
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	expect_result(K60_RAIL_OBS_OUTCOME_DUPLICATE_CONFLICT);
	CHECK(last_result.qualifiers == K60_RAIL_OBS_Q_DUPLICATE_CONFLICT);
	CHECK(last_result.record_count == 3);
	if (last_result.record_count == 3)
		CHECK(last_result.record[1].data == 8);
}

static void case_observed_v2_command1(void)
{
	setup_v2();
	seed_observed(UINT32_C(0x00020700), 1, 16, 16);
	snapshot();
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	expect_observed(0);
	CHECK(last_result.version == UINT32_C(0x00020700));
	CHECK(last_result.caps == UINT32_C(0x10002000));
	CHECK(last_result.resource[0] == FIX_LCX);
	CHECK(last_result.resource[1] == FIX_LMX);
	CHECK(last_result.slots == 2 && last_result.commands == 2);
	CHECK(last_result.record_count == 2);
	CHECK(last_result.maps[0] == 1 && last_result.maps[1] == 1);
	CHECK(last_result.loads[0] == 14);
	CHECK(last_result.loads[1] == 16);
	if (last_result.record_count == 2) {
		const K60RailObsRecord *a = &last_result.record[0];
		const K60RailObsRecord *b = &last_result.record[1];
		CHECK(a->rail == 0 && a->slot == 0 && a->command == 1);
		CHECK(a->type == 2 && a->enable == 2);
		CHECK(a->msgid == FIX_MSGID && a->tcs_status == 1);
		CHECK(a->cmd_status == FIX_STATUS_OK);
		CHECK(a->address == FIX_LCX && a->data == 16);
		CHECK((a->flags & (K60_RAIL_OBS_REC_ENABLED |
		    K60_RAIL_OBS_REC_FORMAT_OK | K60_RAIL_OBS_REC_RESPONSE |
		    K60_RAIL_OBS_REC_ISSUED | K60_RAIL_OBS_REC_COMPLETE)) ==
		    (K60_RAIL_OBS_REC_ENABLED | K60_RAIL_OBS_REC_FORMAT_OK |
		    K60_RAIL_OBS_REC_RESPONSE | K60_RAIL_OBS_REC_ISSUED |
		    K60_RAIL_OBS_REC_COMPLETE));
		CHECK(b->rail == 1 && b->slot == 1 && b->command == 1);
		CHECK(b->type == 0 && b->enable == 2);
		CHECK(b->address == FIX_LMX && b->data == 16);
	}
}

static void case_observed_v3_command1(void)
{
	setup_v3();
	seed_observed(UINT32_C(0x00030000), 1, 16, 16);
	snapshot();
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	expect_observed(0);
	CHECK(last_result.version == UINT32_C(0x00030000));
	CHECK(last_result.caps == UINT32_C(0x10002000));
	CHECK(last_result.record_count == 2);
	CHECK(last_result.maps[0] == 1 && last_result.maps[1] == 1);
	CHECK(last_result.loads[0] == 14);
	CHECK(last_result.loads[1] == 16);
	if (last_result.record_count == 2) {
		CHECK(last_result.record[0].command == 1);
		CHECK(last_result.record[0].type == 2);
		CHECK(last_result.record[0].address == FIX_LCX);
		CHECK(last_result.record[1].command == 1);
		CHECK(last_result.record[1].type == 0);
		CHECK(last_result.record[1].address == FIX_LMX);
	}
}

static void case_reentry_busy(void)
{
	setup_v2();
	seed_observed(UINT32_C(0x00020700), 0, 16, 16);
	snapshot();
	ctl.reentry = 1;
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	expect_observed(0);
	CHECK(ctl.did_reentry == 1);
	CHECK(ctl.nested_rc == K60_RAIL_OBS_BUSY);
	CHECK(ctl.map_calls[0] == 1 && ctl.map_calls[1] == 1);
}

static void *contender_main(void *arg)
{
	struct timespec ts;
	int r;
	K60RailObsResult nested;
	(void)arg;
	(void)clock_gettime(CLOCK_REALTIME, &ts);
	ts.tv_sec += 5;
	pthread_mutex_lock(&mu);
	while (!ctl.inside_map) {
		r = pthread_cond_timedwait(&cv, &mu, &ts);
		if (r == ETIMEDOUT) {
			ctl.hold_timeout = 1;
			pthread_mutex_unlock(&mu);
			return NULL;
		}
	}
	pthread_mutex_unlock(&mu);
	memset(&nested, 0xa5, sizeof nested);
	ctl.contender_rc = k60_rail_observe_once(gate_good, &permit,
	    &io_seam, &nested);
	pthread_mutex_lock(&mu);
	ctl.contender_done = 1;
	pthread_cond_broadcast(&cv);
	pthread_mutex_unlock(&mu);
	return NULL;
}

static void case_concurrent_busy(void)
{
	pthread_t th;
	setup_v2();
	seed_observed(UINT32_C(0x00020700), 0, 16, 16);
	snapshot();
	ctl.hold = 1;
	CHECK(pthread_create(&th, NULL, contender_main, NULL) == 0);
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	CHECK(pthread_join(th, NULL) == 0);
	expect_observed(0);
	CHECK(!ctl.hold_timeout);
	CHECK(ctl.contender_rc == K60_RAIL_OBS_BUSY);
	CHECK(ctl.map_calls[0] == 1 && ctl.map_calls[1] == 1);
}

static void case_cache_copy(void)
{
	K60RailObsResult first;

	setup_v2();
	seed_observed(UINT32_C(0x00020700), 0, 16, 16);
	snapshot();
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	expect_observed(0);
	first = last_result;
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	CHECK(memcmp(&first, &last_result, sizeof first) == 0);
	CHECK(last_result.maps[0] == 1 && last_result.loads[0] == 14);
	last_result.record[0].flags = UINT32_C(0xffffffff);
	last_result.outcome = 0;
	last_result.magic = 0;
	last_result.record_count = 0;
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	CHECK(memcmp(&first, &last_result, sizeof first) == 0);
	CHECK(ctl.map_calls[0] == 1 && ctl.map_calls[1] == 1);
}

static void case_terminal_gate(void)
{
	K60RailObsResult first;
	K60RailObsGate off = { 0, 1, 1 };
	int before;

	setup_v2();
	seed_observed(UINT32_C(0x00020700), 0, 16, 16);
	snapshot();
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	first = last_result;
	before = io_total();
	CHECK(invoke(off) == K60_RAIL_OBS_INELIGIBLE);
	CHECK(io_total() == before);
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	CHECK(memcmp(&first, &last_result, sizeof first) == 0);
	CHECK(ctl.map_calls[0] == 1 && ctl.map_calls[1] == 1);
}

static void case_plan_mismatch(void)
{
	K60RailObsPermit p;
	K60RailObsResult first;
	int before;

	setup_v2();
	seed_observed(UINT32_C(0x00020700), 0, 16, 16);
	snapshot();
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	first = last_result;
	p = permit;
	p.plan_id++;
	before = io_total();
	CHECK(k60_rail_observe_once(gate_good, &p, &io_seam, &last_result) ==
	    K60_RAIL_OBS_PLAN_MISMATCH);
	CHECK(io_total() == before);
	CHECK(k60_rail_obs_test_state() == K60_RAIL_OBS_TERMINAL);
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	CHECK(memcmp(&first, &last_result, sizeof first) == 0);
}

static void corrupt_case(unsigned kind)
{
	K60RailObsResult first;
	int before;

	setup_v2();
	seed_observed(UINT32_C(0x00020700), 0, 16, 16);
	snapshot();
	CHECK(invoke(gate_good) == K60_RAIL_OBS_RETURNED);
	first = last_result;
	k60_rail_obs_test_corrupt(kind);
	before = io_total();
	CHECK(invoke(gate_good) == K60_RAIL_OBS_CACHE_CORRUPT);
	CHECK(io_total() == before);
	CHECK(k60_rail_obs_test_state() == K60_RAIL_OBS_TERMINAL);
	(void)first;
	CHECK(ctl.map_calls[0] == 1 && ctl.map_calls[1] == 1);
}

static void case_corrupt_magic(void) { corrupt_case(0); }
static void case_corrupt_checksum(void) { corrupt_case(1); }
static void case_corrupt_record_count(void) { corrupt_case(2); }

typedef struct {
	const char *name;
	void (*fn)(void);
} Case;

static const Case cases[] = {
	{ "gate-ineligible", case_gate_ineligible },
	{ "api-null", case_api_null },
	{ "permit-invalid-scalars", case_permit_invalid_scalars },
	{ "permit-invalid-spans", case_permit_invalid_spans },
	{ "permit-db-gap", case_permit_db_gap },
	{ "permit-rsc-gap", case_permit_rsc_gap },
	{ "db-short-map", case_db_short_map },
	{ "rsc-short-map", case_rsc_short_map },
	{ "db-map-fail", case_db_map_fail },
	{ "rsc-map-fail", case_rsc_map_fail },
	{ "db-read-fail", case_db_read_fail },
	{ "db-block-table-truncated", case_db_block_table_truncated },
	{ "command-block-short", case_command_block_short },
	{ "command-block-0x44-geometry", case_command_block_0x44_geometry },
	{ "observed-parse-ok-truthy", case_observed_parse_ok_truthy },
	{ "db-missing", case_db_missing },
	{ "db-corrupt-magic", case_db_corrupt_magic },
	{ "db-corrupt-count", case_db_corrupt_count },
	{ "unsupported-version", case_unsupported_version },
	{ "caps-max-tcs", case_caps_max_tcs },
	{ "caps-ncpt", case_caps_ncpt },
	{ "not-found", case_not_found },
	{ "disabled", case_disabled },
	{ "malformed", case_malformed },
	{ "tcs-busy", case_tcs_busy },
	{ "not-issued", case_not_issued },
	{ "incomplete", case_incomplete },
	{ "duplicate-identical", case_duplicate_identical },
	{ "duplicate-conflict", case_duplicate_conflict },
	{ "observed-v2-command1", case_observed_v2_command1 },
	{ "observed-v3-command1", case_observed_v3_command1 },
	{ "reentry-busy", case_reentry_busy },
	{ "concurrent-busy", case_concurrent_busy },
	{ "cache-copy", case_cache_copy },
	{ "terminal-gate", case_terminal_gate },
	{ "plan-mismatch", case_plan_mismatch },
	{ "corrupt-magic", case_corrupt_magic },
	{ "corrupt-checksum", case_corrupt_checksum },
	{ "corrupt-record-count", case_corrupt_record_count }
};

static void list_cases(void)
{
	size_t i;
	for (i = 0; i < sizeof cases / sizeof cases[0]; i++)
		printf("%s\n", cases[i].name);
}

static int run_case(const Case *c)
{
	case_name = c->name;
	failed = 0;
	checks = 0;
	saw_result = 0;
	last_rc = 0;
	snapshot_taken = 0;
	memset(&last_result, 0xa5, sizeof last_result);
	reset_ctl();
	if (setjmp(fail_jmp) == 0) {
		c->fn();
		finish_case();
	}
	if (failed) {
		printf("RESULT %s FAIL\n", c->name);
		printf("SUMMARY total=1 pass=0 fail=1\n");
		return 1;
	}
	if (last_rc == K60_RAIL_OBS_RETURNED)
		printf("CASE %s PASS rc=%d outcome=%u(%s) qualifiers=0x%x "
		    "records=%u maps=%u/%u loads=%u/%u\n", c->name, last_rc,
		    (unsigned)last_result.outcome,
		    outcome_name(last_result.outcome),
		    (unsigned)last_result.qualifiers,
		    (unsigned)last_result.record_count,
		    (unsigned)last_result.maps[0], (unsigned)last_result.maps[1],
		    (unsigned)last_result.loads[0], (unsigned)last_result.loads[1]);
	else
		printf("CASE %s PASS rc=%d outcome=n/a records=n/a maps=%u/%u "
		    "loads=%u/%u\n", c->name, last_rc,
		    (unsigned)ctl.map_calls[0], (unsigned)ctl.map_calls[1],
		    (unsigned)ctl.read_calls[0], (unsigned)ctl.read_calls[1]);
	printf("SUMMARY total=1 pass=1 fail=0\n");
	return 0;
}

int main(int argc, char **argv)
{
	size_t i;
	const char *want = NULL;

	if (argc == 2 && strcmp(argv[1], "--list") == 0) {
		list_cases();
		return 0;
	}
	if (argc == 2)
		want = argv[1];
	else if (argc == 3)
		want = argv[2];
	else {
		fprintf(stderr, "usage: %s --list | %s <mode-label> <case> | %s <case>\n",
		    argv[0], argv[0], argv[0]);
		return 2;
	}
	for (i = 0; i < sizeof cases / sizeof cases[0]; i++) {
		if (strcmp(want, cases[i].name) == 0)
			return run_case(&cases[i]);
	}
	fprintf(stderr, "unknown case: %s\n", want);
	return 2;
}
