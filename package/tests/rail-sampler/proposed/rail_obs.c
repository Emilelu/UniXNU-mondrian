/* Offline candidate implementation. NOT production, NOT linked, no hardware.
 * Build guard keeps a kernel compilation from ever absorbing this file.
 */
#ifdef KERNEL
#error "candidate observation core is host-only; do not build into the kernel"
#endif
#include "rail_obs.h"
#include <stdatomic.h>
#include <stddef.h>
#include <string.h>

#define DB_MAGIC 0x0c0330dbu
#define V2 0x20700u
#define V3 0x30000u
#define DB_HEADER 144u
#define DB_SLAVES 8u
#define DB_ENTRY 24u
#define TCS_STRIDE 672u
#define DB_SPANS_MAX 8u

enum { C_NONE = 0, C_PERMISSION, C_COVERAGE, C_READ, C_GEOMETRY,
       C_DB_CORRUPT, C_CAPACITY };

typedef struct {
	const K60RailObsPermit *permit;
	const K60RailObsIo *io;
	K60RailObsResult *res;
	void *db_token, *rsc_token;
	size_t db_mapped, rsc_mapped;
	uint64_t cmd_stride, status_off, enable_off, msgid_off, addr_off;
	uint64_t data_off, cmd_status_off;
	uint32_t slot_type[K60_RAIL_OBS_MAX_SLOTS];
	int stop;
	uint32_t stop_region;
	uint64_t stop_at;
	const char *stop_field;
} Pass;

static _Atomic unsigned attempt;
static K60RailObsResult terminal;

_Static_assert(offsetof(K60RailObsResult, checksum) +
    sizeof(uint64_t) == sizeof(K60RailObsResult), "checksum must be last");

static uint64_t digest_mix(uint64_t h, uint64_t v)
{
	unsigned i;
	for (i = 0; i < 8; i++) {
		h ^= (v >> (8u * i)) & 0xffu;
		h *= UINT64_C(0x100000001b3);
	}
	return h;
}

static uint32_t plan_digest(const K60RailObsPermit *p)
{
	uint64_t h = UINT64_C(0xcbf29ce484222325);
	size_t i;
	h = digest_mix(h, p->reviewed);
	h = digest_mix(h, p->plan_id);
	h = digest_mix(h, p->logical_drv_id);
	h = digest_mix(h, p->tcs_offset);
	h = digest_mix(h, p->reviewed_max_slots);
	h = digest_mix(h, p->reviewed_max_commands);
	h = digest_mix(h, p->map_extent_db);
	h = digest_mix(h, p->map_extent_rsc);
	h = digest_mix(h, p->db_block);
	h = digest_mix(h, p->command_block);
	h = digest_mix(h, p->bootstrap[0].offset);
	h = digest_mix(h, p->bootstrap[0].bytes);
	h = digest_mix(h, p->bootstrap[1].offset);
	h = digest_mix(h, p->bootstrap[1].bytes);
	for (i = 0; i < 5; i++) h = digest_mix(h, p->type_count[i]);
	for (i = 0; i < 5; i++) h = digest_mix(h, p->type_order[i]);
	for (i = 0; i < p->db_span_count; i++) {
		h = digest_mix(h, p->db_spans[i].offset);
		h = digest_mix(h, p->db_spans[i].bytes);
	}
	for (i = 0; i < p->rsc_span_count; i++) {
		h = digest_mix(h, p->rsc_spans[i].offset);
		h = digest_mix(h, p->rsc_spans[i].bytes);
	}
	return h;
}

static uint64_t checksum_of(const K60RailObsResult *r)
{
	K60RailObsResult copy = *r;
	const unsigned char *b;
	size_t i, n = offsetof(K60RailObsResult, checksum);
	uint64_t h = UINT64_C(0xcbf29ce484222325);
	copy.checksum = 0;
	b = (const unsigned char *)&copy;
	for (i = 0; i < n; i++) {
		h ^= b[i];
		h *= UINT64_C(0x100000001b3);
	}
	return h;
}

static int span_holds(const K60RailObsSpan *s, uint64_t offset, uint64_t bytes)
{
	uint64_t delta;
	if (s->bytes == 0 || offset < s->offset) return 0;
	delta = offset - s->offset;
	if (delta > s->bytes || bytes > s->bytes - delta) return 0;
	return 1;
}

