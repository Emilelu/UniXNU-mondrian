/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* The EFS image table and the scatter-to-copy mapping. Protocol only: no UFS,
 * no SCM, no allocation, so the host test and the kernel share it. */

#include "K60ModemEfs.h"

typedef struct {
	const char *boot;
	const char *partition;
} K60EfsImage;

static const K60EfsImage k60_efs_images[K60_EFS_IMAGE_COUNT] = {
	{ "/boot/modem_fs1", "modemst1" },
	{ "/boot/modem_fs2", "modemst2" },
	{ "/boot/modem_fsg", "fsg" },
	{ "/boot/modem_fsc", "fsc" },
};

const char *
k60_efs_partition(uint32_t storage)
{
	if (storage == 0 || storage > K60_EFS_IMAGE_COUNT) {
		return NULL;
	}
	return k60_efs_images[storage - 1].partition;
}

const char *
k60_efs_boot_path(uint32_t storage)
{
	if (storage == 0 || storage > K60_EFS_IMAGE_COUNT) {
		return NULL;
	}
	return k60_efs_images[storage - 1].boot;
}

int
k60_efs_name_matches(const void *entry, size_t entry_bytes, const char *name)
{
	const uint8_t *at = (const uint8_t *)entry;
	size_t units;
	size_t i;

	if (entry == NULL || name == NULL || entry_bytes < 2) {
		return -1;
	}
	units = entry_bytes / 2;
	if (units > K60_EFS_GPT_NAME_BYTES / 2) {
		units = K60_EFS_GPT_NAME_BYTES / 2;
	}
	for (i = 0; i < units; i++) {
		const uint16_t unit = (uint16_t)(at[2 * i] | (uint16_t)(at[2 * i + 1] << 8));

		if (name[i] == '\0') {
			/* The entry may not run past the end of the name. */
			return unit == 0 ? 0 : -1;
		}
		if (unit != (uint16_t)(uint8_t)name[i]) {
			return -1;
		}
	}
	/* The name is longer than the entry: only a zero terminated entry can
	 * match, and a 36-unit entry is never terminated. */
	return -1;
}

int
k60_efs_plan(const K60RmtfsRequest *request, uint64_t image_bytes,
    uint64_t window_base, uint64_t window_bytes, K60EfsSpan *out, size_t cap)
{
	size_t written = 0;
	size_t i;

	if (request == NULL || out == NULL || request->message != K60_RMTFS_RW) {
		return -1;
	}
	if (request->vectors == 0 || request->vectors > cap ||
	    request->vectors > K60_RMTFS_MAX_VECS) {
		return -1;
	}
	for (i = 0; i < request->vectors; i++) {
		const K60RmtfsVec *vec = &request->table[i];
		const uint64_t image_offset = (uint64_t)vec->block_offset * K60_RMTFS_BLOCK;
		const uint64_t bytes = (uint64_t)vec->block_length * K60_RMTFS_BLOCK;

		if (vec->block_length == 0) {
			continue;
		}
		if (image_offset > image_bytes || bytes > image_bytes - image_offset) {
			return -1;
		}
		if (vec->physical < window_base ||
		    (uint64_t)vec->physical - window_base > window_bytes ||
		    bytes > window_bytes - ((uint64_t)vec->physical - window_base)) {
			return -1;
		}
		out[written].image_offset = image_offset;
		out[written].buffer_offset = (uint64_t)vec->physical - window_base;
		out[written].bytes = (uint32_t)bytes;
		written++;
	}
	if (written == 0) {
		return -1;
	}
	return (int)written;
}
