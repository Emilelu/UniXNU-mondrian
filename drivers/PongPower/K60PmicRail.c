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
	*index = r->level_count - 1;
	return K60RpmhOk;
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

#ifdef KERNEL
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
	}
	return 0;
}
#endif /* KERNEL */
