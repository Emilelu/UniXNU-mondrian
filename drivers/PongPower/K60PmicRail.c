/*
 * The pm8350c_l2 rail lives behind the applications RSC: the AP has no SPMI
 * channel for PPID 0x241 (the kernel's SPMI probe answered apid=-1), so a
 * voltage vote can only go through RPMh. This file only reads: it parses the
 * command database and reports the resource's RPMh address and level table so
 * that the vote (if any) is written against measured numbers.
 *
 * The layout follows UniXNU-sheng/package/QcomRpmh.{c,h}; that reference is
 * the only working RPMh implementation in the tree and its parser is pinned by
 * a host test with a synthetic database.
 */
#include "K60PmicRail.h"

#ifdef KERNEL
#include <pexpert/pexpert.h>
#include <machine/machine_routines.h>
/* printf() lives here, not in pexpert.h: without it the kernel build stops at
 * "call to undeclared function 'printf'" (the host test never sees this file's
 * KERNEL branch, so only a real build catches it). */
#include <sys/systm.h>

extern vm_offset_t ml_io_map_unmappable(vm_offset_t phys, vm_size_t size,
    unsigned int flags);
#endif /* KERNEL */

static uint16_t
le16(const uint8_t *p)
{
	return (uint16_t)(p[0] | (uint16_t)p[1] << 8);
}

static uint32_t
le32(const uint8_t *p)
{
	return (uint32_t)le16(p) | (uint32_t)le16(p + 2) << 16;
}

static int
fits(size_t at, size_t length, size_t size)
{
	return at <= size && length <= size - at;
}

/*
 * Header: u32 version, u32 magic, eight 16-byte slave records
 * (u16 id, header offset, data offset, entry count, version, reserved[3]),
 * u32 checksum, u32 reserved, then the region the offsets count from.
 * Entries are 24 bytes: an 8-byte id, two u32 priorities, u32 address,
 * u16 aux length, u16 aux offset.
 */
int
k60_cmd_db_find(const uint8_t *db, size_t bytes, const char *name,
    K60RpmhResource *out)
{
	char id[8] = { 0 };
	size_t n;

	if (db == NULL || name == NULL || out == NULL) {
		return K60RpmhArgument;
	}
	if (bytes < 144 || le32(db + 4) != K60_CMD_DB_MAGIC) {
		return K60RpmhNoDb;
	}
	for (n = 0; n < sizeof(id) && name[n] != '\0'; n++) {
		id[n] = name[n];
	}
	for (unsigned s = 0; s < 8; s++) {
		const uint8_t *slave = db + 8 + 16 * s;
		size_t heads, data, count;

		if (le16(slave) == 0) {
			break;
		}
		heads = 144u + le16(slave + 2);
		data = 144u + le16(slave + 4);
		count = le16(slave + 6);
		if (!fits(heads, count * 24, bytes)) {
			return K60RpmhCorrupt;
		}
		for (size_t e = 0; e < count; e++) {
			const uint8_t *entry = db + heads + 24 * e;
			int same = 1;

			for (unsigned i = 0; i < sizeof(id) && same; i++) {
				same = entry[i] == (uint8_t)id[i];
			}
			if (!same) {
				continue;
			}
			{
				K60RpmhResource r;
				size_t length, at;

				r.address = le32(entry + 16);
				r.level_count = 0;
				length = le16(entry + 20);
				at = data + le16(entry + 22);
				if (r.address == 0 || !fits(at, length, bytes)) {
					return K60RpmhCorrupt;
				}
				for (size_t l = 0;
				    l + 1 < length && r.level_count < K60_RPMH_MAX_LEVELS;
				    l += 2) {
					uint16_t level = le16(db + at + l);

					if (r.level_count != 0 && level == 0) {
						break;  /* zero padded */
					}
					r.levels[r.level_count++] = level;
				}
				*out = r;
				return K60RpmhOk;
			}
		}
	}
	return K60RpmhMissing;
}

