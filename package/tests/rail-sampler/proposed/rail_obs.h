/* Offline candidate only. NOT production, NOT linked, no hardware, no boot.
 * Source facts: Xiaomi 989b27aa8391a2ede9b067b53877c4c3343955fe,
 * Linux 458c6079fc1d41d564c37679c8ace02cd83ee817 rpmh-rsc.c.
 * HARD-RULES.md:44-58 currently names only DRV-2 w[0] as a conditionally
 * permitted read. Every span below is therefore an explicit INPUT, not a
 * permission inferred from geometry, DT counts or historical logs.
 */
#ifndef K60_RAIL_OBS_H
#define K60_RAIL_OBS_H
#include <stddef.h>
#include <stdint.h>

#define K60_RAIL_OBS_DB_PHYS   UINT64_C(0x80860000)
#define K60_RAIL_OBS_RSC_PHYS  UINT64_C(0x17a20000)
#define K60_RAIL_OBS_DB_BYTES  0x20000u
#define K60_RAIL_OBS_RSC_BYTES 0x10000u
#define K60_RAIL_OBS_MAX_SLOTS 16u
#define K60_RAIL_OBS_MAX_COMMANDS 16u
#define K60_RAIL_OBS_MAX_RECORDS 32u
#define K60_RAIL_OBS_MAX_SPANS 64u
#define K60_RAIL_OBS_REVIEWED 0x52455631u
#define K60_RAIL_OBS_MAGIC 0x4b524f31u
#define K60_RAIL_OBS_SCHEMA 1u
#define K60_RAIL_OBS_NO_AUTHORITY 0u

/* All codes are negative: there is no zero/"success" return that could be
 * mistaken for ResourcesHeld, not even after a complete observation. */
enum {
	K60_RAIL_OBS_RETURNED = -1,
	K60_RAIL_OBS_INELIGIBLE = -2,
	K60_RAIL_OBS_BUSY = -3,
	K60_RAIL_OBS_CACHE_CORRUPT = -4,
	K60_RAIL_OBS_BAD_INPUT = -5,
	K60_RAIL_OBS_PLAN_MISMATCH = -6
};

enum {
	K60_RAIL_OBS_UNATTEMPTED = 0,
	K60_RAIL_OBS_ATTEMPTING = 1,
	K60_RAIL_OBS_TERMINAL = 2
};

enum {
	K60_RAIL_OBS_OUTCOME_NONE = 0,
	K60_RAIL_OBS_OUTCOME_INELIGIBLE,
	K60_RAIL_OBS_OUTCOME_MAP_FAILED_DB,
	K60_RAIL_OBS_OUTCOME_MAP_FAILED_RSC,
	K60_RAIL_OBS_OUTCOME_READ_FAILED,
	K60_RAIL_OBS_OUTCOME_DB_CORRUPT,
	K60_RAIL_OBS_OUTCOME_DB_MISSING,
	K60_RAIL_OBS_OUTCOME_PERMISSION_DENIED,
	K60_RAIL_OBS_OUTCOME_UNSUPPORTED_VERSION,
	K60_RAIL_OBS_OUTCOME_CAPS_INVALID,
	K60_RAIL_OBS_OUTCOME_GEOMETRY_INVALID,
	K60_RAIL_OBS_OUTCOME_COVERAGE_INCOMPLETE,
	K60_RAIL_OBS_OUTCOME_NOT_FOUND,
	K60_RAIL_OBS_OUTCOME_MALFORMED_REQUEST,
	K60_RAIL_OBS_OUTCOME_DUPLICATE_CONFLICT,
	K60_RAIL_OBS_OUTCOME_OBSERVED_REQUEST,
	K60_RAIL_OBS_OUTCOME_CACHE_CORRUPT
};

/* Non-exclusive qualifiers; outcome alone must not hide them. */
#define K60_RAIL_OBS_Q_DISABLED_RESIDUAL 0x0001u
#define K60_RAIL_OBS_Q_MALFORMED         0x0002u
#define K60_RAIL_OBS_Q_TCS_BUSY          0x0004u
#define K60_RAIL_OBS_Q_NOT_ISSUED        0x0008u
#define K60_RAIL_OBS_Q_INCOMPLETE        0x0010u
#define K60_RAIL_OBS_Q_DUPLICATE_IDENTICAL 0x0020u
#define K60_RAIL_OBS_Q_DUPLICATE_CONFLICT  0x0040u

typedef struct { uint64_t offset, bytes; } K60RailObsSpan;