static int spans_valid(const K60RailObsSpan *list, size_t count, size_t cap,
    uint32_t extent)
{
	size_t i, j;
	if (count == 0 || count > cap || cap > K60_RAIL_OBS_MAX_SPANS) return 0;
	if (list == NULL) return 0;
	for (i = 0; i < count; i++) {
		const K60RailObsSpan *a = &list[i];
		if (a->bytes == 0 || (a->offset & 3u) != 0 || (a->bytes & 3u) != 0)
			return 0;
		if (a->offset > extent || a->bytes > extent - a->offset) return 0;
		for (j = 0; j < i; j++) {
			const K60RailObsSpan *b = &list[j];
			if (a->offset < b->offset + b->bytes &&
			    b->offset < a->offset + a->bytes) return 0;
		}
	}
	return 1;
}

static int permit_valid(const K60RailObsPermit *p)
{
	uint32_t sum = 0, seen = 0, i;
	if (p == NULL || p->reviewed != K60_RAIL_OBS_REVIEWED || p->plan_id == 0)
		return 0;
	if (p->logical_drv_id > 3u) return 0;
	if (p->tcs_offset != 0xd00u) return 0;
	if (p->reviewed_max_slots == 0 ||
	    p->reviewed_max_slots > K60_RAIL_OBS_MAX_SLOTS) return 0;
	if (p->reviewed_max_commands == 0 ||
	    p->reviewed_max_commands > K60_RAIL_OBS_MAX_COMMANDS) return 0;
	if (p->bootstrap[0].offset != 0 || p->bootstrap[0].bytes != 4) return 0;
	if (p->bootstrap[1].offset != 0x0cu || p->bootstrap[1].bytes != 4) return 0;
	if (p->map_extent_db < 4 || p->map_extent_db > K60_RAIL_OBS_DB_BYTES)
		return 0;
	if (p->map_extent_rsc < 4 || p->map_extent_rsc > K60_RAIL_OBS_RSC_BYTES)
		return 0;
	if (p->db_block < DB_HEADER || p->db_block > p->map_extent_db) return 0;
	if (p->command_block < 4 || p->command_block > p->map_extent_rsc) return 0;
	for (i = 0; i < 5; i++) {
		if (p->type_order[i] > 4 || (seen & (1u << p->type_order[i])))
			return 0;
		seen |= 1u << p->type_order[i];
		sum += p->type_count[i];
	}
	if (sum == 0 || sum > p->reviewed_max_slots) return 0;
	if (p->type_count[3] != 0) return 0;
	if (!spans_valid(p->db_spans, p->db_span_count, p->db_span_capacity,
	    p->map_extent_db)) return 0;
	if (!spans_valid(p->rsc_spans, p->rsc_span_count, p->rsc_span_capacity,
	    p->map_extent_rsc)) return 0;
	return 1;
}

static int gate_ok(K60RailObsGate g)
{
	return g.data_mounted == 1 && g.parse_ok != 0 && g.parsed_value == 1;
}

static void stop(Pass *p, int why, uint32_t region, const char *field,
    uint64_t at)
{
	if (p->stop == C_NONE) {
		p->stop = why;
		p->stop_region = region;
		p->stop_field = field;
		p->stop_at = at;
	}
}

static int rsc_permitted(const Pass *p, int bootstrap, uint64_t off, uint64_t bytes)
{
	const K60RailObsPermit *q = p->permit;
	size_t i;
	if (bootstrap) {
		return span_holds(&q->bootstrap[0], off, bytes) ||
		    span_holds(&q->bootstrap[1], off, bytes);
	}
	for (i = 0; i < q->rsc_span_count; i++)
		if (span_holds(&q->rsc_spans[i], off, bytes)) return 1;
	return 0;
}

static int db_permitted(const Pass *p, uint64_t off, uint64_t bytes)
{
	size_t i;
	for (i = 0; i < p->permit->db_span_count; i++)
		if (span_holds(&p->permit->db_spans[i], off, bytes)) return 1;
	return 0;
}