int
k60_rpmh_level_index(const K60RpmhResource *r, uint32_t level, uint32_t *index)
{
	if (r == NULL || index == NULL || r->level_count == 0) {
		return K60RpmhNoLevel;
	}
	if (level == 0) {
		*index = 0;
		return K60RpmhOk;
	}
	for (unsigned i = 0; i < r->level_count; i++) {
		if (r->levels[i] >= level) {
			*index = i;
			return K60RpmhOk;
		}
	}
	/* Reporting the highest corner as a success would let a caller vote a
	 * voltage it never asked for while believing the request was honoured.
	 * If the table cannot express the level, say so. */
	*index = r->level_count - 1;
	return K60RpmhNoLevel;
}

K60RscLayout
k60_rsc_layout(uint32_t drv_id)
{
	K60RscLayout v3 = { 672, 24, 0x04, 0x08, 0x20, 0x24, 0x28, 0x2c, 0x34,
			    0x38, 0x3c };
	K60RscLayout v2 = { 672, 20, 0x04, 0x08, 0x10, 0x14, 0x18, 0x1c, 0x30,
			    0x34, 0x38 };

	return ((drv_id >> 16) & 0xff) >= 3 ? v3 : v2;
}

/* Clear a record so that a failed measurement still names what was missing. */
static void
rail_record_clear(K60RailRecord *r, const char *not_read)
{
	r->resource_id = 0;
	r->address = 0;
	r->level = 0;
	r->tcs_slot = 0;
	r->complete = 0;
	r->valid = 0;
	r->missing = not_read;
	r->why = 0;
}

/*
 * Scan the DRV-2 TCS slots for the one whose cmd_addr carries this rail's
 * cmd-db address, then read that slot's cmd_data. Read-only: every access is a
 * load from the already-mapped window. The slot number is discovered, never
 * assumed, because this board votes touch through TCS3 while the reference
 * implementation writes slot 4 (POWER-RPMH-LDOC2.md:30-33, :142-144).
 */
int
k60_rail_measure(const volatile uint32_t *words, size_t words_bytes,
    const K60RscLayout *layout, uint32_t resource_id, K60RailRecord *out)
{
	unsigned slot;

	if (out == NULL || layout == NULL || words == NULL) {
		return K60RpmhArgument;
	}
	rail_record_clear(out, "resource id");
	if (resource_id == 0) {
		return K60RpmhMissing;
	}
	out->resource_id = resource_id;
	out->missing = "tcs slot";
	for (slot = 0; slot < K60_RAIL_SLOTS; slot++) {
		const size_t base = (size_t)K60_RSC_TCS_OFFSET +
		    (size_t)slot * layout->tcs_stride;
		size_t at_addr, at_data, at_status;
		uint32_t addr;

		if (base + layout->cmd_data + sizeof(uint32_t) > words_bytes ||
		    base + layout->status + sizeof(uint32_t) > words_bytes) {
			break;
		}
		at_addr = base + layout->cmd_addr;
		at_data = base + layout->cmd_data;
		at_status = base + layout->status;
		addr = words[at_addr / sizeof(uint32_t)];
		if (addr != resource_id) {
			continue;
		}
		out->tcs_slot = slot;
		out->address = addr;
		out->level = words[at_data / sizeof(uint32_t)];
		out->complete = 1;
		out->missing = 0;
		if (out->level == 0) {
			out->why = "level read back as 0";
		} else if ((words[at_status / sizeof(uint32_t)] & 1u) == 0) {
			out->why = "tcs slot not idle";
		} else {
			out->valid = 1;
		}
		return K60RpmhOk;
	}
	return K60RpmhMissing;
}

static K60RailLedger rail_ledger;

void
k60_rail_ledger_store(uint32_t drv_id, const K60RailRecord *lcx,
    const K60RailRecord *lmx)
{
	K60RailLedger next;

	next.magic = K60_RAIL_LEDGER_MAGIC;
	next.drv_id = drv_id;
	next.recorded = 1;
	next.gate = K60_RAIL_GATE_PROBE;
	if (lcx != NULL) {
		next.lcx = *lcx;
	} else {
		rail_record_clear(&next.lcx, "not read");
	}
	if (lmx != NULL) {
		next.lmx = *lmx;
	} else {
		rail_record_clear(&next.lmx, "not read");
	}
	rail_ledger = next;
}