/* Explicit reviewed plan. Absent/unknown/conflicting input is refused before
 * the attempt is claimed, so a typo cannot poison the one lifetime attempt. */
typedef struct {
	uint32_t reviewed;          /* K60_RAIL_OBS_REVIEWED */
	uint32_t plan_id;           /* caller's reviewed plan identity */
	uint32_t logical_drv_id;    /* 0..3; caps shifts by 6*id */
	uint32_t type_count[5];     /* sleep,wake,active,control,fast */
	uint32_t type_order[5];     /* exact DT order, permutation of 0..4 */
	uint64_t tcs_offset;        /* reviewed board value */
	uint32_t reviewed_max_slots;
	uint32_t reviewed_max_commands;
	const K60RailObsSpan *db_spans;
	size_t db_span_count;
	size_t db_span_capacity;
	const K60RailObsSpan *rsc_spans;
	size_t rsc_span_count;
	size_t rsc_span_capacity;
	K60RailObsSpan bootstrap[2]; /* exactly {0,4} and {0xc,4} */
	uint32_t map_extent_db;      /* bytes actually requested from map */
	uint32_t map_extent_rsc;
	uint32_t db_block;           /* reviewed cmd-db parse extent */
	uint32_t command_block;      /* reviewed command block width */
} K60RailObsPermit;

typedef struct {
	int32_t data_mounted; /* must equal 1 */
	int32_t parse_ok;     /* boot-argument name parsed */
	int32_t parsed_value; /* must equal 1 */
} K60RailObsGate;

/* Opaque map token. The core never dereferences it; every raw load, including
 * cmd-db bytes, must pass through read32 at a checked, permitted offset. */
typedef struct {
	void *context;
	int (*map)(void *context, uint32_t region, uint64_t physical,
	    size_t requested, void **token, size_t *mapped_bytes);
	int (*read32)(void *context, void *token, size_t offset, uint32_t *value);
	void (*unmap)(void *context, void *token);
} K60RailObsIo;

#define K60_RAIL_OBS_REGION_DB 0u
#define K60_RAIL_OBS_REGION_RSC 1u

typedef struct {
	uint32_t rail;      /* 0 lcx.lvl, 1 lmx.lvl */
	uint32_t slot, command, type;
	uint32_t flags;
	uint32_t enable, msgid, tcs_status, cmd_status, address, data;
} K60RailObsRecord;

#define K60_RAIL_OBS_REC_ENABLED   0x0001u
#define K60_RAIL_OBS_REC_FORMAT_OK 0x0002u
#define K60_RAIL_OBS_REC_RESPONSE  0x0004u
#define K60_RAIL_OBS_REC_ISSUED    0x0008u
#define K60_RAIL_OBS_REC_COMPLETE  0x0010u
#define K60_RAIL_OBS_REC_DISABLED  0x0020u
#define K60_RAIL_OBS_REC_MALFORMED 0x0040u
#define K60_RAIL_OBS_REC_TCS_BUSY  0x0080u

/* A request observation. There is deliberately no power/voltage/authority
 * field and no conversion to ResourcesHeld. authority is always 0. */
typedef struct {
	uint32_t magic, schema, bytes, state, outcome, qualifiers, authority;
	uint32_t plan_digest;
	int32_t data_mounted, parse_ok, parsed_value;
	uint64_t db_physical, rsc_physical;
	uint32_t logical_drv_id, version, caps, slots, commands;
	uint32_t resource[2];       /* cmd-db addresses, not voltages */
	uint32_t coverage_complete, record_count;
	uint32_t maps[2], loads[2]; /* attempt totals, not this call's counters */
	uint32_t stop_region;
	uint64_t stop_offset;
	char stop_field[24];
	K60RailObsRecord record[K60_RAIL_OBS_MAX_RECORDS];
	uint64_t checksum;          /* accidental corruption only, not auth */
} K60RailObsResult;

/* One attempt per process/boot, shared by every caller. Gate and plan are
 * re-validated on every call before any cached result is returned. A loser
 * returns BUSY immediately without mapping or loading. There is no reset. */
int k60_rail_observe_once(K60RailObsGate gate, const K60RailObsPermit *permit,
    const K60RailObsIo *io, K60RailObsResult *out);

#ifdef K60_RAIL_OBS_HOST_TEST
/* Sequential only, after TERMINAL: 0=magic, 1=checksum, 2=record_count. */
void k60_rail_obs_test_corrupt(unsigned kind);
unsigned k60_rail_obs_test_state(void);
#endif

#endif /* K60_RAIL_OBS_H */