static int read_field(Pass *p, int region, int bootstrap, uint64_t limit,
    uint64_t off, const char *field, uint32_t *value)
{
	size_t mapped = region ? p->rsc_mapped : p->db_mapped;
	void *token = region ? p->rsc_token : p->db_token;
	uint32_t v;
	if ((off & 3u) != 0 || off > UINT64_MAX - 4u) {
		stop(p, C_GEOMETRY, (uint32_t)region, field, off);
		return -1;
	}
	if (off + 4u > limit) {
		stop(p, C_GEOMETRY, (uint32_t)region, field, off);
		return -1;
	}
	if (off + 4u > (uint64_t)mapped) {
		stop(p, C_COVERAGE, (uint32_t)region, field, off);
		return -1;
	}
	if (region ? !rsc_permitted(p, bootstrap, off, 4u) :
	    !db_permitted(p, off, 4u)) {
		stop(p, C_PERMISSION, (uint32_t)region, field, off);
		return -1;
	}
	if (p->io->read32(p->io->context, token, (size_t)off, &v) != 0) {
		stop(p, C_READ, (uint32_t)region, field, off);
		return -1;
	}
	p->res->loads[region]++;
	*value = v;
	return 0;
}

static void unmap(Pass *p, int region)
{
	void *token = region ? p->rsc_token : p->db_token;
	if (token != NULL && p->io->unmap != NULL) p->io->unmap(p->io->context, token);
}

static int map(Pass *p, int region)
{
	uint64_t phys = region ? K60_RAIL_OBS_RSC_PHYS : K60_RAIL_OBS_DB_PHYS;
	size_t extent = region ? p->permit->map_extent_rsc : p->permit->map_extent_db;
	void **token = region ? &p->rsc_token : &p->db_token;
	size_t *mapped = region ? &p->rsc_mapped : &p->db_mapped;
	size_t got = 0;
	p->res->maps[region]++;
	if (p->io->map(p->io->context, (uint32_t)region, phys, extent, token,
	    &got) != 0 || *token == NULL || got == 0) return -1;
	*mapped = got;
	return 0;
}

static uint32_t le16(uint32_t w, unsigned shift)
{
	return (w >> shift) & 0xffffu;
}

static int name_match(uint32_t a, uint32_t b, const char *want)
{
	unsigned char got[8];
	unsigned i;
	for (i = 0; i < 4; i++) {
		got[i] = (unsigned char)(a >> (8u * i));
		got[i + 4] = (unsigned char)(b >> (8u * i));
	}
	for (i = 0; i < 8; i++) {
		if (want[i] == '\0') return got[i] == 0;
		if (got[i] != (unsigned char)want[i]) return 0;
	}
	return 1;
}

static int db_find(Pass *p, const char *name, uint32_t *address)
{
	uint32_t magic, w0, w1, id, heads, count, e;
	if (read_field(p, 0, 0, p->permit->db_block, 4, "db magic", &magic) != 0)
		return -1;
	if (magic != DB_MAGIC) {
		stop(p, C_DB_CORRUPT, 0, "db magic", 4);
		return -1;
	}
	for (e = 0; e < DB_SLAVES; e++) {
		uint64_t base = 8u + 16u * e;
		uint64_t start, end;
		uint32_t i;
		if (read_field(p, 0, 0, p->permit->db_block, base, "db slave",
		    &w0) != 0) return -1;
		if (read_field(p, 0, 0, p->permit->db_block, base + 4u,
		    "db slave", &w1) != 0) return -1;
		id = le16(w0, 0);
		if (id == 0) break;
		heads = le16(w0, 16);
		count = le16(w1, 16);
		start = DB_HEADER + heads;
		end = start + (uint64_t)count * DB_ENTRY;
		if (end < start || end > p->permit->db_block) {
			stop(p, C_DB_CORRUPT, 0, "db entries", start);
			return -1;
		}
		if (end > p->db_mapped) {
			stop(p, C_COVERAGE, 0, "db entries", start);
			return -1;
		}
		for (i = 0; i < count; i++) {
			uint64_t at = start + (uint64_t)i * DB_ENTRY;
			uint32_t a, b;
			if (read_field(p, 0, 0, p->permit->db_block, at,
			    "db name", &a) != 0) return -1;
			if (read_field(p, 0, 0, p->permit->db_block, at + 4u,
			    "db name", &b) != 0) return -1;
			if (!name_match(a, b, name)) continue;
			if (read_field(p, 0, 0, p->permit->db_block, at + 16u,
			    "db address", address) != 0) return -1;
			if (*address == 0) {
				stop(p, C_DB_CORRUPT, 0, "db address", at + 16u);
				return -1;
			}
			return 0;
		}
	}
	stop(p, C_DB_CORRUPT, 0, "db missing", 0);
	return -1;
}