const K60RailLedger *
k60_rail_ledger(void)
{
	return rail_ledger.recorded ? &rail_ledger : 0;
}

/*
 * The three answers a consumer must be able to tell apart. "Not recorded" is
 * not "the rail is absent"; "incomplete" is not "invalid"; and only the last
 * one says something about the rail itself rather than about the read.
 */
int
k60_rail_verdict(const K60RailLedger *ledger, const char **rail,
    const char **field)
{
	const K60RailRecord *r;

	if (rail != 0) {
		*rail = 0;
	}
	if (field != 0) {
		*field = 0;
	}
	if (ledger == 0 || ledger->magic != K60_RAIL_LEDGER_MAGIC ||
	    !ledger->recorded) {
		return K60RailVerdictNotRecorded;
	}
	r = &ledger->lcx;
	if (!r->complete) {
		if (rail != 0) {
			*rail = "lcx";
		}
		if (field != 0) {
			*field = r->missing ? r->missing : "field";
		}
		return K60RailVerdictIncomplete;
	}
	if (!r->valid) {
		if (rail != 0) {
			*rail = "lcx";
		}
		if (field != 0) {
			*field = r->why ? r->why : "inconsistent";
		}
		return K60RailVerdictInvalid;
	}
	r = &ledger->lmx;
	if (!r->complete) {
		if (rail != 0) {
			*rail = "lmx";
		}
		if (field != 0) {
			*field = r->missing ? r->missing : "field";
		}
		return K60RailVerdictIncomplete;
	}
	if (!r->valid) {
		if (rail != 0) {
			*rail = "lmx";
		}
		if (field != 0) {
			*field = r->why ? r->why : "inconsistent";
		}
		return K60RailVerdictInvalid;
	}
	return K60RailVerdictInherited;
}

#ifdef KERNEL
static void
rail_print(const char *name, const K60RailRecord *r)
{
	printf("K60RAIL %s id=%#x tcs=%u addr=%#x level=%u (arc index, not mV)"
	    " complete=%u valid=%u", name, r->resource_id, r->tcs_slot,
	    r->address, r->level, r->complete, r->valid);
	if (r->missing != 0) {
		printf(" missing=%s", r->missing);
	}
	if (r->why != 0) {
		printf(" why=%s", r->why);
	}
	printf("\n");
}

/* One read-only pass over the two windows: find each rail's cmd-db address and
 * read the TCS slot that address names. Nothing here writes. */
static void
rail_record_pass(const uint8_t *db, volatile uint32_t *words, uint32_t drv_id)
{
	K60RailRecord lcx, lmx;
	K60RscLayout layout = k60_rsc_layout(drv_id);
	K60RpmhResource rail;
	uint32_t lcx_id = 0, lmx_id = 0;

	if (k60_cmd_db_find(db, K60_CMD_DB_BYTES, "lcx.lvl", &rail) == K60RpmhOk) {
		lcx_id = rail.address;
	}
	if (k60_cmd_db_find(db, K60_CMD_DB_BYTES, "lmx.lvl", &rail) == K60RpmhOk) {
		lmx_id = rail.address;
	}
	(void)k60_rail_measure(words, K60_RSC_BYTES, &layout, lcx_id, &lcx);
	(void)k60_rail_measure(words, K60_RSC_BYTES, &layout, lmx_id, &lmx);
	k60_rail_ledger_store(drv_id, &lcx, &lmx);
	rail_print("lcx", &lcx);
	rail_print("lmx", &lmx);
}

