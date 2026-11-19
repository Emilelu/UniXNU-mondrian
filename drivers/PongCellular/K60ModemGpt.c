#include "K60ModemGpt.h"

#include "K60ModemEfs.h"

static uint64_t
k60_gpt_le64(const uint8_t *at)
{
	uint64_t value = 0;

	for (unsigned i = 0; i < 8; i++) {
		value |= (uint64_t)at[i] << (8 * i);
	}
	return value;
}

int
k60_gpt_find(const void *entries, size_t entries_bytes, uint32_t entry_bytes,
    const char *name, K60GptPartition *out)
{
	const uint8_t *bytes = (const uint8_t *)entries;
	size_t count;

	if (entries == NULL || name == NULL) {
		return -1;
	}
	if (entry_bytes < K60_GPT_ENTRY_BYTES ||
	    entry_bytes - K60_GPT_NAME_OFFSET < K60_EFS_GPT_NAME_BYTES) {
		return -1;
	}
	count = entries_bytes / entry_bytes;

	for (size_t i = 0; i < count; i++) {
		const uint8_t *entry = bytes + i * entry_bytes;
		uint8_t type = 0;

		for (unsigned b = 0; b < K60_GPT_TYPE_BYTES; b++) {
			type |= entry[b];
		}
		if (type == 0) {
			continue;       /* the slot was never written */
		}
		if (k60_efs_name_matches(entry + K60_GPT_NAME_OFFSET,
		    K60_EFS_GPT_NAME_BYTES, name) != 0) {
			continue;
		}
		if (out != NULL) {
			out->first_lba = k60_gpt_le64(entry + 32);
			out->last_lba = k60_gpt_le64(entry + 40);
		}
		return 0;
	}
	return -1;
}

uint64_t
k60_gpt_partition_bytes(const K60GptPartition *partition, uint32_t sector_bytes)
{
	if (partition == NULL || sector_bytes == 0) {
		return 0;
	}
	if (partition->last_lba < partition->first_lba) {
		return 0;
	}
	return (partition->last_lba - partition->first_lba + 1) * sector_bytes;
}

int
k60_gpt_locate_storage(uint32_t storage, const void *entries,
    size_t entries_bytes, uint32_t entry_bytes, uint32_t sector_bytes,
    uint64_t *first_lba, uint64_t *image_bytes)
{
	const char *name = k60_efs_partition(storage);
	K60GptPartition partition;
	uint64_t bytes;

	if (name == NULL) {
		return -1;
	}
	if (k60_gpt_find(entries, entries_bytes, entry_bytes, name,
	    &partition) != 0) {
		return -1;
	}
	bytes = k60_gpt_partition_bytes(&partition, sector_bytes);
	if (bytes == 0) {
		return -1;
	}
	if (first_lba != NULL) {
		*first_lba = partition.first_lba;
	}
	if (image_bytes != NULL) {
		*image_bytes = bytes;
	}
	return 0;
}