static int layout(Pass *p, uint32_t version)
{
	if (version == V2) {
		p->cmd_stride = 20; p->status_off = 0x18; p->enable_off = 0x1c;
		p->msgid_off = 0x30; p->addr_off = 0x34; p->data_off = 0x38;
		p->cmd_status_off = 0x3c;
		return 0;
	}
	if (version == V3) {
		p->cmd_stride = 24; p->status_off = 0x28; p->enable_off = 0x2c;
		p->msgid_off = 0x34; p->addr_off = 0x38; p->data_off = 0x3c;
		p->cmd_status_off = 0x40;
		return 0;
	}
	return -1;
}

static void finish_record(K60RailObsRecord *r)
{
	uint32_t len = r->msgid & 0xffu;
	if (r->tcs_status == 0) r->flags |= K60_RAIL_OBS_REC_TCS_BUSY;
	if (!(r->flags & K60_RAIL_OBS_REC_ENABLED)) {
		r->flags |= K60_RAIL_OBS_REC_DISABLED;
		return;
	}
	if (len == 0 || len > 8u) {
		r->flags |= K60_RAIL_OBS_REC_MALFORMED;
		return;
	}
	r->flags |= K60_RAIL_OBS_REC_FORMAT_OK;
	if (r->msgid & 0x100u) r->flags |= K60_RAIL_OBS_REC_RESPONSE;
	if (r->cmd_status & 0x100u) r->flags |= K60_RAIL_OBS_REC_ISSUED;
	if (r->cmd_status & 0x10000u) r->flags |= K60_RAIL_OBS_REC_COMPLETE;
}

static int scan(Pass *p, uint32_t slots, uint32_t commands)
{
	uint32_t slot, command;
	for (slot = 0; slot < slots; slot++) {
		uint64_t base = (uint64_t)p->permit->tcs_offset +
		    (uint64_t)slot * TCS_STRIDE;
		uint32_t status, enable;
		if (read_field(p, 1, 0, base + p->permit->command_block,
		    base + p->status_off, "tcs_status", &status) != 0) return -1;
		if (read_field(p, 1, 0, base + p->permit->command_block,
		    base + p->enable_off, "enable", &enable) != 0) return -1;
		for (command = 0; command < commands; command++) {
			uint64_t at = base + (uint64_t)command * p->cmd_stride;
			uint32_t address, msgid, data, cmd_status, rail;
			K60RailObsRecord *r;
			if (read_field(p, 1, 0, base + p->permit->command_block,
			    at + p->addr_off, "cmd_address", &address) != 0)
				return -1;
			if (address == p->res->resource[0]) rail = 0;
			else if (address == p->res->resource[1]) rail = 1;
			else continue;
			if (read_field(p, 1, 0, base + p->permit->command_block,
			    at + p->msgid_off, "cmd_msgid", &msgid) != 0) return -1;
			if (read_field(p, 1, 0, base + p->permit->command_block,
			    at + p->data_off, "cmd_data", &data) != 0) return -1;
			if (read_field(p, 1, 0, base + p->permit->command_block,
			    at + p->cmd_status_off, "cmd_status", &cmd_status) != 0)
				return -1;
			if (p->res->record_count >= K60_RAIL_OBS_MAX_RECORDS) {
				stop(p, C_CAPACITY, 1, "record capacity", at);
				return -1;
			}
			r = &p->res->record[p->res->record_count++];
			memset(r, 0, sizeof *r);
			r->rail = rail;
			r->slot = slot;
			r->command = command;
			r->type = p->slot_type[slot];
			r->enable = enable;
			r->msgid = msgid;
			r->tcs_status = status;
			r->cmd_status = cmd_status;
			r->address = address;
			r->data = data;
			if ((enable >> command) & 1u)
				r->flags |= K60_RAIL_OBS_REC_ENABLED;
			finish_record(r);
		}
	}
	return 0;
}