/* Map both windows once, record, leave. 0 means the ledger now exists. */
static int
rail_pass(void)
{
	vm_offset_t db, rsc;

	db = ml_io_map_unmappable((vm_offset_t)K60_CMD_DB_PHYS,
	    (vm_size_t)K60_CMD_DB_BYTES, 0x7);
	if (db == 0) {
		printf("K60RAIL cmd-db map failed phys=%#llx\n",
		    (unsigned long long)K60_CMD_DB_PHYS);
		return -1;
	}
	rsc = ml_io_map_unmappable((vm_offset_t)K60_RSC_DRV2_PHYS,
	    (vm_size_t)K60_RSC_BYTES, 0x7);
	if (rsc == 0) {
		printf("K60RAIL rsc map failed phys=%#llx\n",
		    (unsigned long long)K60_RSC_DRV2_PHYS);
		return -1;
	}
	rail_record_pass((const uint8_t *)db, (volatile uint32_t *)rsc,
	    ((volatile uint32_t *)rsc)[0]);
	return 0;
}

/*
 * The rail gate, and the reason it is not in resources(): the earliest call
 * site in the kernel cannot legally read these registers at all (HR-01 timing),
 * so a verdict there would be an always-false condition wearing a gate's
 * clothes (P-223). This runs as the first step of k60_adsp_bring_up(), which
 * only exists after Data mount and which reaches AUTH_AND_RESET itself; the
 * refusal therefore sits before the irreversible step it is protecting.
 */
int
k60_rail_inherit(void)
{
	const K60RailLedger *led;
	const char *rail = 0, *field = 0;
	int verdict, gate = 0;

	led = k60_rail_ledger();
	if (led == 0 || led->magic != K60_RAIL_LEDGER_MAGIC || !led->recorded) {
		/* HR-01 condition 2: this second restricted read site stays behind
		 * the same explicit boot argument as the first one. */
		if (!PE_parse_boot_argn("pong_rail_probe", &gate, sizeof(gate)) ||
		    gate == 0) {
			printf("K60ADSP: rails not measured: pong_rail_probe is "
			    "off, so inheritance cannot be proven; refusing "
			    "AUTH_AND_RESET\n");
			return K60_RAIL_REFUSED;
		}
		if (rail_pass() != 0) {
			printf("K60ADSP: rails not measured: cmd-db=%#llx or "
			    "rsc=%#llx could not be mapped; refusing "
			    "AUTH_AND_RESET\n",
			    (unsigned long long)K60_CMD_DB_PHYS,
			    (unsigned long long)K60_RSC_DRV2_PHYS);
			return K60_RAIL_REFUSED;
		}
		led = k60_rail_ledger();
	}
	verdict = k60_rail_verdict(led, &rail, &field);
	if (verdict == K60RailVerdictInherited) {
		printf("K60ADSP: rails inherited lcx=%#x@%u level=%u "
		    "lmx=%#x@%u level=%u (arc index, not mV)\n",
		    led->lcx.resource_id, led->lcx.tcs_slot, led->lcx.level,
		    led->lmx.resource_id, led->lmx.tcs_slot, led->lmx.level);
		return 0;
	}
	if (verdict == K60RailVerdictInvalid) {
		/* Wording differs from the missing case on purpose: a measured
		 * but self-inconsistent rail is not a failed read. */
		printf("K60ADSP: rail measured but invalid %s (%s); refusing "
		    "AUTH_AND_RESET\n", rail ? rail : "?", field ? field : "?");
		return K60_RAIL_REFUSED;
	}
	printf("K60ADSP: rail not inherited %s: %s missing; refusing "
	    "AUTH_AND_RESET\n", rail ? rail : "lcx", field ? field : "record");
	return K60_RAIL_REFUSED;
}