static int is_request(const K60RailObsRecord *r)
{
	return (r->flags & (K60_RAIL_OBS_REC_ENABLED | K60_RAIL_OBS_REC_FORMAT_OK)) ==
	    (K60_RAIL_OBS_REC_ENABLED | K60_RAIL_OBS_REC_FORMAT_OK);
}

static void duplicates(Pass *p)
{
	uint32_t i, j, rail;
	for (rail = 0; rail < 2; rail++) {
		int identical = 0, conflict = 0;
		for (i = 0; i < p->res->record_count; i++) {
			const K60RailObsRecord *a = &p->res->record[i];
			if (a->rail != rail || !is_request(a)) continue;
			for (j = i + 1; j < p->res->record_count; j++) {
				const K60RailObsRecord *b = &p->res->record[j];
				if (b->rail != rail || !is_request(b)) continue;
				if (a->address != b->address || a->data != b->data ||
				    a->msgid != b->msgid || a->type != b->type)
					conflict = 1;
				else identical = 1;
			}
		}
		if (identical) p->res->qualifiers |= K60_RAIL_OBS_Q_DUPLICATE_IDENTICAL;
		if (conflict) p->res->qualifiers |= K60_RAIL_OBS_Q_DUPLICATE_CONFLICT;
	}
}

static void classify(Pass *p)
{
	uint32_t i, rails = 0, malformed = 0;
	for (i = 0; i < p->res->record_count; i++) {
		const K60RailObsRecord *r = &p->res->record[i];
		if (r->flags & K60_RAIL_OBS_REC_DISABLED)
			p->res->qualifiers |= K60_RAIL_OBS_Q_DISABLED_RESIDUAL;
		if (r->flags & K60_RAIL_OBS_REC_TCS_BUSY)
			p->res->qualifiers |= K60_RAIL_OBS_Q_TCS_BUSY;
		if (r->flags & K60_RAIL_OBS_REC_MALFORMED)
			p->res->qualifiers |= K60_RAIL_OBS_Q_MALFORMED;
		if ((r->flags & K60_RAIL_OBS_REC_ENABLED) &&
		    !(r->flags & K60_RAIL_OBS_REC_FORMAT_OK)) malformed = 1;
		if (r->flags & K60_RAIL_OBS_REC_RESPONSE) {
			if (!(r->cmd_status & 0x100u))
				p->res->qualifiers |= K60_RAIL_OBS_Q_NOT_ISSUED;
			else if (!(r->cmd_status & 0x10000u))
				p->res->qualifiers |= K60_RAIL_OBS_Q_INCOMPLETE;
		}
	}
	for (i = 0; i < 2; i++) {
		uint32_t j;
		for (j = 0; j < p->res->record_count; j++)
			if (p->res->record[j].rail == i && is_request(&p->res->record[j]))
				break;
		if (j < p->res->record_count) rails |= 1u << i;
	}
	if (p->res->qualifiers & K60_RAIL_OBS_Q_DUPLICATE_CONFLICT)
		p->res->outcome = K60_RAIL_OBS_OUTCOME_DUPLICATE_CONFLICT;
	else if (rails != 3u)
		p->res->outcome = malformed ? K60_RAIL_OBS_OUTCOME_MALFORMED_REQUEST :
		    K60_RAIL_OBS_OUTCOME_NOT_FOUND;
	else
		p->res->outcome = K60_RAIL_OBS_OUTCOME_OBSERVED_REQUEST;
}

static void stop_outcome(Pass *p)
{
	switch (p->stop) {
	case C_PERMISSION: p->res->outcome = K60_RAIL_OBS_OUTCOME_PERMISSION_DENIED; break;
	case C_COVERAGE: p->res->outcome = K60_RAIL_OBS_OUTCOME_COVERAGE_INCOMPLETE; break;
	case C_READ: p->res->outcome = K60_RAIL_OBS_OUTCOME_READ_FAILED; break;
	case C_GEOMETRY: p->res->outcome = K60_RAIL_OBS_OUTCOME_GEOMETRY_INVALID; break;
	case C_DB_CORRUPT:
		p->res->outcome = strcmp(p->stop_field, "db missing") == 0 ?
		    K60_RAIL_OBS_OUTCOME_DB_MISSING : K60_RAIL_OBS_OUTCOME_DB_CORRUPT;
		break;
	case C_CAPACITY: p->res->outcome = K60_RAIL_OBS_OUTCOME_COVERAGE_INCOMPLETE; break;
	default: p->res->outcome = K60_RAIL_OBS_OUTCOME_COVERAGE_INCOMPLETE; break;
	}
}

static void run_pass(Pass *p)
{
	uint32_t version, caps, max_tcs, ncpt, sum = 0, i, slot = 0;
	uint64_t end;

	if (map(p, 0) != 0) {
		p->res->outcome = K60_RAIL_OBS_OUTCOME_MAP_FAILED_DB;
		return;
	}
	if (db_find(p, "lcx.lvl", &p->res->resource[0]) != 0 ||
	    db_find(p, "lmx.lvl", &p->res->resource[1]) != 0) {
		stop_outcome(p);
		unmap(p, 0);
		return;
	}
	unmap(p, 0);
	if (map(p, 1) != 0) {
		p->res->outcome = K60_RAIL_OBS_OUTCOME_MAP_FAILED_RSC;
		return;
	}
	if (read_field(p, 1, 1, p->permit->map_extent_rsc, 0, "version",
	    &version) != 0) {
		stop_outcome(p); unmap(p, 1); return;
	}
	p->res->version = version;
	if (layout(p, version) != 0) {
		p->res->outcome = K60_RAIL_OBS_OUTCOME_UNSUPPORTED_VERSION;
		unmap(p, 1); return;
	}
	end = p->cmd_status_off + 4u;
	if (end > p->permit->command_block) {
		p->res->outcome = K60_RAIL_OBS_OUTCOME_GEOMETRY_INVALID;
		unmap(p, 1); return;
	}
	if (read_field(p, 1, 1, p->permit->map_extent_rsc, 0x0cu, "caps",
	    &caps) != 0) {
		stop_outcome(p); unmap(p, 1); return;
	}
	p->res->caps = caps;
	max_tcs = (caps >> (6u * p->permit->logical_drv_id)) & 0x3fu;
	ncpt = (caps >> 27) & 0x1fu;
	p->res->slots = 0;
	p->res->commands = 0;
	if (max_tcs == 0 || ncpt == 0) {
		p->res->outcome = K60_RAIL_OBS_OUTCOME_CAPS_INVALID;
		unmap(p, 1); return;
	}
	for (i = 0; i < 5; i++) sum += p->permit->type_count[i];
	if (sum > max_tcs || sum > p->permit->reviewed_max_slots) {
		p->res->outcome = K60_RAIL_OBS_OUTCOME_CAPS_INVALID;
		unmap(p, 1); return;
	}
	for (i = 0; i < 5; i++) {
		uint32_t type = p->permit->type_order[i];
		uint32_t n = p->permit->type_count[type];
		while (n-- > 0 && slot < K60_RAIL_OBS_MAX_SLOTS)
			p->slot_type[slot++] = type;
	}
	p->res->slots = slot;
	p->res->commands = ncpt < p->permit->reviewed_max_commands ?
	    ncpt : p->permit->reviewed_max_commands;
	if (scan(p, p->res->slots, p->res->commands) != 0) {
		stop_outcome(p); unmap(p, 1); return;
	}
	unmap(p, 1);
	p->res->coverage_complete = 1;
	duplicates(p);
	classify(p);
}

static int cache_ok(const K60RailObsResult *r, const K60RailObsPermit *permit)
{
	uint32_t i;
	if (r->magic != K60_RAIL_OBS_MAGIC || r->schema != K60_RAIL_OBS_SCHEMA ||
	    r->bytes != sizeof(K60RailObsResult) ||
	    r->state != K60_RAIL_OBS_TERMINAL || r->authority != 0) return 0;
	if (r->outcome <= K60_RAIL_OBS_OUTCOME_NONE ||
	    r->outcome > K60_RAIL_OBS_OUTCOME_CACHE_CORRUPT) return 0;
	if (r->record_count > K60_RAIL_OBS_MAX_RECORDS) return 0;
	if (r->coverage_complete > 1 || r->stop_region > 1) return 0;
	if (r->stop_field[sizeof r->stop_field - 1] != '\0') return 0;
	if (r->plan_digest != plan_digest(permit)) return 0;
	for (i = 0; i < 2; i++) {
		if (r->maps[i] > 1u || r->loads[i] > 0x10000u) return 0;
	}
	if (r->checksum != checksum_of(r)) return 0;
	return 1;
}