int
k60_rail_probe(void)
{
	vm_offset_t db = 0, rsc = 0;
	const uint8_t *bytes;
	K60RpmhResource res;
	int rc;

	db = ml_io_map_unmappable((vm_offset_t)K60_CMD_DB_PHYS,
	    (vm_size_t)K60_CMD_DB_BYTES, 0x7);
	if (db == 0) {
		printf("K60RAIL cmd-db map failed phys=%#llx\n",
		    (unsigned long long)K60_CMD_DB_PHYS);
		return -1;
	}
	bytes = (const uint8_t *)db;
	printf("K60RAIL cmd-db magic=%#x version=%u\n", le32(bytes + 4),
	    le32(bytes));
	rc = k60_cmd_db_find(bytes, K60_CMD_DB_BYTES, "ldoc2", &res);
	if (rc != K60RpmhOk) {
		printf("K60RAIL ldoc2 not found rc=%d\n", rc);
	} else {
		uint32_t index = 0;
		int li = k60_rpmh_level_index(&res, 1800, &index);

		/* The level table did not look like millivolts, so dump the bytes
		 * that produced it instead of guessing a different field layout.
		 * ldoc2 lives in a different slave than the clock resources, so walk
		 * every slave the header declares. */
		{
			uint32_t s;

			for (s = 0; s < 8; s++) {
				const uint8_t *slave = bytes + 8 + 16 * s;
				uint32_t id = le16(slave);
				uint32_t heads, data, count, e;

				if (id == 0) {
					break;
				}
				heads = 144u + le16(slave + 2);
				data = 144u + le16(slave + 4);
				count = le16(slave + 6);
				printf("K60RAIL slave%u id=%u heads=%u data=%u count=%u\n",
				    s, id, heads, data, count);
				for (e = 0; e < count && e < 40; e++) {
					const uint8_t *en = bytes + heads + 24 * e;
					uint32_t at, n, i;

					printf("K60RAIL s%u e%u id=%c%c%c%c%c%c%c%c "
					    "addr=%#x len=%u off=%u\n", s, e,
					    en[0], en[1], en[2], en[3], en[4], en[5], en[6], en[7],
					    le32(en + 16), le16(en + 20), le16(en + 22));
					if (en[0] != 'l' || en[1] != 'd' || en[2] != 'o' ||
					    en[3] != 'c' || en[4] != '2') {
						continue;
					}
					at = data + le16(en + 22);
					n = le16(en + 20);
					printf("K60RAIL ldoc2 aux at=%u len=%u:", at, n);
					for (i = 0; i < n && i < 32; i++) {
						printf(" %02x", bytes[at + i]);
					}
					printf("\n");
				}
			}
		}
		printf("K60RAIL ldoc2 address=%#x levels=%u idx1800=%d->%u",
		    res.address, res.level_count, li, index);
		for (unsigned i = 0; i < res.level_count && i < 8; i++) {
			printf(" l%u=%u", i, res.levels[i]);
		}
		printf("\n");
	}
	rsc = ml_io_map_unmappable((vm_offset_t)K60_RSC_DRV2_PHYS,
	    (vm_size_t)K60_RSC_BYTES, 0x7);
	if (rsc == 0) {
		printf("K60RAIL rsc map failed phys=%#llx\n",
		    (unsigned long long)K60_RSC_DRV2_PHYS);
		return -1;
	}
	{
		volatile uint32_t *w = (volatile uint32_t *)rsc;
		K60RscLayout l = k60_rsc_layout(w[0]);

		printf("K60RAIL rsc drv_id=%#x version=%u stride=%u cmd=%u "
		    "ctrl=%#x enable=%#x msgid=%#x addr=%#x data=%#x\n", w[0],
		    (unsigned)((w[0] >> 16) & 0xff), l.tcs_stride, l.cmd_stride,
		    l.control, l.cmd_enable, l.cmd_msgid, l.cmd_addr, l.cmd_data);

		/* Same pass, same gate, single shot: if k60_adsp_bring_up()
		 * already measured this boot, print that ledger instead of
		 * mapping a second time (P-223). */
		if (k60_rail_ledger() == 0) {
			rail_record_pass(bytes, w, w[0]);
		} else {
			const K60RailLedger *led = k60_rail_ledger();

			rail_print("lcx", &led->lcx);
			rail_print("lmx", &led->lmx);
		}
	}
	return 0;
}
#endif /* KERNEL */