static int cache_read(const K60RailObsPermit *permit, K60RailObsResult *out)
{
	K60RailObsResult copy;
	unsigned s = atomic_load_explicit(&attempt, memory_order_acquire);
	if (s != K60_RAIL_OBS_TERMINAL) return K60_RAIL_OBS_BUSY;
	copy = terminal;
	if (copy.plan_digest != plan_digest(permit))
		return K60_RAIL_OBS_PLAN_MISMATCH;
	if (!cache_ok(&copy, permit)) return K60_RAIL_OBS_CACHE_CORRUPT;
	*out = copy;
	return K60_RAIL_OBS_RETURNED;
}

int k60_rail_observe_once(K60RailObsGate gate, const K60RailObsPermit *permit,
    const K60RailObsIo *io, K60RailObsResult *out)
{
	unsigned expected = K60_RAIL_OBS_UNATTEMPTED;
	K60RailObsResult local;
	Pass pass;

	if (out == NULL || permit == NULL || io == NULL || io->map == NULL ||
	    io->read32 == NULL) return K60_RAIL_OBS_BAD_INPUT;
	if (!gate_ok(gate)) return K60_RAIL_OBS_INELIGIBLE;
	if (!permit_valid(permit)) return K60_RAIL_OBS_BAD_INPUT;
	if (!atomic_compare_exchange_strong_explicit(&attempt, &expected,
	    K60_RAIL_OBS_ATTEMPTING, memory_order_acq_rel,
	    memory_order_acquire)) {
		if (expected == K60_RAIL_OBS_TERMINAL) return cache_read(permit, out);
		return K60_RAIL_OBS_BUSY;
	}
	memset(&local, 0, sizeof local);
	local.magic = K60_RAIL_OBS_MAGIC;
	local.schema = K60_RAIL_OBS_SCHEMA;
	local.bytes = sizeof local;
	local.state = K60_RAIL_OBS_TERMINAL;
	local.outcome = K60_RAIL_OBS_OUTCOME_COVERAGE_INCOMPLETE;
	local.authority = K60_RAIL_OBS_NO_AUTHORITY;
	local.plan_digest = plan_digest(permit);
	local.data_mounted = gate.data_mounted;
	local.parse_ok = gate.parse_ok;
	local.parsed_value = gate.parsed_value;
	local.db_physical = K60_RAIL_OBS_DB_PHYS;
	local.rsc_physical = K60_RAIL_OBS_RSC_PHYS;
	local.logical_drv_id = permit->logical_drv_id;
	strcpy(local.stop_field, "attempt");
	memset(&pass, 0, sizeof pass);
	pass.permit = permit;
	pass.io = io;
	pass.res = &local;
	run_pass(&pass);
	if (pass.stop != C_NONE) {
		local.stop_region = pass.stop_region;
		local.stop_offset = pass.stop_at;
		memset(local.stop_field, 0, sizeof local.stop_field);
		if (pass.stop_field != NULL)
			strncpy(local.stop_field, pass.stop_field,
			    sizeof local.stop_field - 1);
	} else {
		memset(local.stop_field, 0, sizeof local.stop_field);
		strcpy(local.stop_field, "none");
	}
	local.checksum = checksum_of(&local);
	terminal = local;
	atomic_store_explicit(&attempt, K60_RAIL_OBS_TERMINAL, memory_order_release);
	*out = local;
	return K60_RAIL_OBS_RETURNED;
}

#ifdef K60_RAIL_OBS_HOST_TEST
void k60_rail_obs_test_corrupt(unsigned kind)
{
	if (atomic_load_explicit(&attempt, memory_order_acquire) !=
	    K60_RAIL_OBS_TERMINAL) return;
	switch (kind) {
	case 0: terminal.magic ^= 0x1u; break;
	case 1: terminal.checksum ^= 0x1u; break;
	case 2: terminal.record_count = K60_RAIL_OBS_MAX_RECORDS + 1u; break;
	default: break;
	}
}

unsigned k60_rail_obs_test_state(void)
{
	return atomic_load_explicit(&attempt, memory_order_acquire);
}
#endif
